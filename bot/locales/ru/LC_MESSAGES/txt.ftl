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
message-nothing_due = Сейчас нет слов для повторения. Хочешь продолжить? Нажми «Ещё слова» или используй /more.
message-session_done = Сессия завершена! Продолжай занятие или добавь новые слова кнопкой «Ещё слова» или командой /more. /stats — твой прогресс.
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
message-unknown_command = Не понимаю. Команды: /start /learn /more /stats /settings /help
message-cram_started = Добавлено новых слов: { $n }. Начинаем занятие!
message-cram_bad_n = Используй /more или /more N, где N — целое число от 1 до 500. Также работает /cram N.
message-no_more_words = В словаре больше нет слов 🎉
message-settings_summary =
    Настройки:

    • Размер батча: { $batch }
    • Время напоминания: { $reminder }
    • Часовой пояс: { $tz }
    • Части речи: { $parts }
    • Осталось новых слов: { $count }

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
    Следующее новое слово по фильтру: { $next_rank }

    Прогресс по CEFR (review + graduated):
    { $cefr }
message-pos_summary =
    <b>Части речи</b>

    Выбрано: { $parts }
    Осталось новых слов: <b>{ $count }</b>

    В режиме «Все» нажатие выбирает одну категорию. Затем нажимай категории, чтобы добавлять и убирать их. Выбор сохраняется сразу; нужна хотя бы одна категория.
    Фильтр действует на новые слова и повторения. Скрытые карточки сохраняют прогресс и интервалы и вернутся при выборе их категорий. У каждой карточки остаются значения, с которыми её выдали.
    Счётчик учитывает слова после твоего стартового уровня, для которых ещё нет карточки. Уже выданные слова в него не входят.
message-pos_empty = Выбери хотя бы одну часть речи. Чтобы вернуть весь словарь, нажми «Все части речи».
message-no_matching_words = Новых слов для выбранных частей речи нет. Измени выбор в /settings. Уже выданные карточки и прогресс сохранены.
message-nothing_due_filtered = Сейчас нет подходящих карточек для повторения. Добавь новые через /more или измени части речи в /settings. Скрытые карточки и их прогресс сохранены.
message-help =
    📖 Команды:

    /learn — продолжить занятие: повторения и все начатые порции слов
    /more <code>N</code> — добавить новые слова и сразу начать занятие;
       без числа — порция из настроек, с числом — от 1 до 500 слов
    /cram <code>N</code> — форс-сессия из N новых слов (default 50, max 500),
       обходит batch/daily_goal — удобно прощёлкивать знакомое
    /stats — прогресс: сегодня / в изучении / выучено / CEFR
    /settings — части речи, размер батча, время напоминания, часовой пояс
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
button-settings_pos = Части речи
button-pos_all = Все части речи
button-pos_done = Готово
pos-noun = Существительные
pos-verb = Глаголы
pos-adj = Прилагательные
pos-adv = Наречия
pos-pron = Местоимения
pos-num = Числительные
pos-prep = Предлоги
pos-conj = Союзы
pos-det = Определители
pos-intj = Междометия
pos-particle = Частицы
pos-name = Имена собственные
pos-phrase = Выражения
pos-other = Прочее / без разметки

button-more_words = ➕ Ещё слова
button-continue_learning = ▶️ Продолжить
command-learn = Продолжить обучение
command-more = Добавить новые слова
command-stats = Мой прогресс
command-settings = Настройки обучения
command-help = Помощь по командам
command-start = Выбрать начальный уровень
command-cram = Добавить 50 новых слов или задать число
command-skip = Как пропустить слово
command-hard = Как отметить сложное слово
