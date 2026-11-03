"""Group messages are handled before any personal learning or settings state."""
from __future__ import annotations

import logging
from html import escape

from aiogram import BaseMiddleware, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message, ReplyParameters
from sqlalchemy.exc import SQLAlchemyError

from bot.constants import DEFAULT_TZ
from bot.services.group_service import GROUP_HELP, next_report_at, utc_now, validate_schedule

logger = logging.getLogger(__name__)
router = Router(name="groups")
GROUP_TYPES = {ChatType.GROUP, ChatType.SUPERGROUP}
router.message.filter(F.chat.type.in_(GROUP_TYPES))
router.callback_query.filter(F.message.chat.type.in_(GROUP_TYPES))
router.my_chat_member.filter(F.chat.type.in_(GROUP_TYPES))
router.chat_member.filter(F.chat.type.in_(GROUP_TYPES))


class GroupErrorMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except (SQLAlchemyError, TelegramAPIError):
            logger.exception("group_request_failed")
            try:
                await event.answer("Не удалось обновить таблицу. Попробуй ещё раз чуть позже.")
            except TelegramAPIError:
                pass


router.message.middleware(GroupErrorMiddleware())
router.callback_query.middleware(GroupErrorMiddleware())


async def require_sender(message: Message) -> bool:
    if message.from_user and not message.from_user.is_bot and not message.sender_chat:
        return True
    await message.answer("Отправь команду от своего имени, без анонимного режима администратора.")
    return False


async def require_group(message: Message, groups):
    group = await groups.repository.get(message.chat.id)
    if group is None:
        await message.answer("Таблица ещё не создана. Отправь /challenge, чтобы начать и вступить первым.")
    return group


async def require_manager(message: Message, group: dict) -> bool:
    if not await require_sender(message):
        return False
    if message.from_user.id == group["creator_id"]:
        return True
    administrators = await message.bot.get_chat_administrators(message.chat.id)
    if any(member.user.id == message.from_user.id for member in administrators):
        return True
    await message.answer("Расписание могут менять организатор и администраторы группы.")
    return False


@router.message(F.migrate_to_chat_id | F.migrate_from_chat_id)
async def migrate_group(message: Message, container) -> None:
    old_id = message.chat.id if message.migrate_to_chat_id else message.migrate_from_chat_id
    new_id = message.migrate_to_chat_id or message.chat.id
    async with container.groups.lock(old_id):
        await container.groups.repository.migrate(old_id, new_id)


@router.message(F.left_chat_member)
async def member_left(message: Message, container) -> None:
    async with container.groups.lock(message.chat.id):
        await container.groups.repository.leave(message.chat.id, message.left_chat_member.id)


@router.message(Command("challenge"))
async def create_group(message: Message, container) -> None:
    if not await require_sender(message):
        return
    user = await container.users_repo.get(message.from_user.id)
    zone = user["tz"] if user else DEFAULT_TZ
    await container.groups.create(message, zone)


@router.message(Command("leaders", "stats"))
async def show_leaders(message: Message, command: CommandObject, container) -> None:
    try:
        page = int(command.args or "1")
        if page < 1:
            raise ValueError
    except ValueError:
        await message.answer("Используй /leaders или /leaders 2 для следующей страницы.")
        return
    async with container.groups.lock(message.chat.id):
        group = await require_group(message, container.groups)
        if group:
            await container.groups.publish(group, page=page)


@router.message(Command("join"))
async def join_by_command(message: Message, container) -> None:
    if not await require_sender(message):
        return
    async with container.groups.lock(message.chat.id):
        group = await require_group(message, container.groups)
        if group:
            joined = await container.groups.join(group["id"], message.from_user)
            await message.answer("Ты участвуешь! Учи слова в личном чате с Recall." if joined else "Ты уже участвуешь.")
            if joined:
                await container.groups.publish(group, edit=True)


@router.callback_query(F.data == "group:join")
async def join_by_button(callback: CallbackQuery, container) -> None:
    if callback.from_user.is_bot:
        await callback.answer()
        return
    chat_id = callback.message.chat.id
    async with container.groups.lock(chat_id):
        group = await container.groups.repository.get(chat_id)
        if group is None:
            await callback.answer("Сначала создай таблицу командой /challenge.")
            return
        joined = await container.groups.join(chat_id, callback.from_user)
        await callback.answer("Ты участвуешь! Учи слова в личном чате с Recall." if joined else "Ты уже участвуешь.")
        if joined:
            await container.groups.publish(group, edit=True)


@router.callback_query(F.data.startswith("group:refresh:"))
async def refresh(callback: CallbackQuery, container) -> None:
    try:
        page = int(callback.data.rsplit(":", 1)[1])
        if page < 1:
            raise ValueError
    except ValueError:
        await callback.answer("Не удалось определить страницу таблицы.")
        return
    chat_id, message_id = callback.message.chat.id, callback.message.message_id
    if container.groups.reserve_refresh(chat_id, message_id):
        await callback.answer("Обновлять можно раз в 5 секунд.", cache_time=0)
        return
    async with container.groups.lock(chat_id):
        group = await container.groups.repository.get(chat_id)
        if group:
            await container.groups.publish(group, page=page, message_id=message_id)
    await callback.answer("Статистика обновлена" if group else "Сначала создай таблицу командой /challenge.")


