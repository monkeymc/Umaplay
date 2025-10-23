# main.py
from __future__ import annotations

import threading
import time
import webbrowser
import keyboard
import uvicorn
import subprocess
import sys
from pathlib import Path
import shutil

from core.utils.logger import logger_uma, setup_uma_logging
from core.settings import Settings
from core.agent import Player
from core.agent_nav import AgentNav

from server.main import app
from server.utils import load_config, ensure_config_exists, ensure_nav_exists

# Controllers & perception interfaces
from core.controllers.base import IController
from core.perception.ocr.interface import OCRInterface
from core.perception.yolo.interface import IDetector
from core.controllers.steam import SteamController
from core.controllers.android import ScrcpyController
from core.utils.abort import request_abort, clear_abort
from core.utils.event_processor import UserPrefs

try:
    # Optional; if your Bluestacks controller is a separate class
    from core.controllers.bluestacks import BlueStacksController

    HAS_BLUESTACKS_CTRL = True
except Exception:
    BlueStacksController = None  # type: ignore
    HAS_BLUESTACKS_CTRL = False


# ---------------------------
# Helpers to instantiate runtimes from Settings
# ---------------------------
def make_controller_from_settings() -> IController:
    """Build a fresh controller based on current Settings.MODE + resolved window title."""
    mode = Settings.MODE.lower().strip()
    window_title = Settings.resolve_window_title(mode)

    if mode == "steam":
        logger_uma.info(f"[CTRL] Mode=steam, window_title='{window_title}'")
        return SteamController(window_title)
    elif mode == "bluestack":
        # Use dedicated controller if available, else ScrcpyController as a windowed generic fallback
        logger_uma.info(f"[CTRL] Mode=bluestack, window_title='{window_title}'")
        if HAS_BLUESTACKS_CTRL and BlueStacksController is not None:
            return BlueStacksController(window_title)  # type: ignore
        return ScrcpyController(window_title)
    else:
        # scrcpy (default branch)
        logger_uma.info(f"[CTRL] Mode=scrcpy, window_title='{window_title}'")
        return ScrcpyController(window_title)


def make_ocr_yolo_from_settings(
    ctrl: IController, weights: str | None = None
) -> tuple[OCRInterface, IDetector]:
    """Build fresh OCR and YOLO engines based on current Settings."""
    if Settings.USE_FAST_OCR:
        det_name = "PP-OCRv5_mobile_det"
        rec_name = "en_PP-OCRv5_mobile_rec"
    else:
        det_name = "PP-OCRv5_server_det"
        rec_name = "en_PP-OCRv5_server_rec"

    if Settings.USE_EXTERNAL_PROCESSOR:
        logger_uma.info(
            f"[PERCEPTION] Using external processor at: {Settings.EXTERNAL_PROCESSOR_URL}"
        )
        from core.perception.ocr.ocr_remote import RemoteOCREngine
        from core.perception.yolo.yolo_remote import RemoteYOLOEngine

        ocr = RemoteOCREngine(base_url=Settings.EXTERNAL_PROCESSOR_URL)
        if weights:
            yolo_engine = RemoteYOLOEngine(
                ctrl=ctrl, base_url=Settings.EXTERNAL_PROCESSOR_URL, weights=weights
            )
        else:
            yolo_engine = RemoteYOLOEngine(
                ctrl=ctrl, base_url=Settings.EXTERNAL_PROCESSOR_URL
            )
        return ocr, yolo_engine

    logger_uma.info("[PERCEPTION] Using internal processors")
    from core.perception.ocr.ocr_local import LocalOCREngine
    from core.perception.yolo.yolo_local import LocalYOLOEngine

    ocr = LocalOCREngine(
        text_detection_model_name=det_name,
        text_recognition_model_name=rec_name,
    )
    if weights:
        yolo_engine = LocalYOLOEngine(ctrl=ctrl, weights=weights)
    else:
        yolo_engine = LocalYOLOEngine(ctrl=ctrl)

    return ocr, yolo_engine


# ---------------------------
# Server
# ---------------------------
def boot_server():
    url = f"http://{Settings.HOST}:{Settings.PORT}"
    logger_uma.info(f"[SERVER] {url}")
    try:
        webbrowser.open(url, new=2)
    except Exception as exc:
        logger_uma.debug(f"[SERVER] Failed to open browser automatically: {exc}")
    uvicorn.run(app, host=Settings.HOST, port=Settings.PORT, log_level="warning")


