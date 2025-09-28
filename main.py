# main.py
from __future__ import annotations

import threading
import time
import keyboard
import uvicorn

from core.utils.logger import logger_uma, setup_uma_logging
from core.settings import Settings
from core.agent import Player

from server.main import app
from server.utils import load_config, ensure_config_exists

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


def make_ocr_yolo_from_settings(ctrl: IController) -> tuple[OCRInterface, IDetector]:
    """Build fresh OCR and YOLO engines based on current Settings."""
    if Settings.USE_FAST_OCR:
        det_name = "PP-OCRv5_mobile_det"
        rec_name = "en_PP-OCRv5_mobile_rec"
    else:
        det_name = "PP-OCRv5_server_det"
        rec_name = "en_PP-OCRv5_server_rec"

    if Settings.USE_EXTERNAL_PROCESSOR:
        logger_uma.info(f"[PERCEPTION] Using external processor at: {Settings.EXTERNAL_PROCESSOR_URL}")
        from core.perception.ocr.ocr_remote import RemoteOCREngine
        from core.perception.yolo.yolo_remote import RemoteYOLOEngine
        ocr = RemoteOCREngine(base_url=Settings.EXTERNAL_PROCESSOR_URL)
        yolo_engine = RemoteYOLOEngine(ctrl=ctrl, base_url=Settings.EXTERNAL_PROCESSOR_URL)
        return ocr, yolo_engine

    logger_uma.info("[PERCEPTION] Using internal processors")
    from core.perception.ocr.ocr_local import LocalOCREngine
    from core.perception.yolo.yolo_local import LocalYOLOEngine
    ocr = LocalOCREngine(
        text_detection_model_name=det_name,
        text_recognition_model_name=rec_name,
    )
    yolo_engine = LocalYOLOEngine(ctrl=ctrl)
    return ocr, yolo_engine


# ---------------------------
# Server
# ---------------------------
def boot_server():
    url = f"http://{Settings.HOST}:{Settings.PORT}"
    logger_uma.info(f"[SERVER] {url}")
    uvicorn.run(app, host=Settings.HOST, port=Settings.PORT, log_level="warning")


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
                miss = "Steam" if mode == "steam" else ("BlueStacks" if mode == "bluestack" else "SCRCPY")
                logger_uma.error(f"[BOT] Could not find/focus the {miss} window (title='{Settings.resolve_window_title(mode)}').")
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
                select_style=preset_opts["select_style"],  # "end"|"late"|"pace"|"front"|None
                event_prefs=event_prefs,
            )

            def _runner():
                re_init = False
                try:
                    logger_uma.info("[BOT] Started.")
                    self.player.run(
                        delay=getattr(Settings, "MAIN_LOOP_DELAY", 0.4),
                        max_iterations=getattr(Settings, "MAX_ITERATIONS", None),
                    )
                except Exception as e:
                    if 'connection aborted' in str(e).lower():
                        logger_uma.info("Trying to recover from bot crash, connection to host was lost")
                        time.sleep(2)
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
# Hotkey loop (keyboard lib + polling fallback)
# ---------------------------
def hotkey_loop(state: BotState):
    # We’ll support both the configured hotkey and F2 as a backup
    configured = str(getattr(Settings, "HOTKEY", "F2")).upper()
    keys = sorted(set([configured, "F2"]))  # e.g. ["F1","F2"] (no duplicates)
    logger_uma.info(f"[HOTKEY] Press {', '.join(keys)} to start/stop the bot.")

    # Debounce across both hook & poll paths
    last_ts = 0.0

    def _debounced_toggle(source: str):
        nonlocal last_ts
        now = time.time()
        if now - last_ts < 0.35:
            logger_uma.debug(f"[HOTKEY] Debounced toggle from {source}.")
            return
        last_ts = now
        state.toggle(source=source)

    # Try to register hooks
    for k in keys:
        try:
            logger_uma.debug(f"[HOTKEY] Registering hook for {k}…")
            keyboard.add_hotkey(
                k,
                lambda key=k: _debounced_toggle(f"hook:{key}"),
                suppress=False,
                trigger_on_release=True,
            )
            logger_uma.info(f"[HOTKEY] Hook active for '{k}'.")
        except PermissionError as e:
            logger_uma.warning(
                f"[HOTKEY] PermissionError registering '{k}'. "
                f"On Windows you may need to run as Administrator. {e}"
            )
        except Exception as e:
            logger_uma.warning(f"[HOTKEY] Could not register '{k}': {e}")

    # Polling fallback (works even when hooks fail)
    logger_uma.debug("[HOTKEY] Polling fallback thread running…")
    try:
        while True:
            fired = False
            for k in keys:
                try:
                    if keyboard.is_pressed(k):
                        logger_uma.debug(f"[HOTKEY] Poll detected '{k}'.")
                        _debounced_toggle(f"poll:{k}")
                        fired = True
                        time.sleep(0.20)  # allow key release; prevents rapid repeats
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

    # Launch hotkey listener and server
    state = BotState()
    logger_uma.debug("[INIT] Spawning hotkey thread…")
    threading.Thread(target=hotkey_loop, args=(state,), daemon=True).start()

    try:
        boot_server()  # blocking
    except KeyboardInterrupt:
        pass
    finally:
        logger_uma.debug("[SHUTDOWN] Stopping bot and joining thread…")
        state.stop()
        if state.thread:
            state.thread.join(timeout=2.0)
        logger_uma.info("[SHUTDOWN] Bye.")
