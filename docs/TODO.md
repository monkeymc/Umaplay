# UMA MUSUME (UmaPlay) – Backlog (organized)

This organizes the mixed notes into a clear, actionable backlog. Items are grouped by workstream and priority. “Later” holds non-urgent ideas. 

================================================================================

## 0.4

### 0.4.0

General
- Add minimal testing
tag button pink (filter the race_after_next), we didn't have that before


Aoharu Hai (beta):
- Create Label Studio project for YOLO 'large' model, considerations:
"""
1. not director, but keep it, put kashimoto intead. She is special here, not like tazuna
kashimoto can act as new director (no support_type icon) or as our support card (then she will have the support_type pal icon). -> team joined. For URA we need to do this if they use Riko Kashimoto here

new classes:
-> Retrain Calendar with new images
1. Calendar below aoharu turns
2. hint special training (classifier for the color)
3. flame special training (classifier to check if 'explosion, normal / remaning energy)
4. banner race
5. clock
6. Inspiration button change by: 'button_golden' to be able to support the riko confrontation
"""


- Aoharu Strategy:
"""

- Add a priority stats for explosions (can be different than normal priority stats)
- first trials may be better to select second one, the rest the first one. In web ui we need to set the 'first' team oponnent selection, and then the rest.
- Rainbow score is configurable, with a button that says 'add rainbow combo' 
- priority explosion, but also 'disable' stat to explode in the same ui
- flexible risk now we need to be careful because we can easily get 5 6  7 etc, reuce and increase the requirements
- first race in unity cup should press 'watch main race' and a yellow button like inspiration appears. After that a concert appears. Handle a new screen class 'Race Stale' to detect the 'advance / next' button and press it 
- ability to disable explosion in certains stats, and also prioritize stats explosion so in case there are same scores we decide this in same ui
- now a weak turn may be a little up, to sleep preparing for better opportunity. May be 1.75 because two flames may be or not may be ok)
- "At team at last" will have options that will vary, so we need to check the OCR text to decide, by default the last one
- 1.5 in wit (if flame) may be better than 1.75 in guts (if in priority order wit is first before guts)
- mantain a counter, if explosion is not in expected stats to be exploded, don't explode and check if some flame is about to fill, keep counting to do the best planning algorithm
- don't explode in overtrained stats
- if it is the final season, just explode any blue ball, doesn't matter position (prefer wit)


"""