# ---------------------------
# Cleanup helpers
# ---------------------------
def cleanup_debug_training_if_needed():
    debug_root = Settings.DEBUG_DIR
    if not debug_root.exists():
        return

    threshold_bytes = 250 * 1024 * 1024
    agent_dirs = [p for p in debug_root.iterdir() if p.is_dir()]

    for agent_dir in sorted(agent_dirs, key=lambda p: p.name.lower()):
        total_bytes = 0
        for path in agent_dir.rglob("*"):
            if path.is_file():
                try:
                    total_bytes += path.stat().st_size
                except OSError:
                    continue

        if total_bytes <= threshold_bytes:
            continue

        timestamp = time.strftime("%y%m%d_%H%M%S")
        set_name = f"{agent_dir.name}_low_{timestamp}"
        cmd = [
            sys.executable,
            "collect_data_training.py",
            "--src",
            str(debug_root),
            "--agent",
            agent_dir.name,
            "--set-name",
            set_name,
            "--percentile",
            "5",
            "--min-per-folder",
            "3",
            "--max-per-folder",
            "10",
            "--action",
            "move",
            "--exclude",
            "general",
            "agent_unknown_advance",
            "screen",
        ]

        size_mb = total_bytes / (1024 * 1024)
        logger_uma.info(
            f"[CLEANUP] debug/{agent_dir.name} size={size_mb:.1f} MB exceeds threshold. Running cleanup to {set_name}."
        )
        try:
            subprocess.run(cmd, check=True)
            for child in agent_dir.iterdir():
                if child.is_dir():
                    try:
                        shutil.rmtree(child)
                        logger_uma.info(f"[CLEANUP] Removed folder {child}")
                    except Exception as exc:
                        logger_uma.warning(
                            f"[CLEANUP] Failed to remove folder {child}: {exc}"
                        )
        except subprocess.CalledProcessError as exc:
            logger_uma.warning(
                f"[CLEANUP] Cleanup command exited with status {exc.returncode}: {exc}"
            )
        except Exception as exc:
            logger_uma.warning(f"[CLEANUP] Cleanup command failed: {exc}")


