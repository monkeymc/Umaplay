# UMA MUSUME (UmaPlay) – Backlog (organized)

This organizes the mixed notes into a clear, actionable backlog. Items are grouped by workstream and priority. “Later” holds non-urgent ideas. 

================================================================================
## 0.3

### 0.3.2

General:
- @EpharGy: Add a CLI flag to specify port, ie --port 8005
- Base model uma full training.
- “Hint Icon” recognition with same YOLO: so we reduce misses. Don't use color for this.
- Change 'hint value enabled' instead of only 'hint enabled' or hint not ignored, something more clear
- Cleanup requirements for python 3.10, delete some unused dependencies, pin all versions. TEST in real pc

Skill Buying:
- @Rosetta / @Hibiki: Improve OCR ambiguos recognition (reports). non-standard vs standard for example and others of taking the lead / leading the .... This person shared some ZIP files that can help.
"""
regarding the OCR, I would prefer to have a kind of 'exceptions' / 'custom logic' for those particular cases
"""
- @EO1:Web UI: Organize the types of skills so you don't have to search every single skill you need like debuffs, stamina skills, greens, purples etc. Also include new ones and images to make it easier.
- Improve Control for double buying of single circle skills. if hint / skill already got / bought, not take that hint anymore:
"""
So, in our screen where we are buying skills, we have a pseudo-control to control how much time we need to buy, and that is working. The problem is that the next time that we visit the skills, that is reset, so we are buying again the same skills. So maybe we need to persist in a higher level, maybe at player level, what skills have we bought, and so the next time... So we have this memory of the skills that we bought, that were enabled, and given this, we can control to not buy more, especially the skills that has one single circle. So we only buy one, and the next time we match with the OCR we just can ignore, so we need this kind of memory to understand which skills we bought.
"""

Events:
- @EO1: Include Summer Characters and new characters and cards. Make it scalable and more easy to replicate


### 0.3.3
Claw Machine:
- @Rosetta: Re-check of the logic so it always Win. If first detected plushie is good enough and it is not at the border take it, if not do a full scan

Bug:
- race.py 867 when getting the style_btns chosen, error of list index out of range

## 0.4

### 0.4.0

General
- Add minimal testing and lint check for big refactoring
- Remove tech debt of publich path and path in template matcher
- Increase timeout uvicorn so it waits for server to answer up to 1 min
- Aoharu Hai preparation
- Color unit testing: detected as yellow the 'green' one "yellow: +0.00"

Bot Strategy / Policy:
- Lookup toggle: allow skipping **scheduled race** if training has **2+ rainbows**
  “Check first” at lobby: pre-turn heuristics before going to infirmaty, rest, etc. Pre lookup
  "Check first" allowed for races individually set
- Parameter to define 'weak turn' / 'low 
- PAL training:
  - @Rosetta: Tazuna blue was worth more, you want to get it to green ASAP to unlock her dates (there's a bonus if you do it in the junior year)
  - Make Tazuna orange/max also configurable (Also Riko Kashimoto). +0.15 (orange, yellow, max) by default
  - Capture in lobby stats'Recreation Tazuna' for later trainig decisions
    -> When energy needed, and tazuna available, prefer tazuna (keep the chain counting to not select one with no good energy recovery)

Events:
- how should i respond still fails (chain). Check and validate
- When no event detected, generate a special log in debug folder if 'debug' bool is enabled: gent.py:292: [Event] EventDecision(matched_key=None, matched_key_step=None, pick_option=1, clicked_box=(182.39614868164062, 404.23193359375, 563.8184204101562, 458.83447265625), debug={'current_energy': 64, 'max_energy_cap': 100, 'chain_step_hint': None, 'num_choices': 2, 'has_event_card': False, 'ocr_title': '', 'ocr_description': ''}). 

## 0.5

### 0.5.0

Scenario:
- Aoharu Hai

Bat and executable:
- bat is failing
- Executable in release

Skill Buying:
- @EO1: List what skills the bot should prioritize and any that isn't in the selection it will randomally get in the list of skills to automatically pick: like if for the 1st part I know I need a certain uma stamina skill to win, then i would 9/10 times get it first. Add auto buy best option based on running style (with a premade priority list)

Bot Strategy / Policy:
- configurable scoring system for rainbows, explosion, combos
"""@EO1:
I also like to add one other idea, maybe like a prioritize support card you want so like kitasan or maybe Tazuna since I am not sure how pals are intergrated in the script

@Undertaker-86 Issue at Github:
Each card also has a different "rainbow bonus". For instance, the Manhattan Cafe STAM card has 1.2 Friendship multiplier, while Super Creek STAM has 1.375, so Super Creek should nudge the bot to click it more than Manhattan Cafe.
"""
- Put parameter in web ui, to decide when is 'weak' turn based on SV or others configs. """Weak turn classifications is used to decide if go to race, rest or recreation instead of training"""
- Change text to: Allow Racing when 'weak turn'
- @EpharGy: Director / Riko Kashimoto custom configs: option to add more and more weight to the Director with the aim to be green by 2nd Skill  increase check.
- Slight WIT nerf on weak turns (prevent over-weighting).
- put rainbow in hint icon or something like that it is not clear what it is right now
- after two failed retried, change style position to front

Team trials:
- handle 'story unlocked'  (press close button), before shop. And "New High score" message (test on monday)
- infinite loop when nothing to do in team trials but in go button check log 'log_team_trials_0.5.0.txt'
- improve team trials the 6 clicks, check if we are in that screen and do as much or as less clicks as needed instead of precomputing

Shop:
- Error loop in shop when nothing to buy, partial state, check on debug 'log_shop_0.5.0.txt'


## 0.6

### 0.6.0

General:
- Connection error handler (“A connection error occurred”): detect dialog with **white** and **green** buttons; handle “Title Screen” and “Retry”.

Bot Strategy / Policy:
- Better turn number prediction (11 or 1 for example, fails)
- Final Season: consider turn number on strategy and configuration; avoid Rest on last turn but allow earlier.
- optimization formula as recommended in a paper shared on discord
- For fans goals, we can wait a little more,  like winning maiden, we don't need to take it immediattly we can wait for weak turn add  configuration for this

QoL:
- Adapt Triple Tiara, Crown, and Senior preconfigs for race scheduler
- improvement: show data about support cards: which skills they have, and more, also for trainees. Like gametora

Coach (assistant / helper instead of Auto):
- @Rocostre
"""
As I was experimenting with it, I thought it would be great if, in a future update, you could experiment with an AI coach or something similar. This could involve adding an overlay to the game that provides guidance based on the current preset and its own calculations. Instead of relying solely on an automated bot, it could also offer an option for an overlay assistant to suggest actions.
LLM?
"""


## 0.7

### 0.7.0

General:
- More human like behavior

Bot Strategy:
- Fast mode: like human pre check rainbow buttons / hints, to decide if keep watching options or not. For example if rainbows in 2  tiles then we need to investigate, otherwise we can do a shortcut
- Fans handling for “director training” decisions or similar events.

End2End navigator play:
- Github Issue

