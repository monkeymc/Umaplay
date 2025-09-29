# UMA MUSUME (UmaPlay) – Backlog (organized)

This organizes the mixed notes into a clear, actionable backlog. Items are grouped by workstream and priority. “Later” holds non-urgent ideas. A final section captures non-UMA (“Meta Manager”) items so they don’t pollute the UMA queue.

================================================================================
NEXT WORK (prioritized)

P0 — Must do next
-----------------
Vision/OCR & Models
- Label low-confidence frames in Label Studio and retrain a more robust detector; raise acceptance thresholds where safe.
- “Hint” robustness: reduce misses (tune ROI, add ensemble check, raise min conf with a small hysteresis).

Training Strategy
- Configurable “Hint importance” as a **multiplier** (default x2). Per-preset; supports “disable special racing fallback when SV<=1” flag.
- If an option contains a skill hint: pick it only if the skill hasn’t been bought; otherwise rotate to next best option.
- Add control knobs in Web UI: “maximum critical turn”, and “% distribution for stats” (used by fallback/stat balancing).

Racing & Schedule
- Connection error handler (“A connection error occurred”): detect dialog with **white** and **green** buttons; handle “Title Screen” and “Retry”.
- Lookup toggle: allow skipping **scheduled race** if training has **2+ rainbows**; avoid **3 races in a row** and racing at **0 energy**.

Skills Buying
- Prevent over-opening the Skill shop in Final Season; throttle and tighten triggers.

UI / UX
- Ensure “Thanks for reporting” messaging for BlueStacks users.
- Web UI: show version; add “Force update” confirmation; persist preset-specific event setups (no cross-preset bleed).

Debugging, Telemetry & Quality
- Better logs for “no match” / errors when Debug Mode is on.
- Instruction banner: “Restart after updating.”

P1 — Should follow P0
---------------------
Training Strategy
- When no good option (SV ≤ 1), **race for skill points** (toggle to disable: fallback to highest SV).
- Slight WIT nerf on weak turns (prevent over-weighting).

Vision/OCR & Models
- Accept YOLO `tag` in endpoint to organize samples.

Integrations & Platforms
- Scrcpy “drag” bug: fix gesture handling.
- Primary screen limitation: detect and warn or add fallback.

UI / UX
- End-of-career: if nothing was bought, ensure it goes **Back** correctly.

Data / Update / Ops
- “Thanks to GameTora” acknowledgement somewhere appropriate.

Check phone logs

================================================================================
LATER (nice-to-have / backlog)
------------------------------
Mobile / UI
- On mobile, avoid tapping “View result” too quickly (misclassifies as inactive).
- Web UI perf: investigate skills.json / races.json bottlenecks.
- Reduce BlueStacks crop.

Vision/OCR
- Faster digits: YOLO + single-digit recognizer (ResNet-20) for stat/date.
- Template matching for “turns left = 1”.

Training Strategy
- Ensure ≥600 in top-3 stats starting ~4 months before Final Season when SV>0 (and Ura finals ok with SV=0).
- Early stop at scrolling skill list at endgame when all desired 3 hints bought (fix case where first isn’t bought).
- “Check first” at lobby: pre-turn heuristics before going to infirmaty, rest, etc. Pre lookup
- Failure risk guardrails: clamp color read values; compare against prior failures; optionally use **Speed** failure as reference.
- Final Season: consider turn number; avoid Rest on last turn but allow earlier; better plan to exploit Summer training (Rest may be worse than training).

Racing
- Prioritize **G1** and **fans**: smart search to train for fans when needed.
- Reactivity: race handling is slow — reduce latencies.

Skills Buying
- Speed on mobile; improve left-handed OCR; shrink click box to avoid inertia misses.

Date / Timeline
- Fuzzy date matching; handle y0→y1 and y3→y4 jumps.
- After a scheduled race, date sometimes doesn’t advance; don’t try to race again.

Control & Safety
- Implement **immediate stop** (do not wait for routine end).
- Avoid “Rest” directly in Summer if +40; sometimes +50/+70 normal is better; create smarter summer strategy.

Housekeeping
- Early stop mode not working when “all bought 3” edge case; fix.
- YOLO endpoint `accept tag` (for dataset org).
- SIM phone notification: click a plausible button if shown.
- Fans handling for “director training” decisions.

Integrations & Platforms
- Gold Ship training restriction coverage.

- “Recreation special handling” (2 options, tazuna for example) — document behavior.

================================================================================
IMPLEMENTED — PENDING VALIDATION
--------------------------------
Training Policy
- Only train in Director if it is in top-3 priority stats; lower its priority below SV≥2; respect G1 priority.
- Dynamic risk: 
  - SV≥2.5 → allow risk up to 1.25×; 
  - SV>3 → up to 1.5×; 
  - SV>4 → up to 2×.
- Fast Mode:
  - Greedy: if SV≥2.5 found, take it — skip scanning others.
  - Low energy: check the “great value first” path (others likely ≥40% fail).

Final Season
- Prevent Rest on the very last turn → force a training.
- Avoid trying to race in wrong contexts.

Training Check
- High-confidence + multi-overlap control; handled case with >6 rainbows.

Stats
- If any stat = -1 while others valid, fill with average and mark as “artificial” so real reads overwrite.
- Max-refresh behavior: if not a refresh turn but any stat is -1, force a stat read.

Skills
- Mobile speed improvements.
- OCR region/fuzzy accuracy; left-handed recognition when buying.
- Smaller click box on the confirm button to avoid inertia misclick.

Date Processing
- Fuzzy date match; handle large year jumps.
- Fix: after a scheduled race the date may not change; avoid double racing.

Race
- Make handler reactive (initial pass done).

Settings Bridge
- Wire WebUI “Accept consecutive race” to program setting.

- Stats corrections: accept large downward “corrections” after OCR spikes (post-spike suspect window + persist/median gate). (Implementation aligned with recent `_update_stats` changes.)

- BlueStacks: scrolling solved 
- Connect Web UI “Accept consecutive race” to program setting.

- Normalize extreme stat reads (e.g., 931 → clamp/median replace); continue using “artificial” average fill only until a real read arrives.

Event Engine
- Event chooser UI: surface options and default to option #1 if no preference is stored; persist per event/preset.
- Trainee events override: when a character has a specific event with same (name, step), it replaces the general one (no duplicates).
- Only search/use events for the **selected** support cards, trainee, and scenario (smaller, faster index).