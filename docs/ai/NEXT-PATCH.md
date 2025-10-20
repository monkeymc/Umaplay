NEXT WORK (towards 0.3.0)

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
Skill buying
- Bug recognizing titles (75% of accuracy)
- Improve Control for double buying of single circle skills