# ---------------------------
# Bot state & helpers
# ---------------------------
class BotState:
    def __init__(self):
        self.thread: threading.Thread | None = None
        self.player: Player | None = None
        self.running: bool = False
        self._lock = threading.Lock()

    def start(self):
        """
        Reload config.json -> Settings.apply_config -> build fresh controller + OCR/YOLO -> run Player.
        This guarantees we always reflect the latest UI changes at start time.
        """
        with self._lock:
            if self.running:
                logger_uma.info("[BOT] Already running.")
                return

            # 1) Re-hydrate Settings from the (possibly updated) config.json
            try:
                cfg = load_config()
            except Exception:
                cfg = {}
            Settings.apply_config(cfg or {})

            # 2) Configure logging using (possibly updated) Settings.DEBUG
            setup_uma_logging(debug=Settings.DEBUG)

            # 3) Build fresh controller & perception engines using the *current* settings
            ctrl = make_controller_from_settings()
            if not ctrl.focus():
                # Helpful mode-aware error
                mode = Settings.MODE.lower()
                miss = (
                    "Steam"
                    if mode == "steam"
                    else ("BlueStacks" if mode == "bluestack" else "SCRCPY")
                )
                logger_uma.error(
                    f"[BOT] Could not find/focus the {miss} window (title='{Settings.resolve_window_title(mode)}')."
                )
                return

            ocr, yolo_engine = make_ocr_yolo_from_settings(ctrl)

            # 4) Extract preset-specific runtime opts (skill_list / plan_races / select_style)
            preset_opts = Settings.extract_runtime_preset(cfg or {})

            # 5) Build event prefs from config (active preset). If malformed/missing,
            #    UserPrefs.from_config() returns safe defaults and EventFlow will still
            #    pick the top option if a pick is invalid at runtime.
            event_prefs = UserPrefs.from_config(cfg or {})

            # 6) Instantiate Player with runtime knobs from Settings + presets + event prefs
            self.player = Player(
                ctrl=ctrl,
                ocr=ocr,
                yolo_engine=yolo_engine,
                interval_stats_refresh=1,
                minimum_skill_pts=Settings.MINIMUM_SKILL_PTS,
                prioritize_g1=False,
                auto_rest_minimum=Settings.AUTO_REST_MINIMUM,
                plan_races=preset_opts["plan_races"],
                skill_list=preset_opts["skill_list"],
                select_style=preset_opts[
                    "select_style"
                ],  # "end"|"late"|"pace"|"front"|None
                event_prefs=event_prefs,
            )

            def _runner():
                re_init = False
                try:
                    logger_uma.info("[BOT] Started.")
                    # if not none
                    if self.player:
                        self.player.run(
                            delay=getattr(Settings, "MAIN_LOOP_DELAY", 0.4),
                            max_iterations=getattr(Settings, "MAX_ITERATIONS", None),
                        )
                except Exception as e:
                    if "connection aborted" in str(e).lower():
                        logger_uma.info(
                            "Trying to recover from bot crash, connection to host was lost"
                        )
                        time.sleep(2)
                        if self.player:
                            self.player.run(
                                delay=getattr(Settings, "MAIN_LOOP_DELAY", 0.4),
                                max_iterations=getattr(Settings, "MAX_ITERATIONS", None),
                            )
                    else:
                        logger_uma.exception("[BOT] Crash: %s", e)
                finally:
                    if not re_init:
                        with self._lock:
                            self.running = False
                            logger_uma.info("[BOT] Stopped.")

            self.thread = threading.Thread(target=_runner, daemon=True)
            self.running = True
            logger_uma.debug("[BOT] Launching agent thread…")
            clear_abort()  # ensure previous abort state is cleared
            self.thread.start()

    def stop(self):
        with self._lock:
            if not self.running or not self.player:
                logger_uma.info("[BOT] Not running.")
                return
            logger_uma.info("[BOT] Stopping… (signal loop to exit)")
            request_abort()
            self.player.is_running = False
            try:
                self.player.emergency_stop()
            except Exception:
                pass

    def toggle(self, source: str = "hotkey"):
        logger_uma.debug(f"[BOT] toggle() called from {source}. running={self.running}")
        if self.running:
            self.stop()
        else:
            self.start()


# ---------------------------
# AgentNav one-shot runner state
# ---------------------------
class NavState:
    def __init__(self):
        self.thread: threading.Thread | None = None
        self.agent: AgentNav | None = None
        self.running: bool = False
        self._lock = threading.Lock()
        self.current_action: str | None = None

    def start(self, action: str):
        with self._lock:
            if self.running:
                logger_uma.info(
                    f"[AgentNav] Already running (action={getattr(self.agent, 'action', '?')})."
                )
                return

            # Re-hydrate settings and logging similar to Player start
            try:
                cfg = load_config()
            except Exception:
                cfg = {}
            Settings.apply_config(cfg or {})
            setup_uma_logging(debug=Settings.DEBUG)

            ctrl = make_controller_from_settings()
            if not ctrl.focus():
                mode = Settings.MODE.lower()
                miss = (
                    "Steam"
                    if mode == "steam"
                    else ("BlueStacks" if mode == "bluestack" else "SCRCPY")
                )
                logger_uma.error(
                    f"[AgentNav] Could not find/focus the {miss} window (title='{Settings.resolve_window_title(mode)}')."
                )
                return

            # OCR from settings, YOLO engine for NAV specifically
            ocr, yolo_engine_nav = make_ocr_yolo_from_settings(
                ctrl, weights=Settings.YOLO_WEIGHTS_NAV
            )

            self.agent = AgentNav(ctrl, ocr, yolo_engine_nav, action=action)

            def _runner():
                try:
                    logger_uma.info(f"[AgentNav] Started (action={action}).")
                    if self.agent:
                        self.agent.run()
                except Exception as e:
                    logger_uma.exception("[AgentNav] Crash: %s", e)
                finally:
                    with self._lock:
                        self.running = False
                        self.current_action = None
                        logger_uma.info("[AgentNav] Stopped.")

            self.thread = threading.Thread(target=_runner, daemon=True)
            self.running = True
            self.current_action = action
            self.thread.start()

    def stop(self):
        with self._lock:
            if not self.running or not self.agent:
                logger_uma.info("[AgentNav] Not running.")
                return
            logger_uma.info(
                f"[AgentNav] Stopping current run (action={self.current_action})."
            )
            try:
                self.agent.stop()
            except Exception:
                pass
            # Fallback: set internal stop event if exposed
            try:
                evt = getattr(self.agent, "_stop_event", None)
                if evt is not None:
                    evt.set()
            except Exception:
                pass
            t = self.thread
            if t is not None:
                # Wait in small intervals so we can break early if stopped
                for _ in range(30):  # ~3s total
                    try:
                        t.join(timeout=0.1)
                    except Exception:
                        break
                    if not t.is_alive():
                        break
                if t.is_alive():
                    logger_uma.warning(
                        "[AgentNav] Worker thread is still alive after stop request."
                    )
            self.running = False
            self.thread = None
            self.agent = None
            self.current_action = None
            logger_uma.info("[AgentNav] Stop requested.")


