message-welcome =
    Hi! I'm a spaced-repetition bot for learning English vocabulary.

    Choose your starting point:
message-onboarded_zero = Starting from the most frequent words. Ready!
message-onboarded_skip = Skipping the first { $n } words. Ready!
message-ask_skip_n = How many words to skip (0–100000)? Send a number.
message-bad_skip_n = Need an integer from 0 to 100000.
message-try_learn_hint = Use /learn to start a session.
message-not_onboarded = First use /start.
message-nothing_due = Nothing to review — all cards are on intervals. Come back later!
message-session_done = Session complete. /stats — see progress.
message-prompt_word =
    Translate to English: <b>{ $translation }</b>

    <i>{ $pos }</i> • remaining: { $remaining }
message-answer_correct = ✅ Correct: <b>{ $word }</b>
message-answer_wrong = ❌ Wrong. Expected: <b>{ $expected }</b>. You wrote: <i>{ $got }</i>
message-answer_revealed = 👀 Was: <b>{ $word }</b>. Marked as hard.
message-new_batch_issued = 🎉 Current batch cleared — new batch issued!
message-skipped_today = Skipped until tomorrow
message-marked_hard = Marked as hard
message-skip_only_inline = /skip works via the card button.
message-hard_only_inline = /hard works via the card button.
message-unknown_command = I don't understand. Commands: /start /learn /cram /stats /settings
message-cram_started = 🚀 Cram session: { $n } new words.
message-cram_bad_n = /cram N — number from 1 to 500.
message-no_more_words = No more words in the dictionary 🎉
message-settings_summary =
    Settings:

    • Batch size: { $batch }
    • Reminder time: { $reminder }
    • Timezone: { $tz }

    What to change?
message-ask_batch_size = Enter batch size (1–100):
message-bad_batch_size = Need an integer from 1 to 100.
message-ask_reminder_time = Enter reminder time in HH:MM format (e.g., 19:30):
message-bad_reminder_time = Format: HH:MM (00:00 to 23:59).
message-ask_tz = Enter timezone in tzdata format (e.g., Europe/Moscow):
message-bad_tz = Unknown timezone.
message-saved = Saved.
message-stats_summary =
    📊 Your stats

    Today: { $today_correct } / { $today_total }
    Learning: { $learning }
    Review: { $review }
    Graduated: { $graduated }

    Accuracy (7d): { $accuracy }
    Streak: { $streak }
    Next new word at rank #{ $next_rank }

    CEFR progress (review + graduated):
    { $cefr }
message-help =
    📖 Commands:

    /learn — session: due cards + new from active batch
    /cram <code>N</code> — force-session of N new words (default 50, max 500),
       bypasses batch/daily_goal — handy for clicking through familiar words
    /stats — progress: today / learning / graduated / CEFR
    /settings — batch size, reminder time, timezone
    /start — restart onboarding (change starting rank)
    /help — this message

    On a card (inline buttons):
    🤔 <b>Don't know</b> — reveal answer, count as wrong, advance
    ⏭ <b>Skip</b> — postpone until tomorrow, no scoring

    Just type the English word in chat — that's your answer.

button-start_zero = From scratch (most frequent)
button-start_skip = I already know N words
button-skip = ⏭ Skip
button-hard = Hard
button-dont_know = 🤔 Don't know
button-settings_batch = Batch size
button-settings_reminder = Reminder time
button-settings_tz = Timezone
