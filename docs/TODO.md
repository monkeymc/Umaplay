# Features / TODO
## Priority
- Annotate new low confidence images in Label-Studio and retrain a robust model. Increase thresholds
- hint, is not always detected make it more robuts
- Set custom hint is important value if set to true, by default is x2 instead of true or similar, this should be configurable
- Event chooser option (and by default select the first one)
- Handle 'a connection error ocurred'. Buttons are white and green: title screen, retry
- Lookup feature:
	- Suggestion from Community: "Have a toggle for allowing scheduled races to be skipped if training has 2+ rainbows. And also managing this to avoid 3 races in a row or racing on 0 energy."
	- For infirmary, check if there is not a crazy training option, if not, return to infirmary

## Later
-  mobile still avoid selecting view result quickly and missclassifies view button as inactive
- TODO: improve when stat is higher, hold but not apply, follow an armonic linear flow than 2k if val > 2000: 
- Secure the min 600 in top 3 stats from 4 months before finale season but checking if there is SV >0, also in ura finale but doesn't matter if SV == 0
- Decouple Hint stuff from general config to preset config
- FASTER MODE:
	- multiple clicks in safe zone to skip normal trainee events
- goldship training restriction coverage
- todo in failure to avoid errors, check colors clamp values check previous failures excep with they should be very similar, even use only the spped failure as reference
- Claw machine adjust the release time of the button depending on the turn (turn 3 the claw is way faster than turn 1)
- Final season take into account the turn, to not rest in the end but allow resting in the first turn
- Address low resolution: date recognition
- prioritize G1 x prioritize fans -> train for get fans ( full g1 search smart)
- web ui is inneficent something is taking too much possible related to skills.json and races.json
- Add testing to score algorithm sometimes it doesn't properly sum rainbows hints together
- Reduce bluestack crop
- implement inmediate stop, right now it waits for the routine to end
- not rest directly if in summer is always + 40, but we can get 50 or 70 in normal, also is better to train there. Create better strategy
- implement advanced anti -> anti-cheating based on this deep research:
https://chatgpt.com/share/68cb64a9-2720-800f-8197-9b22547a3e9f
- recognice digits faster and accurate with yolo + single digit recognicer (resnet20)
- Use template matching to recognize turns left = 1
- take into account 'left turns' even considering scheduled race before taking decision specially before summer
- SIM phone notification control, click in a possible button there
- Fans handling (for director training decisions)

# Implemented, pending validate
- Only train in director if it is in top 3 priority stats, also reduce its priority below the >= 2 SV and prioritize G1 config
- Dynamic risk: if 2.5 in SV, allow up to 1.25 of the risk. if > 3, allow  up to 1.5. if > 4 allow up to 2
- FAST_MODE:
	- greedy decisions like: If you found a SV of 2.5 just take it, don't look into other training buttons
	- when low energy but not too low to do immediate est, check for with great value first (because other options will have at least +40% failure so don't waste time looking into them)
	
- Final season features
	- is resting in last turn, that doesn't have value. force a training
	- is trying to race

- Training check
	- high confidence and multi overlap control, it found more than 6 rainbows
	
- Training policy:
	- Handle already capped stats
	- Function to secure 600 minimum in case stats are '-1'
	- if hint is important not prioritize untrained stat unless there is no hint

- STATS
	- If stat is -1 but others has something, use the 'avg' of them, at least to address the distribution stat, but set a flag like 'artificial' so a real read overwrites this
	- use max refresh -> if not turn to refresh stat, check if there is a '-1' stat and recalculate

- Skill buying
	- Speed on mobile
	- OCR region and fuzzy accuracy. left-handed not recognized when buying
	- Reduce skill buy box size click, somethins for the inertia is clicking wrong

- Date processing
	- fuzzy date match
	- test initial dates y0 to y1, and y3 to y4 big jumps
	- when scheduled previous race, sometimes date doesn't change so it thinks we are still in previous day and tries to race, but we already raced
	
- Race
	- It is slow, be reactive

- Connect WebUI settings with actual program:
	Settings.ACCEPT_CONSECUTIVE_RACE = True
 