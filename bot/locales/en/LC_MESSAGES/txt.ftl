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
    📊 Your stats:

    Graduated total: { $graduated }
    Accuracy (7d): { $accuracy }
    Streak: { $streak }

    CEFR progress:
    { $cefr }

button-start_zero = From scratch (most frequent)
button-start_skip = I already know N words
button-skip = Skip
button-hard = Hard
button-settings_batch = Batch size
button-settings_reminder = Reminder time
button-settings_tz = Timezone