General Strategy / Policy:
- Parameter to define 'weak turn' / 'low 
- PAL training:
  - @Rosetta: Tazuna blue was worth more, you want to get it to green ASAP to unlock her dates (there's a bonus if you do it in the junior year)
  - Make Tazuna orange/max also configurable (Also Riko Kashimoto). +0.15 (orange, yellow, max) by default
  - Capture in lobby stats 'Recreation PAL' for later trainig decisions
    -> When energy needed, and tazuna available, prefer tazuna (keep the chain counting to not select one with no good energy recovery)

QoL:
- Show in toast if selected scenario is ura or Aoharu, too along to the preset name

Only

 — 9:09
this is what my script are able to parse right now just need to make constant of trainee shared event such as Special Events / After a Race manually and and use this data { "nyear": "in", "dance": [ "sp", "st" ] } to adjust New Year's Resolutions and Dance Lesson accordingly then we are done. you can check the progress here https://github.com/preampinbut/Umaplay. 
e.g.
https://gametora.com/umamusume/supports/30027-mejiro-palmer
https://gametora.com/umamusume/characters/105602-matikanefukukitaru


PhantomDice —> Thanks for supporting project

if race_after_next is disabled click pink?

Weir error check thread, air grove: @


on tutorial, press the second option, set the events for this cup


scikit-image==0.25.2 -> new library, try to handle autoinstall

### 0.4.1

add a togle to 'prefer priority stats if are 0.75 less or equal' disabled by default


annotated for 0.4.1, thanks for suggestions as always Rosetta

For Tazuna I have stats > hints for energy overcap priority, but it will still reject dating if energy is high enough even though accepting provides stats and rejecting only a hint (I want energy overcap prevention for her third date)
Speaking of Tazuna, I'd like to see an option that when auto rest is supposed to trigger and mood is below minimum, recreation takes priority
Speaking of minimum mood, if it's great you often see the bot recreate for the first 2 turns, is it possible to perhaps have a different minimum mood option for the junior year or if energy is full and a friendship can be raised do that instead?


General:
- Create discord roles

### Bugfixes
- For initial stuff

General Strategy / Policy:
- Lookup toggle: allow skipping **scheduled race** if training has **2+ rainbows**
  “Check first” at lobby: pre-turn heuristics before going to infirmaty, rest, etc. Pre lookup
  "Check first" allowed for races individually set

Claw Machine:
- @Rosetta: Re-check of the logic so it always Win. If first detected plushie is good enough and it is not at the border take it, if not do a full scan. Check the zips on discord.

### 0.4.2

Events:
- how should i respond still fails (chain). Check and validate
- When no event detected, generate a special log in debug folder if 'debug' bool is enabled: gent.py:292: [Event] EventDecision(matched_key=None, matched_key_step=None, pick_option=1, clicked_box=(182.39614868164062, 404.23193359375, 563.8184204101562, 458.83447265625), debug={'current_energy': 64, 'max_energy_cap': 100, 'chain_step_hint': None, 'num_choices': 2, 'has_event_card': False, 'ocr_title': '', 'ocr_description': ''}). 

Bug:
- race.py 867 when getting the style_btns chosen, error of list index out of range

Bot Strategy:
One more little idea I've just had - it would be cool if the settings "allow racing over low training" could be expanded into deciding what grades of races this is allowed to trigger with (eg. only G1s)
MagodyBoy — 17:20
and the minimum energy to trigger race, I think right now I check if we have >= 70% of energy

Quality Assurance:
- Color unit testing: detected as yellow the 'green' one "yellow: +0.00"



PhantomDice —> Thanks for supporting project

## 0.5

### 0.5.0

Scenario:
- Aoharu Hai stabilization

Bat and executable:
- bat is failing
- Executable in release

Team trial
- Prioritize the ones with 'With every win' (gift)

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


- transparent may be happening after pressing 'back' in training
- fix data per trainee, (extra training and others, otherwise fit doesn't work)

Template Matching:
- for 'scenario' how does template matching works? is it used? or only text?

- race scheduler improve the patience when no stars found or similar views. Speed up.
- doc the new data augmentation including data steam checker. We need to keep that in sync with traineed, a way to check if there is consistency or if we have more information or less information in particular areas

@Unknown: do you think you could add a feature to add the minimum fans for the unique upgrade or is that already implemented?


Agent Nav: didn't recognized star pieces and bout shoes, retrain nav with more data

- UX: on hint required skills, only bring the selected on 'skills to buy' to have all in sync, instead of the full list. on required skills make sure standard distance cicle or double circle are the same?

- they added new choices for some events of oguri cap, grass wonders, mejiro mcqueens, mejiro ryan, agnes Tachyon, Sakura Bakushin -> automate the event scrapping

Bug:
- false positive, tried to look for this race on july 1:
10:03:03 INFO    agent.py:789: [planned_race] skip_guard=1 after failure desired='Takarazuka Kinen' key=Y3-06-2
10:03:03 INFO    agent.py:241: [planned_race] scheduled skip reset key=Y3-06-2 cooldown=2
10:03:04 DEBUG   lobby.py:796: [date] prev: DateInfo(raw='Senior Year Early Jun', year_code=3, month=6, half=2). Cand: DateInfo(raw='Senior Year Early Jul', year_code=3, month=7, half=1). accepted: DateInfo(raw='Senior Year Early Jul', year_code=3, month=7, half=1)
10:03:04 INFO    lobby.py:797: [date] monotonic: Y3-Jun-2 -> Y3-Jul-1

- for trainee matcher, train a classifier, for now keep template matching. With label studio train the classifier
- 'pre-process' based on the preset, and use the preprocess to speed up the progress

## 0.6

### 0.6.0

General:
- Connection error handler (“A connection error occurred”): detect dialog with **white** and **green** buttons; handle “Title Screen” and “Retry”.
- classifier transparent or not? handle transparents, only on main parts like screen detector (lobby)? or simple do multiple clicks when selecting  option in lobby to avoid pressing transparent. WAIT in back and after training

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


Bot Strategy:
- Rest and recreation during Summer Camp now cures bad conditions
- Resting now has a chance to cure the Night owl and skit outbreak
- You can cure slow metabolism by doing some training


## 0.7

### 0.7.0

General:
- More human like behavior

Bot Strategy:
- Fast mode: like human pre check rainbow buttons / hints, to decide if keep watching options or not. For example if rainbows in 2  tiles then we need to investigate, otherwise we can do a shortcut
- Fans handling for “director training” decisions or similar events.

End2End navigator play:
- Github Issue



