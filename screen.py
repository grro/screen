import os
import re
import subprocess
import logging
import time
from threading import Thread, RLock
from datetime import datetime, timedelta
from time import sleep

class Screen:
    def __init__(self, start_script: str = None, stop_script: str = None):
        self._listeners = set()
        self._lock = RLock()
        self._initialized = False

        self.start_script = start_script.strip() if start_script else None
        self.stop_script = stop_script.strip() if stop_script else None

        self.screen_on_target_state = False
        self.browser_active = False
        self.last_browser_attempt = datetime.now() - timedelta(seconds=60)
        self.last_hw_action = datetime.now()

        Thread(target=self._init_sequence, daemon=True).start()
        Thread(target=self._repair_loop, daemon=True).start()

    def _get_env(self):
        env = os.environ.copy()
        runtime_dir = "/run/user/1000"
        env["XDG_RUNTIME_DIR"] = runtime_dir

        try:
            sockets = [f for f in os.listdir(runtime_dir) if f.startswith("wayland-")]
            if sockets:
                # Neuesten Socket wählen (falls labwc neu gestartet wurde)
                sockets.sort(key=lambda x: os.path.getmtime(os.path.join(runtime_dir, x)), reverse=True)
                env["WAYLAND_DISPLAY"] = sockets[0]
        except Exception as e:
            logging.error(f"Kritischer Fehler bei Socket-Suche: {e}")

        return env

    @property
    def is_screen_on(self) -> bool:
        return self.screen_on_target_state

    def _is_screen_power_on(self) -> bool:
        try:
            res = subprocess.run(["wlr-randr"], env=self._get_env(), capture_output=True, text=True, timeout=5)
            match = re.search(r"HDMI-A-2.*?Enabled:\s+(yes|no)", res.stdout, re.DOTALL)
            if match:
                return match.group(1) == "yes"
        except Exception:
            pass
        return False

    def _is_browser_running(self) -> bool:
        try:
            return subprocess.run(["pgrep", "chromium"], capture_output=True).returncode == 0
        except Exception:
            return False

    def set_screen(self, turn_on: bool):
        self.activate() if turn_on else self.deactivate()

    def activate(self):
        self.screen_on_target_state = True
        if not self._initialized:
            return

        with self._lock:
            # 1. Browser-Check (Zuerst starten für Zero-OS Look)
            if not self._is_browser_running():
                self._start_browser_script()
                sleep(5)

                # 2. Hardware-Check (Korrekte Einrückung!)
            if not self._is_screen_power_on():
                self._set_power_on()
                self._notify_listeners()
            else:
                self._notify_listeners()

    def deactivate(self):
        self.screen_on_target_state = False
        if not self._initialized:
            logging.warning("Ignoriere deactivate(): System bootet noch.")
            return

        with self._lock:
            logging.info("Action: Screen OFF")
            self._set_power_off()
            self._stop_browser_script()
            self._notify_listeners()

    def _set_power_on(self) -> bool:
        output = "HDMI-A-2"
        env = self._get_env()
        self.last_hw_action = datetime.now() # Zeitstempel für Loop-Sperre

        logging.info(f"Hardware-Reset-Sequenz für {output} ({env.get('WAYLAND_DISPLAY')})...")

        # 1. Ressourcen-Refresh
        subprocess.run(["wlr-randr"], env=env, capture_output=True)
        # 2. Hard-Off
        subprocess.run(["wlr-randr", "--output", output, "--off"], env=env, capture_output=True)
        time.sleep(2)
        # 3. Weckruf
        subprocess.run(["wlr-randr", "--output", output, "--on"], env=env, capture_output=True)
        time.sleep(5)

        try:
            res = subprocess.run(
                ["wlr-randr", "--output", output, "--mode", "1280x800"],
                env=env, capture_output=True, text=True, timeout=10
            )
            if res.returncode == 0:
                logging.info(f"Hardware {output} erfolgreich gesetzt.")
                return True
        except Exception as e:
            logging.error(f"Modus-Timeout/Fehler: {e}")

        # Rettungsanker
        logging.warning("Erzwinge Auto-On Fallback...")
        subprocess.run(["wlr-randr", "--output", output, "--on"], env=env)
        return True

    def _set_power_off(self) -> bool:
        output = "HDMI-A-2"
        env = self._get_env()
        self.last_hw_action = datetime.now() # WICHTIG: Auch hier Sperre setzen!

        logging.info(f"Schalte Hardware {output} AUS.")
        res = subprocess.run(["wlr-randr", "--output", output, "--off"],
                             env=env, capture_output=True, text=True)
        return res.returncode == 0

    def _init_sequence(self):
        time.sleep(45)
        logging.info("Init: Setze Basis-Zustand...")
        self._initialized = True
        self.activate()
        time.sleep(5)
        logging.info("Init: System bereit, Repair-Loop aktiv.")

    def _start_browser_script(self):
        if self.start_script:
            logging.info(" Starting browser...")
            try:
                subprocess.Popen(["/bin/bash", self.start_script], env=self._get_env())
                self.browser_active = True
            except Exception as e:
                logging.error(f"Browser start error: {e}")

    def _stop_browser_script(self):
        if self.stop_script:
            logging.info(" Stopping browser...")
            try:
                subprocess.run(["/bin/bash", self.stop_script], env=self._get_env())
                self.browser_active = False
            except Exception as e:
                logging.error(f"Browser stop error: {e}")

    def add_listener(self, listener):
        self._listeners.add(listener)

    def _notify_listeners(self):
        [l() for l in self._listeners if callable(l)]

    def _repair_loop(self):
        while True:
            time.sleep(25)
            if not self._initialized:
                continue

            # Verhindert Repair während die Hardware noch schaltet (Anti-Racing)
            if datetime.now() < self.last_hw_action + timedelta(seconds=20):
                continue

            if self._repair_browser():
                sleep(5)

            self._repair_screen_power()

    def _repair_browser(self) -> bool:
        try:
            if self.screen_on_target_state and not self._is_browser_running():
                logging.warning("Repair: Browser tot. Neustart...")
                with self._lock:
                    self._start_browser_script()
                return True
        except Exception as e:
            logging.error(f"Fehler im Browser-Repair: {e}")
        return False

    def _repair_screen_power(self) -> bool:
        try:
            hw_is_on = self._is_screen_power_on()
            if hw_is_on != self.screen_on_target_state:
                logging.warning(f"Repair: HW-Abweichung! Soll: {self.screen_on_target_state}, Ist: {hw_is_on}")
                with self._lock:
                    if self.screen_on_target_state:
                        self._set_power_on()
                    else:
                        self._set_power_off()
                return True
        except Exception as e:
            logging.error(f"Fehler im Repair: {e}")
        return True