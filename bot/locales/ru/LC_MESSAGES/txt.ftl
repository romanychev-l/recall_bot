message-welcome =
    Привет! Это бот для изучения английских слов методом интервальных повторений.

    Слова идут от самых частотных к более редким. С чего начнём?

    🌱 <b>С нуля</b> — если ты новичок.
    ⏩ <b>Уже знаю часть</b> — пропустим базовые слова, скажешь сколько.
message-onboarded_zero = Отлично, начинаем с самых частотных слов 👍
message-onboarded_skip = Готово! Первые { $n } слов пропущены — начнём со следующих.
message-ask_skip_n =
    Сколько самых частотных слов ты уже знаешь?

    Отправь число — начнём со следующего слова (от 0 до 100000).
message-bad_skip_n = Нужно целое число от 0 до 100000.
message-try_learn_hint = Используй /learn чтобы начать занятие.
message-not_onboarded = Сначала используй /start.
message-nothing_due = Нечего повторять — все слова на интервалах. Возвращайся позже!
message-session_done = Сессия завершена. /stats — увидеть прогресс.
message-prompt_word =
    Переведи на английский: <b>{ $translation }</b>

    <i>{ $pos }</i> • осталось: { $remaining }
message-answer_correct = ✅ Верно: <b>{ $word }</b>
message-answer_wrong = ❌ Неверно. Было: <b>{ $expected }</b>. Ты написал: <i>{ $got }</i>
message-answer_revealed = 👀 Было: <b>{ $word }</b>. Помечено как сложное.
message-new_batch_issued = 🎉 Текущий батч пройден — выдан новый!
message-skipped_today = Пропущено до завтра
message-marked_hard = Помечено как сложное
message-skip_only_inline = /skip работает через кнопку в карточке.
message-hard_only_inline = /hard работает через кнопку в карточке.
message-unknown_command = Не понимаю. Команды: /start /learn /cram /stats /settings
message-cram_started = 🚀 Cram-сессия: { $n } новых слов.
message-cram_bad_n = /cram N — число от 1 до 500.
message-no_more_words = В словаре больше нет слов 🎉
message-settings_summary =
    Настройки:

    • Размер батча: { $batch }
    • Время напоминания: { $reminder }
    • Часовой пояс: { $tz }

    Что меняем?
message-ask_batch_size = Введи размер батча (1–100):
message-bad_batch_size = Нужно целое число от 1 до 100.
message-ask_reminder_time = Введи время напоминания в формате HH:MM (например, 19:30):
message-bad_reminder_time = Формат: HH:MM (от 00:00 до 23:59).
message-ask_tz = Введи часовой пояс в формате tzdata (например, Europe/Moscow):
message-bad_tz = Неизвестный часовой пояс.
message-saved = Сохранено.
message-stats_summary =
    📊 Твоя статистика

    Сегодня: { $today_correct } / { $today_total }
    В изучении: { $learning }
    На повторении: { $review }
    Выучено (graduated): { $graduated }

    Точность за 7д: { $accuracy }
    Серия дней: { $streak }
    Следующее новое слово в словаре: #{ $next_rank }

    Прогресс по CEFR (review + graduated):
    { $cefr }
message-help =
    📖 Команды:

    /learn — занятие: due-карточки + новые из активного батча
    /cram <code>N</code> — форс-сессия из N новых слов (default 50, max 500),
       обходит batch/daily_goal — удобно прощёлкивать знакомое
    /stats — прогресс: сегодня / в изучении / выучено / CEFR
    /settings — размер батча, время напоминания, часовой пояс
    /start — заново онбординг (сменить стартовый ранк)
    /help — эта подсказка

    В карточке (inline-кнопки):
    🤔 <b>Не знаю</b> — показать ответ, засчитать как ошибку, дальше
    ⏭ <b>Пропустить</b> — отложить до завтра, без оценки

    Просто пиши английское слово в чат — это и есть ответ.

button-start_zero = 🌱 Начать с нуля
button-start_skip = ⏩ Уже знаю часть слов
button-skip = ⏭ Пропустить
button-hard = Сложное
button-dont_know = 🤔 Не знаю
button-settings_batch = Размер батча
button-settings_reminder = Время напоминания
button-settings_tz = Часовой пояс
