---
status: in_progress
updated: 2025-11-06T19:02:00-05:00
---

# PROGRESS — Refactoring Second Scenario Support

## Context & Goal
Enable smooth switching between multiple UmaMusume training scenarios by separating scenario-specific logic and providing a robust F2 hotkey chooser with polished UX.

## Key Decisions
- Consolidated all Tkinter interactions onto a dedicated dispatcher thread to avoid cross-thread crashes.
- Replaced the legacy text prompt with a button-based, modal scenario chooser featuring optional icons and keyboard shortcuts.
- Updated preset overlay logic to read scenario-aware config branches and render toast notifications through the Tk dispatcher.
- Hotkey loop now runs on the main thread while the web server runs on a daemon thread to keep UI responsive and thread-safe.

## Files & Anchors in Play
- `core/ui/scenario_prompt.py` — lines 1-189 (scenario chooser dialog and cancellation handling)
- `core/utils/tkthread.py` — lines 1-88 (shared Tk dispatcher implementation)
- `core/utils/preset_overlay.py` — lines 1-116 (toast overlay rendered via dispatcher)
- `main.py` — lines 30-792 (hotkey loop restructuring, scenario selection flow, overlay fix)

## Work Completed in This Iteration
- Rebuilt the scenario prompt as a Tkinter Toplevel with buttons, images, focus management, and keyboard shortcuts.
- Added WM_DELETE handler, cancel button, and escape binding so closing the dialog aborts the bot start.
- Introduced a shared Tk dispatcher (`tkthread.py`) and integrated it with both the scenario prompt and preset overlay.
- Refactored `show_preset_overlay` to execute entirely on the Tk dispatcher and corrected preset lookup to use scenario-specific config paths.
- Moved hotkey execution to the main thread, funneled hook callbacks through a queue, and started the web server on a daemon thread.
- Added aggressive focus/grab logic so the scenario chooser surfaces above VS Code.

## Current Issue or Observation
- None.

## Next Step
- Verify scenario-specific automation flows (Unity Cup) and adjust remaining components to respect the new scenario-aware settings structure.
