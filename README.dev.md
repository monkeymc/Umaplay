# Adding new Support cards / Trainees Events


## ChatGPT Helper
- https://chatgpt.com/g/g-68d00d901b5881919302a559ef96ed07-umamusume-events-horse

## Current Catalog data
-- datasets\in_game\events.json

## GameTora event data:
Go to this GPT I created with custom prompt: https://chatgpt.com/g/g-68d00d901b5881919302a559ef96ed07-umamusume-events-horse
Go to and select the character: https://gametora.com/umamusume/training-event-helper
Take usually 2 screenshots (up to Dance Lesson section), and put them in the GPT (Thinking extended mode recommended, may take 3 minutes to complete)
3.5. Argue with Chatgpt  and fight with it because ChatGPT is dumb (important)
Verify that ChatGPT didn't hallucinate on the json output (I usually open multiple chats to process multiple at the same time)
Copy-paste that new json at the end of: datasets\in_game\events.json
Set the best 'general' default preferences that could work for everybody in community. Specially accepting 'Slow metabolism' for that good +30 energy
Important: Download the image from details page (e.g. https://gametora.com/umamusume/characters/100102-special-week) and put in web\public\events\trainee with standard name like 'Special Week
(Summer)_profile.png' (name is really important to follow this kind of format
7.5. Repeat with all other character
I compile the catalog so it is ready for being used: At dev_play.ipynb I run:
from core.utils.event_processor import build_catalog
...
build_catalog()

I compile frontend with:
cd web
npm run build

Done, and do a run test if I have the character in one of my 2 accounts. Otherwise, the step 10 is to pray everything is ok

## Support cards
1. https://gametora.com/umamusume/training-event-helper
2. Select Cards
3. Take screen capture for each one and put in chatgpt helper

##  Build catalog
- Run the script to build catalog, it is in jupyter

## Last processed
- SR WIT Mejiro Ardan
- SSR SPD Sweep Tosho