# ---------------------------
# Hotkey loop (keyboard lib + polling fallback)
# ---------------------------
def hotkey_loop(bot_state: BotState, nav_state: NavState):
    # Support configured hotkey and F2 as backup for Player; F7/F8 for AgentNav
    configured = str(getattr(Settings, "HOTKEY", "F2")).upper()
    keys_bot = sorted(set([configured, "F2"]))
    keys_nav = ["F7", "F8", "F9"]
    logger_uma.info(f"[HOTKEY] Run bot in Scenario (e.g. URA, Unity Cup): press {', '.join(keys_bot)} to start/stop.")
    logger_uma.info("[HOTKEY] AgentNav: press F7=TeamTrials, F8=DailyRaces")
    logger_uma.info("[HOTKEY] AgentNav: press F9=Roulette/PrizeDerby.")

    # Track which keys successfully registered hooks (to skip in polling)
    hooked_keys = set()
    
    # Debounce across both hook & poll paths - INCREASED to prevent race condition
    # between hook (trigger_on_release) and polling (while key pressed)
    last_ts_toggle = 0.0
    last_ts_team = 0.0
    last_ts_daily = 0.0
    last_ts_roulette = 0.0

    def _debounced_toggle(source: str):
        nonlocal last_ts_toggle
        now = time.time()
        # Increased debounce from 0.35s to 0.8s to handle hook+poll race condition
        if now - last_ts_toggle < 0.8:
            logger_uma.debug(f"[HOTKEY] Debounced toggle from {source}.")
            return
        last_ts_toggle = now
        bot_state.toggle(source=source)

    def _debounced_team(source: str):
        nonlocal last_ts_team
        now = time.time()
        if now - last_ts_team < 0.8:
            logger_uma.debug(f"[HOTKEY] Debounced team-trials from {source}.")
            return
        last_ts_team = now
        if bot_state.running:
            logger_uma.warning(
                "[AgentNav] Cannot start while Player is running. Stop the Player first (F2)."
            )
            return
        # Toggle or switch
        if nav_state.running:
            if nav_state.current_action == "team_trials":
                nav_state.stop()
            else:
                nav_state.stop()
                nav_state.start(action="team_trials")
        else:
            nav_state.start(action="team_trials")

    def _debounced_daily(source: str):
        nonlocal last_ts_daily
        now = time.time()
        if now - last_ts_daily < 0.8:
            logger_uma.debug(f"[HOTKEY] Debounced daily-races from {source}.")
            return
        last_ts_daily = now
        if bot_state.running:
            logger_uma.warning(
                "[AgentNav] Cannot start while Player is running. Stop the Player first (F2)."
            )
            return
        # Toggle or switch
        if nav_state.running:
            if nav_state.current_action == "daily_races":
                nav_state.stop()
            else:
                nav_state.stop()
                nav_state.start(action="daily_races")
        else:
            nav_state.start(action="daily_races")

    def _debounced_roulette(source: str):
        nonlocal last_ts_roulette
        now = time.time()
        if now - last_ts_roulette < 0.8:
            logger_uma.debug(f"[HOTKEY] Debounced roulette from {source}.")
            return
        last_ts_roulette = now
        if bot_state.running:
            logger_uma.warning(
                "[AgentNav] Cannot start while Player is running. Stop the Player first (F2)."
            )
            return
        if nav_state.running:
            if nav_state.current_action == "roulette":
                nav_state.stop()
            else:
                nav_state.stop()
                nav_state.start(action="roulette")
        else:
            nav_state.start(action="roulette")

    # Try to register hooks
    for k in keys_bot:
        try:
            logger_uma.debug(f"[HOTKEY] Registering hook for {k}…")
            keyboard.add_hotkey(
                k,
                lambda key=k: _debounced_toggle(f"hook:{key}"),
                suppress=False,
                trigger_on_release=True,
            )
            hooked_keys.add(k)
            logger_uma.info(f"[HOTKEY] Hook active for '{k}'.")
        except PermissionError as e:
            logger_uma.warning(
                f"[HOTKEY] PermissionError registering '{k}'. On Windows you may need to run as Administrator. {e}"
            )
        except Exception as e:
            logger_uma.warning(f"[HOTKEY] Could not register '{k}': {e}")

    for k, fn in [("F7", _debounced_team), ("F8", _debounced_daily), ("F9", _debounced_roulette)]:
        try:
            logger_uma.debug(f"[HOTKEY] Registering hook for {k}…")
            keyboard.add_hotkey(
                k,
                lambda key=k, cb=fn: cb(f"hook:{key}"),
                suppress=False,
                trigger_on_release=True,
            )
            hooked_keys.add(k)
            logger_uma.info(f"[HOTKEY] Hook active for '{k}'.")
        except PermissionError as e:
            logger_uma.warning(
                f"[HOTKEY] PermissionError registering '{k}'. On Windows you may need to run as Administrator. {e}"
            )
        except Exception as e:
            logger_uma.warning(f"[HOTKEY] Could not register '{k}': {e}")

    # Polling fallback (works even when hooks fail)
    # With increased debounce (0.8s), both hook and poll can coexist safely
    if hooked_keys:
        logger_uma.debug(f"[HOTKEY] Hooks registered for: {hooked_keys}. Polling also active with 0.8s debounce to prevent race condition.")
    logger_uma.debug("[HOTKEY] Polling fallback thread running…")
    try:
        while True:
            fired = False
            for k in keys_bot:
                try:
                    if keyboard.is_pressed(k):
                        logger_uma.debug(f"[HOTKEY] Poll detected '{k}'.")
                        _debounced_toggle(f"poll:{k}")
                        fired = True
                        time.sleep(0.20)
                except Exception as e:
                    logger_uma.debug(f"[HOTKEY] Poll error on '{k}': {e}")
            # Nav keys
            for k, fn in [("F7", _debounced_team), ("F8", _debounced_daily), ("F9", _debounced_roulette)]:
                try:
                    if keyboard.is_pressed(k):
                        logger_uma.debug(f"[HOTKEY] Poll detected '{k}'.")
                        fn(f"poll:{k}")
                        fired = True
                        time.sleep(0.20)
                except Exception as e:
                    logger_uma.debug(f"[HOTKEY] Poll error on '{k}': {e}")
            if not fired:
                time.sleep(0.08)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            keyboard.unhook_all_hotkeys()
            logger_uma.debug("[HOTKEY] Unhooked all hotkeys.")
        except Exception:
            pass


# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    ensure_nav_exists()
    # Ensure config.json exists (seed from config.sample.json if needed)
    try:
        created = ensure_config_exists()
        if created:
            logger_uma.info("[SERVER] Created config.json from config.sample.json")
    except Exception as e:
        logger_uma.warning(f"[SERVER] Could not ensure config.json exists: {e}")

    # Load once for initial logging setup (will be reloaded again on each Start)
    try:
        cfg0 = load_config()
    except Exception:
        cfg0 = {}
    Settings.apply_config(cfg0 or {})
    setup_uma_logging(debug=Settings.DEBUG)

    try:
        cleanup_debug_training_if_needed()
    except Exception as e:
        logger_uma.warning(f"[SERVER] Could not cleanup debug training: {e}")

    # Launch hotkey listener and server
    state = BotState()
    nav_state = NavState()
    logger_uma.debug("[INIT] Spawning hotkey thread…")
    threading.Thread(target=hotkey_loop, args=(state, nav_state), daemon=True).start()

    try:
        boot_server()  # blocking
    except KeyboardInterrupt:
        pass
    finally:
        logger_uma.debug("[SHUTDOWN] Stopping bot and joining thread…")
        state.stop()
        if state.thread:
            state.thread.join(timeout=2.0)
        if nav_state.thread:
            nav_state.thread.join(timeout=2.0)
        logger_uma.info("[SHUTDOWN] Bye.")
