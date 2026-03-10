import os
import re
import subprocess
import logging
import time
from threading import Thread, Lock
from datetime import datetime, timedelta


class Screen:

    def __init__(self, start_script: str = None, stop_script: str = None):
        self._listeners = set()
        self._lock = Lock()
        self._initialized = False  # Verhindert Repair-Eingriffe während des Bootens

        self.start_script = start_script.strip() if start_script else None
        self.stop_script = stop_script.strip() if stop_script else None

        self.target_state_is_on = False
        self.browser_active = False
        self.last_browser_attempt = datetime.now() - timedelta(seconds=60)

        # Threads starten
        Thread(target=self._init_sequence, daemon=True).start()
        Thread(target=self._repair_loop, daemon=True).start()

    @property
    def is_screen_on(self) -> bool:
        return self.target_state_is_on

    def _get_env(self):
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        # Dynamische Prüfung des Wayland-Sockets
        env["WAYLAND_DISPLAY"] = "wayland-1" if os.path.exists("/run/user/1000/wayland-1") else "wayland-0"
        return env

    def _is_browser_running(self) -> bool:
        try:
            return subprocess.run(["pgrep", "chromium"], capture_output=True).returncode == 0
        except Exception:
            return False

    def set_screen(self, turn_on: bool):
        """Manuelle Steuerung von extern."""
        self.activate() if turn_on else self.deactivate()

    def activate(self, force: bool = False):
        try:
            logging.info("enter activate, force=" + str(force))
            with self._lock:
                hw_success = True
                if force or not self.target_state_is_on:
                    logging.info("Action: Screen ON")
                    self.target_state_is_on = True
                    hw_success = self._set_power(True)
                    if hw_success:
                        self._notify_listeners()
                    else:
                        logging.error("Aborting browser start, hardware not ready.")
                        return

                        # Browser-Check (Watchdog)
                if hw_success and not self._is_browser_running():
                    now = datetime.now()
                    if now > self.last_browser_attempt + timedelta(seconds=15):
                        logging.info("Watchdog: Hardware OK. Starting browser...")
                        self.last_browser_attempt = now
                        self._start_browser_script()
        finally:
            logging.info("exit activate, force=" + str(force))

    def deactivate(self):
        try:
            logging.info("enter deactivate")
            with self._lock:
                logging.info("Action: Screen OFF")
                self.target_state_is_on = False
                self._set_power(False)
                self._stop_browser_script()
                self._notify_listeners()
        finally:
            logging.info("exit deactivate")

    def _set_power(self, on: bool) -> bool:
        output = "HDMI-A-2"
        env = self._get_env()

        if on:
            logging.info(f"Wecke Hardware {output}...")
            # Schritt 1: Nur Einschalten (Handshake triggern)
            subprocess.run(["wlr-randr", "--output", output, "--on"], env=env)

            # Schritt 2: Dem Monitor Zeit geben (EDID-Aushandlung)
            time.sleep(3)

            # Schritt 3: Modus explizit setzen (Stabilisierung)
            res = subprocess.run(["wlr-randr", "--output", output, "--mode", "1280x800"],
                                 env=env, capture_output=True, text=True)

            if res.returncode == 0:
                logging.info(f"Hardware {output} erfolgreich auf 1280x800 gesetzt.")
                return True
            else:
                logging.error(f"Fehler beim Setzen des Modus: {res.stderr.strip()}")
                return False
        else:
            logging.info(f"Schalte Hardware {output} AUS.")
            res = subprocess.run(["wlr-randr", "--output", output, "--off"],
                                 env=env, capture_output=True, text=True)
            return res.returncode == 0

    def _repair_loop(self):
        while True:
            time.sleep(20)
            if not self._initialized:
                continue

            try:
                res = subprocess.run(["wlr-randr"], env=self._get_env(), capture_output=True, text=True)
                # Regex filtert gezielt nur den Block des physischen Monitors
                match = re.search(r"HDMI-A-2.*?Enabled:\s+(yes|no)", res.stdout, re.DOTALL)

                if match:
                    hw_is_on = (match.group(1) == "yes")
                    if hw_is_on != self.target_state_is_on:
                        logging.warning(f"Repair: HW ist {hw_is_on}, Soll ist {self.target_state_is_on}")
                        self.activate(force=True) if self.target_state_is_on else self.deactivate()
            except Exception as e:
                logging.error(f"Fehler im Repair-Loop: {e}")

    def _init_sequence(self):
        # 45 Sek. warten: Host-Compositor & DRM-Master müssen stabil sein
        time.sleep(45)
        logging.info("Init: Setze Basis-Zustand...")

        # Initial-Zustand erzwingen (idR. "AN" beim Booten)
        self.activate(force=True)

        # Kleine Abklingzeit, dann Repair-Loop freigeben
        time.sleep(5)
        self._initialized = True
        logging.info("Init: System bereit, Repair-Loop aktiv.")

    def _start_browser_script(self):
        if self.start_script:
            try:
                subprocess.Popen(["/bin/bash", self.start_script], env=self._get_env())
                self.browser_active = True
            except Exception as e:
                logging.error(f"Browser start error: {e}")

    def _stop_browser_script(self):
        if self.stop_script:
            try:
                subprocess.run(["/bin/bash", self.stop_script], env=self._get_env())
                self.browser_active = False
            except Exception as e:
                logging.error(f"Browser stop error: {e}")

    def add_listener(self, listener):
        self._listeners.add(listener)

    def _notify_listeners(self):
        [l() for l in self._listeners if callable(l)]