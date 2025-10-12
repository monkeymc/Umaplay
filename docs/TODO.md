# UMA MUSUME (UmaPlay) – Backlog (organized)

This organizes the mixed notes into a clear, actionable backlog. Items are grouped by workstream and priority. “Later” holds non-urgent ideas. A final section captures non-UMA (“Meta Manager”) items so they don’t pollute the UMA queue.

================================================================================
NEXT WORK (towards 0.3.0)

0.2.1
New cards / New trainings:
- Automate with Chatgpt pipeline the new cards integration. With python pipeline too.

0.2.2
Skill buying
- Bug recognizing titles (75% of accuracy)
- Improve Control for double buying of single circle skills

0.2.3
Team trials:
- Stale state handling storing counting to not make more count click than expected

0.3.0
Bot Strategy / Policy:
- Hint support card priority checker
- Lookup toggle: allow skipping **scheduled race** if training has **2+ rainbows**
- “Check first” at lobby: pre-turn heuristics before going to infirmaty, rest, etc. Pre lookup
- “Hint” robustness: reduce misses (tune ROI, add ensemble check, raise min conf with a small hysteresis).
- Slight WIT nerf on weak turns (prevent over-weighting).
- Gold Ship training restriction coverage.
- Set Tazuna card training options and special scores / logic. if support_tazuna is there, add +0.15 (orange, yellow, max). Or pal in general in support type. Capture in lobby stats 'Recreation Tazuna' for later trainig decisions
- put parameter in web ui, to decide when is 'weak' turn based on SV. Weak turn classifications is used to decide if go to race, rest or recreation instead of training
- configurable scoring system

---------------------
Priority for 0.4.0:

- Daily race:
  - when race again is disabled automatically finalize, same for money row

Bot Strategy / Policy:
- avoid **3 races in a row
- Final Season: consider turn number; avoid Rest on last turn but allow earlier; better plan to exploit Summer training (Rest may be worse than training).
- Training 'S' uma with wit and speed for 'Team trials'. Particular setup
- Suggestion: "Each card also has a different "rainbow bonus". For instance, the Manhattan Cafe STAM card has 1.2 Friendship multiplier, while Super Creek STAM has 1.375, so Super Creek should nudge the bot to click it more than Manhattan Cafe."
- Adapt Triple Tiara, Crown, and Senior preconfigs

Turns
- Better turn number prediction (11 or 1 for example, fails)

UI / UX
- End-of-career: if nothing was bought, ensure it goes **Back** correctly.

Team trials:
- handle 'story unlocked' (press close button), before shop

Skills:
  - Add auto buy best option based on running style (with a premade priority list)

================================================================================
LATER (nice-to-have / backlog)
------------------------------
Mobile / UI
- On mobile, avoid tapping “View result” too quickly (misclassifies as inactive).
- Web UI perf: investigate skills.json / races.json bottlenecks.
- Reduce BlueStacks crop.
- Decrease usage of ram in backend too
- adb version, emulator support

Skill lis:
- Early stop at scrolling skill list at endgame when all desired 3 hints bought (fix case where first isn’t bought).

Racing
- Prioritize **G1** and **fans**: smart search to train for fans when needed.
- Reactivity: race handling is slow — reduce latencies.

Control & Safety
- Implement **immediate stop** (do not wait for routine end).

Edge cases
- SIM phone notification: click a plausible button if shown.
- Fans handling for “director training” decisions.

Racing & Schedule
- Connection error handler (“A connection error occurred”): detect dialog with **white** and **green** buttons; handle “Title Screen” and “Retry”.
row** and racing at **0 energy**.


================================================================================
IMPLEMENTED — PENDING VALIDATION
--------------------------------

Bot for Auto Team Trials (Experimental)
- Auto-play with F7
- Shop purchase handling
- Session resume support

Bot for Auto Daily Races (Experimental)
- Auto-play with F8
- Shop purchase handling
- Session resume support

AI Model
- Retrained with 100+ additional images
- Improved detection of rainbows and support cards in general
- Added support_tazuna card detection

Bot for Training -> Strategy / Policy:
- Undertrain stat % now configurable in web UI
- Improved undertrain distribution (focuses on top 3 stats)
- Option to disable racing if no good options available
- Improved summer training logic (prevents energy overcap)

Race Scheduler Fixes
- Fixed race detection for events with similar conditions (e.g., Tokyo Yushun vs Japanese Oaks)
- Better handling of races with 'varies' in conditions gametora DB (e.g., JBC Ladies' Classic)
- Fixed 75% scheduled race skip rate issue

Skill buying
- Optimized skill buy check, using intervals to avoid checking too often.

Web UI
- Moved hint configuration to presets
- Fixed/Wired custom failure/rest % settings
- Preset importer now backward compatible
- Automatic browser opening on start at 127.0.0.1 (not the same as localhost, they hold different configs)

General Bug Fixes
- Fixed trainee options not overriding general settings
- Faster skill buying with early stop didn't worked, solved with 'patiente' strategy.
- Better ambiguous text matching for events (e.g. How should I respond of oguri cap, I am enough / am I enough? of Rice shower)
- Debug folder was growing in GB, added automatic cleanup at start. So it auto cleans that folder if it has more than 250 MB.
