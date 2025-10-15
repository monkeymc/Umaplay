# UMA MUSUME (UmaPlay) – Backlog (organized)

This organizes the mixed notes into a clear, actionable backlog. Items are grouped by workstream and priority. “Later” holds non-urgent ideas. A final section captures non-UMA (“Meta Manager”) items so they don’t pollute the UMA queue.

================================================================================
NEXT WORK (towards 0.3.0)

0.2.1
New cards / New trainees:
- Fuji Kiseki, Gold City, Special Week (Summer), Maruzensky (Summer)

0.2.2
Skill buying
- Improve Control for double buying of single circle skills:
"""
So, in our screen where we are buying skills, we have a pseudo-control to control how much time we need to buy, and that is working. The problem is that the next time that we visit the skills, that is reset, so we are buying again the same skills. So maybe we need to persist in a higher level, maybe at player level, what skills have we bought, and so the next time... So we have this memory of the skills that we bought, that were enabled, and given this, we can control to not buy more, especially the skills that has one single circle. So we only buy one, and the next time we match with the OCR we just can ignore, so we need this kind of memory to understand which skills we bought.
"""

0.3.0
Bot Strategy / Policy:
- Hint support card priority checker:
"""
So now we are detecting if we have a tile but we will like to and also we are detecting events for certain super cards and we have all the super cards cards in in the web public and here's the thing not all the hints are available sometimes we have a deck of six cards and we have three cards that are very important to get all the hints and the other ones well we we should ignore them because they will not provide a good skill for for the Yuma so we need to figure out a way that we can not even not only know that is a hint card but also if this hint card looks like looks like a particular super card so we can have a priority of support cards and also a blacklist for which cards ignore the hint I was thinking in training a classifier we will have a lot of we will have a lot of cards in the future we only we only have one image per card so maybe we can do a kind of data augmentation and then we can pseudo create the circle around the face and we can start creating this classifier so each time we we notice we have a hint we can run the classifier and check if that is in the priority list that will be also connected in the web UI and if that's the case we can add the extra value to the hint otherwise we can use the the default value for hint even if hint is important is enabled
"""
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

Events
- Added SSR: Mejiro Ryan (GUTS), Narita Brian (SPD), Daiwa Scarlet (PWR), Winning Ticket (STA), Sweep Tosho (SPD), Mejiro Ardan (WIT)

Team Trials
- Bug fix: instead of clicking races, now clicks around same button, solves Stale state

