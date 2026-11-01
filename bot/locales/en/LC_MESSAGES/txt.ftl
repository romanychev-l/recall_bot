message-welcome =
    Hi! I'm a spaced-repetition bot for learning English vocabulary.

    Words go from the most frequent to rarer ones. Where do we start?

    🌱 <b>From scratch</b> — if you're a beginner.
    ⏩ <b>I know some already</b> — skip the basics, you'll say how many.
message-onboarded_zero = Great — starting from the most frequent words 👍
message-onboarded_skip = Done! Skipped the first { $n } words — starting right after them.
message-ask_skip_n =
    How many of the most frequent words do you already know?

    Send a number — we'll start with the next word (0–100000).
message-bad_skip_n = Need an integer from 0 to 100000.
message-try_learn_hint = Use /learn to start a session.
message-not_onboarded = First use /start.
message-nothing_due = Nothing is due for review right now. Want to continue? Tap “More words” or use /more.
message-session_done = Session complete! Continue learning or add new words with “More words” or /more. /stats — see progress.
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
message-unknown_command = I don't understand. Commands: /start /learn /more /stats /settings /help
message-cram_started = Added { $n } new words. Let’s start!
message-cram_bad_n = Use /more or /more N, where N is an integer from 1 to 500. /cram N also works.
message-no_more_words = No more words in the dictionary 🎉
message-settings_summary =
    Settings:

    • Batch size: { $batch }
    • Reminder time: { $reminder }
    • Timezone: { $tz }
    • Parts of speech: { $parts }
    • New words remaining: { $count }

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
    Next new word matching your filter: { $next_rank }

    CEFR progress (review + graduated):
    { $cefr }
message-pos_summary =
    <b>Parts of speech</b>

    Selected: { $parts }
    New words remaining: <b>{ $count }</b>

    From “All”, tap a category to select just that one. Then tap categories to add or remove them. Changes save immediately; keep at least one category selected.
    The filter applies to new words and reviews. Hidden cards keep their progress and intervals and return when their categories are selected. Each card keeps the meanings it was issued with.
    The counter includes words after your starting level that do not have a card yet. Previously issued words are excluded.
message-pos_empty = Select at least one part of speech. Tap “All parts of speech” to restore the full dictionary.
message-no_matching_words = No new words match the selected parts of speech. Change your selection in /settings. Existing cards and progress are preserved.
message-nothing_due_filtered = No matching cards are due right now. Add new words with /more or change parts of speech in /settings. Hidden cards and their progress are preserved.
message-help =
    📖 Commands:

    /learn — continue learning: reviews and all unfinished batches
    /more <code>N</code> — add new words and start learning immediately;
       without a number — your batch size, with a number — 1 to 500 words
    /cram <code>N</code> — force-session of N new words (default 50, max 500),
       bypasses batch/daily_goal — handy for clicking through familiar words
    /stats — progress: today / learning / graduated / CEFR
    /settings — parts of speech, batch size, reminder time, timezone
    /start — restart onboarding (change starting rank)
    /help — this message

    On a card (inline buttons):
    🤔 <b>Don't know</b> — reveal answer, count as wrong, advance
    ⏭ <b>Skip</b> — postpone until tomorrow, no scoring

    Just type the English word in chat — that's your answer.

button-start_zero = 🌱 Start from scratch
button-start_skip = ⏩ I already know some
button-skip = ⏭ Skip
button-hard = Hard
button-dont_know = 🤔 Don't know
button-settings_batch = Batch size
button-settings_reminder = Reminder time
button-settings_tz = Timezone
button-settings_pos = Parts of speech
button-pos_all = All parts of speech
button-pos_done = Done
pos-noun = Nouns
pos-verb = Verbs
pos-adj = Adjectives
pos-adv = Adverbs
pos-pron = Pronouns
pos-num = Numerals
pos-prep = Prepositions
pos-conj = Conjunctions
pos-det = Determiners
pos-intj = Interjections
pos-particle = Particles
pos-name = Proper names
pos-phrase = Expressions
pos-other = Other / unclassified

button-more_words = ➕ More words
button-continue_learning = ▶️ Continue
command-learn = Continue learning
command-more = Add new words
command-stats = My progress
command-settings = Learning settings
command-help = Command help
command-start = Choose starting level
command-cram = Add 50 new words or specify a number
command-skip = How to skip a word
command-hard = How to mark a difficult word
