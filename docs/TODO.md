# UMA MUSUME (UmaPlay) – Backlog (organized)

This organizes the mixed notes into a clear, actionable backlog. Items are grouped by workstream and priority. “Later” holds non-urgent ideas. 

================================================================================

## 0.4

### 0.4.0

#### Unity Cup Policy:
- Allowed / Disallowed stats for spirit burst.
- Priority for explosion will be handled by the same stat priority config. 
- Web UI, selector for first team opponent and the 'rest'
- Configurable scoring system for: rainbow combo, white spirit values (before senior / in seniour), white spirit combo 
- blue spirit will generate a 'spirit_burst' boolean. But value will be the same something similar to white spirit. Also configurable in score system
- Don't explode in overtrained stats (more than our 'stats caps' in our config)
- prioritize exploding remanent blue explosions in previous 4 turns before Senior November early (we get skill here) ->. In Last two turns (URA finale), just explode wherever they are if we found a burst.
- Prioritize spirit on junior and classic; if there's no white flames in any tile, date Riko if you have her or train wit. Reduce its score in Senior

#### Unity Cup polishment:
- it not officially finishing once the end screen is reached, it just hangs (and doesn't trigger the final skill buy sequence)
- scenario selector in web ui for events, should be forced to the particular active scenario
- Feedback from Rocostre: Ok when switching to unity cup all the presets are blank I mean … the page it’s blank like there’s nothing for me to put there for some reason …
- update web ui hint defaults for unity cup to 0.5 / 0.25

#### General UX:
- changing external processor takes too much time

#### README.md:
- Improve installation instructions
- update requirements.txt
- suggest just open terminal as admin in the worst case
- slice the readme to make easier to read
- Update images

#### QoL:
- @Rosetta:
"""
Speaking of presets, if it's not too hard could we please have a way of sorting them into tabs/groups or at least be able to change the order in which they are on the list? When you have a lot like I do having to keep pressing the arrows while looking through them all is quite the tedious task
"""


### 0.4.1


Weir error check thread, air grove: @

add a togle to 'prefer priority stats if are 0.75 less or equal' disabled by default

also look for 'alone' hints / spirits, we may have a support card below. If not recognized a support_card


@Rosetta:Final tip, only do optional races if:
Never do optional races just because it doesn't look like there's anything else good. Discourage this option in Unity cup web ui


+1 for wit (we want to avoid resting as much as possible), but don't explode blue here

General:
- Create discord roles

BUG:
Rosetta — 8:40

After the bot checks for skills after a hint, it doesn't seem to be able to detect any info on the screen and will always rest regardless of energy value

Claw Machine:
- @Rosetta: Re-check of the logic so it always Win. If first detected plushie is good enough and it is not at the border take it, if not do a full scan. Check the zips on discord.

we have 'silent' yolo detection errors. for example with support_bar, it has 0.31 so it was filtered out before our debug saver
add a check like 'if support type, then you must have support bar, otherwise try again with less confidence

Fast mode bugs:
- Solve

reprocess all events data and trainee data

Handle a new screen class 'Race Stale' to detect the 'advance / next' button and press it 


- @Rosetta:
For Tazuna I have stats > hints for energy overcap priority, but it will still reject dating if energy is high enough even though accepting provides stats and rejecting only a hint (I want energy overcap prevention for her third date)
"""
Author notes: I think this is a bug. This is a problem that should not be happening this way. So we need to investigate what's going on and what this person is trying to to do. This is regarding the energy cap prevention, well, the overflow of energy prevention that we are rotating the options here. But I think it's also related to not only to PALs, but this is also related to in general, because maybe we have this bug also for other support cards, not only for Tasu Nakashimoto or, well, PAL support. Maybe we have this for other ones.
"""

### 0.4.2

Events:
- how should i respond still fails (chain). Check and validate
- When no event detected, generate a special log in debug folder if 'debug' bool is enabled: gent.py:292: [Event] EventDecision(matched_key=None, matched_key_step=None, pick_option=1, clicked_box=(182.39614868164062, 404.23193359375, 563.8184204101562, 458.83447265625), debug={'current_energy': 64, 'max_energy_cap': 100, 'chain_step_hint': None, 'num_choices': 2, 'has_event_card': False, 'ocr_title': '', 'ocr_description': ''}). 

Bug:
- race.py 867 when getting the style_btns chosen, error of list index out of range


Roseta: Also I don't have a log for it but if it's on fast mode and finds a good training that's capped, it'll return NOOP before checking other trianings and keep looping like that 

Bot Strategy:
One more little idea I've just had - it would be cool if the settings "allow racing over low training" could be expanded into deciding what grades of races this is allowed to trigger with (eg. only G1s)
MagodyBoy — 17:20
and the minimum energy to trigger race, I think right now I check if we have >= 70% of energy

Quality Assurance:
- Color unit testing: detected as yellow the 'green' one "yellow: +0.00"



PhantomDice —> Thanks for supporting project


with f8 also detect the shop

@Unknown

 — 3/11/2025 1:00
Found another "bug" where it stops at Ura races
Stuff I used

thread of 'Unknown'

support_type is confusing pwr and PAL, better use a classiffier or another logic


### 0.4.3
optimize CNN predicts with ONNX runtime for CPU automatically


## 0.5

### 0.5.0

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


@Rocostre:
"""
test it in JP version to bring plugins and more:
came across this repository a while back while using the Japanese version, and it worked incredibly well — even to this day. I was wondering if you could take a look at the logic behind it and suggest any possible fixes or improvements on your current project. Not sure if this helps or if you're already familiar with it.

https://github.com/NateScarlet/auto-derby


for the pluggins themselves it looks like they are custom macros or logic that other users generated or contribuited for the project to run certain events or training for example there are specific pluggins for an uma training in an specific way to get specific results here is the directory in the repo https://github.com/NateScarlet/auto-derby/wiki/Plugins is all in jap so youll need to translate it.

and here are training results posted by other users that used specific pluggins during training https://github.com/NateScarlet/auto-derby/wiki/Nurturing-result
"""

@Rocostre:
fair enough... also if you can at some point you can add the bot to have an optional setting to auto purchase skills based on currect uma stats to compensate and for the current next race, if possible, for example even if you set up priotity skills to buy but when you are about to purchase skills you don have your desired skills bot will look for alternate skills that are availble that will help you on your next race.
im going to try it out with air grove and see what happens

### 0.5.1
vestovia — Yesterday at 7:37
hi! thank you for the umaplay bot, i understand you avoid emulators due to the inherent risk, but just wondering if adb support or support for other emulators is in the plans? im currently using mumuplayer for the 60fps+ as sometimes i play manually and i think it also might allow it to run in the background like uat? though i think i can use rdp for the meantime but it would be nice. thank you again!

0.5.2
support friend bar when overlapped by support_hint, make sure we don't confuse colors or classification
new library, try to handle autoinstall


Etsuke cures slacker


allow buying in unity cup race day, take skill pts some steps before to have something kind of updated?

adb
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


check that support bar is intersecting the support box, otherwise sometimes is not inside at all
## 0.7

### 0.7.0

General:
- More human like behavior

Bot Strategy:
- Fast mode: like human pre check rainbow buttons / hints, to decide if keep watching options or not. For example if rainbows in 2  tiles then we need to investigate, otherwise we can do a shortcut
- Fans handling for “director training” decisions or similar events.

End2End navigator play:
- Github Issue





## To validate

@Chat Ja
"""
sorry to dm. my english not good. i found problem on dev branch. could you increase margin top and decrease margin bot ? thank you !
"""

PhantomDice —> Thanks for supporting project


Unity cup:
- Model trained in heavier YOLO model

ADB support:
Thanks for Adding ADB support @C

Automatic scrapping for data
Thanks! @Only

#### General Strategy / Policy:
- Parameter to define 'weak turn':
"""
Author notes: So, when I say weak turns, I mean there are some turns where we usually prefer to skip, and that's why we are using the weak part to skip the turn. And we need to define in the web UI, for both URAfinel and UnityCube, a way to set up which value is considered a weak turn. For example, for UnityCube, it may be by default 1.75, and for URA, it could be 1 in general.
"""
- Speaking of minimum mood, if it's great you often see the bot recreate for the first 2 turns, is it possible to perhaps have a different minimum mood option for the junior year or if energy is full and a friendship can be raised do that instead?
"""
Author notes: We can have also for both scenarios, for all scenarios, a sharded option for a toggle that when clicked, it will show a different mood option that will be triggered only for junior year. So they can set the minimal mood, but that will be only for junior year.
"""
- Lookup toggle: allow skipping **scheduled race** if training has a minimum defined SV like **2.5+ SV if URA or 4 if Unity Cup**. This should be configurable in web ui
  “Check first” at lobby: pre-turn heuristics before going to infirmaty, rest, etc. Pre lookup
  "Check first" allowed for races individually set
"""
Author notes: We’re making a decision to enter the Training phase. Inside Training, we rely on an additional decision layer — essentially another flowchart — to determine what to do during that specific training turn.

This section explains how, in some cases, we might want to check for higher-priority actions before committing to a greedy choice like Training. For instance, going to the Infirmary might be important but not necessarily urgent.

I’d like to introduce a toggle in the Web UI that applies to all scenarios. When this toggle is enabled in a preset, the bot should evaluate some additional conditions before performing its usual greedy actions in the lobby. Usually, we prefer to define such behaviors within presets, as it allows better configurability.

Let’s go through some examples:

1. Infirmary

If the toggle is enabled, before going to the infirmary, we should first check whether the Training screen contains a high-value opportunity.
Specifically, if there’s a super high Support Value (SV) — say, ≥ 3.5 in Unity Cup or ≥ 2.5 in URA — then we should skip the infirmary this turn and train instead, planning to visit the infirmary on the next turn. This logic is straightforward.

2. Auto-Rest Minimum

For the auto-rest rule, however, the toggle doesn’t override anything.
Even if the toggle is active, if the player’s energy is below the auto-rest minimum, the bot should always rest, without any additional checks. This rule must remain absolute.

3. Summer Handling

Similarly, for summer proximity, the existing logic should remain unchanged.
If summer is two or fewer turns away and energy is low, the bot should focus on recovering energy so that it enters summer in good condition — this must be respected even when the toggle is enabled.

4. Goal Races (Critical Goals)

Things get more complex for races, particularly those related to critical goals.
If a mandatory goal race (like a G1, Maven, or fan milestone) is approaching, the bot must still respect the rule for maximum waiting turns before racing.

For example, if the maximum allowed wait time before a goal race is 8 turns, and we’re currently at turn 13, we shouldn’t immediately take the race when we first detect it. Instead, we wait until the number of turns remaining equals 8, or possibly –1 if OCR failed and we couldn’t read it correctly.

If the toggle is enabled, we can make this rule slightly more flexible:

Before racing, check whether there’s a very good Training opportunity.

If there is, we can take that training instead of racing immediately.

However, once the turns left reach ≤ 5, we must proceed to the race, regardless of the toggle.

This ensures the toggle won’t cause failed runs by endlessly delaying goal races just because of attractive training options.

5. Optional / Planned Races

For optional races (those not tied to mandatory goals), the logic differs.
Since these races aren’t required, we should allow users to mark specific planned races as tentative.

At the Web UI level, this would mean adding a per-race toggle in the scheduler.
If this toggle is on for a given race, the bot should, before racing, scan the training screen for good options:

If a valuable training tile is found, the bot should train instead of racing.

If not, it proceeds with the race as usual.

This gives users fine-grained control:

Races marked with the toggle ON are tentative, meaning “only race if no strong training options exist.”

Races with the toggle OFF are mandatory, meaning the bot must race regardless of available training options.

By combining these controls, we gain better configurability, reduce the number of failed or suboptimal runs, and make the decision-making process much more adaptive to each preset and scenario.

Summary:
The new toggle provides a “pre-check” layer before greedy decisions like Infirmary, Rest, or Race actions. It allows the system to momentarily consider higher-value training opportunities but still respects critical safeguards (energy minimums, summer proximity, and goal deadlines). The final behavior should balance flexibility with safety, ensuring the bot neither skips essential actions nor wastes high-value turns.
"""


#### PAL Policy:
- Capture in lobby stats 'Recreation PAL' for later trainig decisions. YOLO model can detect that
"""
Author notes:
In this model, we are capturing a special class just for this RecreationPawl and it's a pink little icon and we should store that in memories so we can use this in next steps. Even more, every time we have a pawl, we need to know in which chain we have this pawl because if this pawl can have 5 dates, 5 chains, and the first chain for example will regenerate some energy, the second one will generate some energy, there will be some special chain step that will not generate that particular energy and we need to keep that in memory and if we know that there is this RecreationPawl icon, we can press the RecreationPawl icon and a pop-up will be displayed and we can just capture the chain steps there. So we know how many chain steps we have and we can take some decisions for this.
"""


- Use dating with pal (if it give energy), as replacement of REST and RECREATION
"""
Author notes: This is literally something, like, I think it's the same as mentioned before, because we either in summer and summer or normal rune we can just have this facility of going to rest or recreation. In case of summer, those options are merged, so anyway. So I think we need to have this option in the web UI. So by default, no, sorry, we don't need this in web UI because this should be a default behavior. If we need energy and we have some events to be triggered from the PAL, we should go back and just take the recreation with the PAL.
"""

- @Rosetta: Tazuna blue was worth more, you want to get it to green ASAP to unlock her dates (there's a bonus if you do it in the junior year)
"""
Author notes: Regarding this requirement, I think I already worked on it. Probably it's done. But let's check that this is implemented in EURA and UnityCup. Basically, I think if the PAL either TASUNA or Super Kashimoto or a support card that contains inside a support PAL icon, this is not very effective. So maybe we want to use this just as a final fallback. But in general, if we have this TASUNA or Kashimoto, we should give more points to if they have the blue color. And I will say if they have blue color, let's add a score of 1.5. I think I already did that anyway. So we can go to green as fast as possible. Maybe we can do that logic for now and we can improve later.
"""

- Some options doesn't give energy, but move the event chain, handle that if 'weak turn'. If we don't know in which chain number we are, open the recreation / collect and go back
"""
Author notes: So, as you can see in the event catalog, some options for Tasuna or Super Kashimoto will not give us energy, will give us stats, so we need to be very careful if we detect a weak turn, but the event chain, let's say we are using a Pal that in its event, in the next event, let's say we are in the second chain right now, after we can collect that information, so let's say we are in the second chain, that means that the next date we will have with the Pal will be the third chain, but let's say for this particular Pal, they will not give us the energy in the third chain, so we need to be careful here because if we need energy and we decide to go back and go using the rest option from this Pal, we will have problems, definitely we will have some problems there because we will not be generating energy, but if we are going back with the reason of do it to, we need recreation, yeah, it doesn't matter if this next chain, this next event will not give us energy, it doesn't matter because we are going back just for the mood increasing or just for the stats, because this is another one, even if we don't need energy or mood increasing, we may detect a weak turn and we should prioritize going with Riko Kashimoto if we have enough energy available to be recovered, so we can move the event chain because our objective is to finalize the date as fast as possible, but only if we have a weak turn and we have some energy to restore, so only if it's worth to do that. Thank you.
"""


- On Weak turn, if energy is not full and recreation is there with a turn that give us energy, use the pal.
"""
Author notes: We are already collecting a weak turn value from YBY, and we should leverage that parameter, or at least make sure we are leveraging properly that. And on weak turn, in weak turn, not a strong turn, sometimes we are deciding in the policy, either in EURA or Unity Cup, we are deciding to go to rest. But if we previously captured that we have this PAL icon, that means that we can have dates, and we can trigger some chain events, and those chain events will be better than going to rest. So, if we have a weak turn, and we know that we need energy, or we need recreation, we can just go back and take the recreation, and take the support PAL recreation.
"""

- @Rosetta: Speaking of Tazuna, I'd like to see an option that when auto rest is supposed to trigger and mood is below minimum, recreation takes priority
"""
Author notes: Again, something similar as before, so we're using this AutoRest, I think the default value is 20%, so if we are triggering the AutoRest option, before just selecting the Rest option, let's check if we have the PAL available, and if we have that, then we should then we should just take the recreation, that would be better, as I told you before, so it's something similar as before, but this is just regarding the lobby policy, I think, that you can review in the policies documentation.
"""