@router.message(Command("leave"))
async def leave_group(message: Message, container) -> None:
    if not await require_sender(message):
        return
    async with container.groups.lock(message.chat.id):
        group = await require_group(message, container.groups)
        if group:
            left = await container.groups.repository.leave(group["id"], message.from_user.id)
            await message.answer("Ты вышел из таблицы этого чата. Вернуться можно кнопкой «Вступить»." if left else "Ты пока не участвуешь в таблице этого чата.")
            if left:
                await container.groups.publish(group, edit=True)


@router.message(Command("settings"))
async def group_settings(message: Message, command: CommandObject, container) -> None:
    async with container.groups.lock(message.chat.id):
        group = await require_group(message, container.groups)
        if group is None:
            return
        if command.args:
            if not await require_manager(message, group):
                return
            args = command.args.split()
            try:
                if len(args) not in (1, 2):
                    raise ValueError("Используй /settings 21:00 Europe/Moscow")
                zone = args[1] if len(args) == 2 else group["timezone"]
                validate_schedule(args[0], zone)
            except ValueError as error:
                await message.answer(escape(str(error)))
                return
            changes = {"report_time": args[0], "timezone": zone,
                       "next_report_at": next_report_at(args[0], zone, utc_now())}
            await container.groups.repository.update(group["id"], **changes)
            group.update(changes)
            await container.groups.publish(group, edit=True)
        status = "включены" if group["enabled"] else "на паузе"
        await message.answer(f"Сводки: <b>{status}</b>\nВремя: <b>{group['report_time']}</b> "
                             f"({escape(group['timezone'])})\n\n"
                             "Изменить: /settings 21:00 Europe/Moscow\n"
                             "Выключить: /pause · Включить: /resume")


@router.message(Command("pause", "resume"))
async def set_publications(message: Message, command: CommandObject, container) -> None:
    async with container.groups.lock(message.chat.id):
        group = await require_group(message, container.groups)
        if group is None or not await require_manager(message, group):
            return
        changes = {"enabled": command.command == "resume"}
        if changes["enabled"]:
            changes.update(bot_present=True, next_report_at=next_report_at(group["report_time"], group["timezone"], utc_now()))
        await container.groups.repository.update(group["id"], **changes)
        group.update(changes)
        await container.groups.publish(group, edit=True)
        await message.answer("Вечерние сводки включены." if group["enabled"] else "Сводки на паузе. Участники и статистика сохраняются.")


@router.message(Command("help_group", "help", "start"))
async def group_help(message: Message, command: CommandObject, container) -> None:
    # Telegram's "Add to group" deep link can initialize the table in one step.
    if command.command == "start" and command.args == "challenge":
        await create_group(message, container)
        return
    await message.answer(GROUP_HELP, reply_markup=await container.groups.keyboard())


@router.message(Command("learn", "more", "cram", "skip", "hard"))
async def open_personal_bot(message: Message, container) -> None:
    await message.answer("Учить слова можно в личном чате с Recall. В группе — общая статистика: /leaders.",
                         reply_markup=await container.groups.keyboard())


def is_present(member) -> bool:
    return member.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR) or (
        member.status == ChatMemberStatus.RESTRICTED and member.is_member)


@router.my_chat_member()
async def bot_membership(event: ChatMemberUpdated, container) -> None:
    present = is_present(event.new_chat_member)
    async with container.groups.lock(event.chat.id):
        await container.groups.repository.update(event.chat.id, bot_present=present)
    if present and not is_present(event.old_chat_member):
        username = (await container.groups.bot_url()).rsplit("/", 1)[1]
        await event.answer("Привет! Я Recall. Учите английские слова в личном чате, "
                           "а здесь используйте их в разговоре: я буду отмечать практику ещё не освоенных слов. "
                           "Для этого достаточно быть пользователем Recall; вступать в таблицу не обязательно.\n\n"
                           f"/challenge@{username} — создать таблицу и вступить первым\n"
                           f"/help_group@{username} — правила и команды\n\n"
                           "Остальные участники смогут нажать «Вступить». Сводки по умолчанию — в 21:00.\n\n"
                           "Чтобы я видел обычные сообщения, нужны права администратора группы "
                           "или отключённый Privacy Mode в BotFather.",
                           reply_markup=await container.groups.keyboard(include_join=False))


@router.chat_member()
async def participant_membership(event: ChatMemberUpdated, container) -> None:
    if not is_present(event.new_chat_member):
        async with container.groups.lock(event.chat.id):
            await container.groups.repository.leave(event.chat.id, event.new_chat_member.user.id)


@router.message()
async def observe_group_message(message: Message, container) -> None:
    # This terminal handler also keeps group text away from personal quiz states.
    try:
        words = await container.practice.observe(message)
        if words:
            shown = ', '.join(f'<b>{escape(word)}</b>' for word in words[:5])
            extra = f' и ещё {len(words) - 5}' if len(words) > 5 else ''
            await message.bot.send_message(
                chat_id=message.chat.id, message_thread_id=message.message_thread_id,
                text=f'🙌 Английский в деле: {shown}{extra}! Практика новых слов учтена.',
                reply_parameters=ReplyParameters(message_id=message.message_id, allow_sending_without_reply=True),
            )
    except (SQLAlchemyError, TelegramAPIError):
        # A failed acknowledgement must not turn normal conversation into an
        # error/retry loop; committed usage credit remains available in /stats.
        logger.exception('chat_practice_failed chat_id=%s', message.chat.id)


@router.callback_query()
async def ignore_personal_callback(callback: CallbackQuery) -> None:
    await callback.answer("Открой личный чат с ботом, чтобы учить слова.")
