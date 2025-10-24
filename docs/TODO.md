# UMA MUSUME (UmaPlay) – Backlog (organized)

This organizes the mixed notes into a clear, actionable backlog. Items are grouped by workstream and priority. “Later” holds non-urgent ideas. A final section captures non-UMA (“Meta Manager”) items so they don’t pollute the UMA queue.

================================================================================
NEXT WORK (towards 0.3.0)

0.3.0 base
Bot Strategy / Policy:
- Hint support card priority checker
- auto wheel clicker for bingo event?
- Daily buy screen, to allow buying star pieces too. Request from: 

0.3.1+
Bot Strategy / Policy:
- Lookup toggle: allow skipping **scheduled race** if training has **2+ rainbows**
  “Check first” at lobby: pre-turn heuristics before going to infirmaty, rest, etc. Pre lookup
  "Check first" allowed for races individually set



- Set Tazuna card training options and special scores / logic. if support_tazuna is there, add +0.15 (orange, yellow, max). 
- Capture in lobby stats'Recreation Tazuna' for later trainig decisions
  -> When energy needed, and tazuna available, prefer tazuna (keep the chain counting to not select one with no good energy recovery)
- parameter to define 'weak turn' / 'low training'
- configurable scoring system


---------------------
Priority for 0.4.0:

For the claw machine, I would suggest that it only select the first plushie on the first row. This way, you can almost guarantee a successful catch and should have a much easier time dealing with it compared to trying with the other rows. If you have yet to try it that is.

While we've got activity here:
I'd suggest increasing the OCR threshold for skills to 0.9 - currently some near matches have confidence in the 0.8s such as standard distance to non-standard distance and Tokyo racecourse to Kyoto racecourse


Is it possible to to add a CLI flag to specify port, ie --port 8005

regarding the OCR, I would prefer to have a kind of 'exceptions' / 'custom logic' for those particular cases


Micro elements recognizer
- Improve Control for double buying of single circle skills:
"""
So, in our screen where we are buying skills, we have a pseudo-control to control how much time we need to buy, and that is working. The problem is that the next time that we visit the skills, that is reset, so we are buying again the same skills. So maybe we need to persist in a higher level, maybe at player level, what skills have we bought, and so the next time... So we have this memory of the skills that we bought, that were enabled, and given this, we can control to not buy more, especially the skills that has one single circle. So we only buy one, and the next time we match with the OCR we just can ignore, so we need this kind of memory to understand which skills we bought.
"""
- Prepare multiple icons recognized (Aoharu hai [Unity cup], etc. Fire blue and more)
- “Hint” robustness: reduce misses (tune ROI, add ensemble check, raise min conf with a small hysteresis).
- Slight WIT nerf on weak turns (prevent over-weighting).
- put parameter in web ui, to decide when is 'weak' turn based on SV. Weak turn classifications is used to decide if go to race, rest or recreation instead of training

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
  - Bug recognizing titles (75% of accuracy)

================================================================================
LATER (nice-to-have / backlog)
------------------------------
Mobile / UI
- On mobile, avoid tapping “View result” too quickly (misclassifies as inactive).
- Web UI perf: investigate skills.json / races.json bottlenecks.
- Reduce BlueStacks crop.
- Decrease usage of ram in backend too
- adb version, emulator support

- Gold Ship training restriction coverage.

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
-------