# main.py
import threading
import time
import keyboard
import uvicorn

from core.controllers.android import ScrcpyController
from core.controllers.base import IController
from core.controllers.steam import SteamController
from core.perception.ocr import OCREngine
from core.settings import Settings
from core.utils.logger import logger_uma, setup_uma_logging
from server.main import app
from core.agent import Player


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

    def start(self, ctrl: IController, ocr: OCREngine):
        with self._lock:
            if self.running:
                logger_uma.info("[BOT] Already running.")
                return

            logger_uma.debug("[BOT] start(): focusing window…")
            if not ctrl.focus():
                logger_uma.error("[BOT] Could not find/focus the scrcpy window.")
                return

            setup_uma_logging(debug=Settings.DEBUG)

            self.player = Player(
                ctrl=ctrl,
                ocr=ocr,
                interval_stats_refresh=4,
                minimum_skill_pts=800,
                prioritize_g1=False,
                auto_rest_minimum=26,
                plan_races = {
                    "Y1-12-1": "Asahi Hai Futurity Stakes",
                    "Y2-05-1": "NHK Mile Cup",
                    "Y2-05-2": "Japanese Oaks",
                    # "Y2-06-1": "Japanese Oaks",
                    # "Y2-06-2": "Queen Elizabeth II Cup",
                    "Y3-05-1": "Osaka Hai",
                    "Y3-11-1": "Victoria Mile",
                    # "Y3-06-2": "Takarazuka Kinen",
                    "Y3-11-2": "Japan Cup",
                },
                skill_list=[
                    "Concentration",
                    "Focus",
                    "Professor of Curvature",
                    "Corner Adept",
                    "Swinging Maestro",
                    "Corner Recovery",
                    "Corner Acceleration",
                    "Straightaway Recovery",
                    "Homestretch Haste",
                    "Straightaway Acceleration",
                    "Firm Conditions",
                    "Pace Chaser Corners",
                    "Pace Chaser Straightaways",
                    "Pace Chaser Savvy",
                    "Slipstream",
                    "Mile Corners",
                    "Left-Handed",
                    "Concentration",
                    "Early Lead",
                    "Final Push",
                    "Fast-Paced",
                    "Updrafters"
                ],
                select_style=None  # front
            )
            # SKILLs Pace
            
            def _runner():
                try:
                    logger_uma.info("[BOT] Started.")
                    self.player.run(
                        delay=getattr(Settings, "MAIN_LOOP_DELAY", 0.4),
                        max_iterations=getattr(Settings, "MAX_ITERATIONS", None),
                    )
                except Exception as e:
                    logger_uma.exception("[BOT] Crash: %s", e)
                finally:
                    with self._lock:
                        self.running = False
                        logger_uma.info("[BOT] Stopped.")

            self.thread = threading.Thread(target=_runner, daemon=True)
            self.running = True
            logger_uma.debug("[BOT] Launching agent thread…")
            self.thread.start()

    def stop(self):
        with self._lock:
            if not self.running or not self.player:
                logger_uma.info("[BOT] Not running.")
                return
            logger_uma.info("[BOT] Stopping… (signal loop to exit)")
            self.player.is_running = False

    def toggle(self, ctrl: IController, ocr: OCREngine, source: str = "hotkey"):
        logger_uma.debug(f"[BOT] toggle() called from {source}. running={self.running}")
        if self.running:
            self.stop()
        else:
            self.start(ctrl, ocr)


# ---------------------------
# Hotkey loop (keyboard lib + polling fallback)
# ---------------------------
def hotkey_loop(state: BotState, ctrl: IController, ocr: OCREngine):
    # We’ll support both the configured hotkey and F4 as a backup
    configured = str(getattr(Settings, "HOTKEY", "F1")).upper()
    keys = sorted(set([configured, "F4"]))  # e.g. ["F1","F4"] (no duplicates)
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
        state.toggle(ctrl, ocr, source=source)

    # Try to register hooks
    handlers = []
    for k in keys:
        try:
            logger_uma.debug(f"[HOTKEY] Registering hook for {k}…")
            h = keyboard.add_hotkey(k, lambda key=k: _debounced_toggle(f"hook:{key}"),
                                    suppress=False, trigger_on_release=True)
            handlers.append(h)
            logger_uma.info(f"[HOTKEY] Hook active for '{k}'.")
        except PermissionError as e:
            logger_uma.warning(f"[HOTKEY] PermissionError registering '{k}'. "
                               f"On Windows you may need to run as Administrator. {e}")
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
                        # small sleep to allow key release; prevents rapid repeats
                        time.sleep(0.20)
                except Exception as e:
                    # keyboard may raise if device focus changes—just continue
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
    setup_uma_logging(debug=Settings.DEBUG)

    # Controller + OCR singletons
    
    window_title = "23117RA68G"  # change by your own windows title in SCRCPY
    # ctrl = ScrcpyController(window_title)
    ctrl = SteamController("Umamusume")

    if Settings.USE_FAST_OCR:
        ocr = OCREngine(
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name="en_PP-OCRv5_mobile_rec",
        )
    else:
        ocr = OCREngine(
            text_detection_model_name="PP-OCRv5_server_det",
            text_recognition_model_name="en_PP-OCRv5_server_rec",
        )

    state = BotState()

    logger_uma.info(f"[INIT] Using scrcpy window title: '{window_title}'")
    # Launch hotkey listener and server
    logger_uma.debug("[INIT] Spawning hotkey thread…")
    threading.Thread(target=hotkey_loop, args=(state, ctrl, ocr), daemon=True).start()

    try:
        boot_server()
    except KeyboardInterrupt:
        pass
    finally:
        logger_uma.debug("[SHUTDOWN] Stopping bot and joining thread…")
        state.stop()
        if state.thread:
            state.thread.join(timeout=2.0)
        logger_uma.info("[SHUTDOWN] Bye.")
