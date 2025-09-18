# Features / TODO
- Github action to autogenerate releases
- Github action to autogenerate release with GPU compilation
- Handle 'a connection error ocurred'. Buttons are white and green: title screen, retry
- Dynamic risk: if 2.5 in SV, allow up to 1.25 of the risk. if > 3, allow  up to 1.5. if > 4 allow up to 2
- Suggestion from Community: "Have a toggle for allowing scheduled races to be skipped if training has 2+ rainbows. And also managing this to avoid 3 races in a row or racing on 0 energy."
- Toggle config for prioritize director friendship training before special dates
- Only train in director if it is in top 3 priority stats
- Function to secure 600 minimum in case stats are '-1'
- if hint is important not prioritize untrained stat unless there is no hint
- Annotate new low confidence images in Label-Studio and retrain a robust model.
- improve stats number recognition it is predicting wrong and when ok is avoiding to update because of big jump
- In racing, reduce the amount of time program is sleeping, and instead add retries to text button recognition.
- Claw machine adjust the release time of the button depending on the turn (turn 3 the claw is way faster than turn 1)
- Add FASTER MODE (greedy decisions like: If you found a SV of 2.5 just take it, don't look into other training buttons)
- implement inmediate stop, right now it waits for the routine to end
- the wait for close button takes too much
- remove one skip check, reduce the close button check, (we have two extra skips, use less time to check)
- Track bought skills to avoid going to buy, improve the speed in buying skills
- FASTER MODE: when low energy but not too low to do immediate est, check for with great value first (because other options will have at least +40% failure so don't waste time looking into them)
- take into account 'left turns' even considering scheduled race before taking decision specially before summer
- improve OCR text cleaning
- fuzzy date match is not good enough, add unit testing there to support weird ocr results
- failure ocr fails sometimes in certain screen sizes, add a test to debug that logic and others... Prepare some good test suites and automate pytest validation
- test initial dates y0 to y1, and y3 to y4 big jumps
- is resting in last turn, that doesn't have value. force a training
- nerf the director friendship training going part if only no much better option
- Reduce skill buy box size click
- Improve region to only title in skill buying for better matching and faster response
- goldship training restriction coverage
- when scheduled previous race, sometimes date doesn't change so it thinks we are still in previous day and tries to race, but we already raced
- if energy <=35 then only check wit for good value... in greedy mode
- Handle already capped stats
- todo in failure to avoid errors, check colors clamp values check previous failures excep with they should be very similar, even use only the spped failure as reference
- add constraint, if turns > 4 and summer, no run
- implement advanced anti -> anti-cheating based on this deep research:
https://chatgpt.com/share/68cb64a9-2720-800f-8197-9b22547a3e9f
- recognice digits faster and accurate with yolo + single digit recognicer (resnet20)
- SIM phone notification control, click in a possible button there
- drawio algorithm update and implement pending stuff
- not rest directly if in summer is always + 40, but we can get 50 or 70 in normal, also is better to train there
- high confidence and multi overlap control, it found more than 6 rainbows
- If stat is -1 but others has something, use the 'avg' of them, at least to address the distribution stat, but set a flag like 'artificial' so a real read overwrites this
- use max refresh -> if not turn to refresh stat, check if there is a '-1' stat and recalculate
- stats not well recognized on small screen, phone
- auto try again but considering maximum attemps
- on consecutive race, act smartly to train or just continue
- train for get fans ( full g1 search smart)
- jitter is going to outside when buying, or because of 'inercy' button move a little up
- left-handed not recognized when buying
- set custom hin is important value, by default is x2 instead of true or similar, this should be configurable
- multiple clicks in safe zone to skip normal trainee events
- Reduce bluestack crop

# Bugs
- bug when view result active probability is 0.899 it is not clear if we clicked view results or not, probably it failed, add more logs in mobile it is confusing 'next' with 'race' or too much lag when waiting for view results 'white screen' and missclassifying a view button active
issues in slow internet specially in race
- Stats are not recognized in certain screen sizes

