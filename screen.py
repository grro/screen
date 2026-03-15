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
        self._initialized = False  # Verhindert Repair-Eingriffe während des Bootens

        self.start_script = start_script.strip() if start_script else None
        self.stop_script = stop_script.strip() if stop_script else None

        self.screen_on_target_state = False
        self.browser_active = False
        self.last_browser_attempt = datetime.now() - timedelta(seconds=60)

        # Threads starten
        Thread(target=self._init_sequence, daemon=True).start()
        Thread(target=self._repair_loop, daemon=True).start()


    def _get_env(self):
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        env["WAYLAND_DISPLAY"] = "wayland-1" if os.path.exists("/run/user/1000/wayland-1") else "wayland-0"
        return env


    @property
    def is_screen_on(self) -> bool:
        return self.screen_on_target_state


    def _is_screen_power_on(self) -> bool:
        res = subprocess.run(["wlr-randr"], env=self._get_env(), capture_output=True, text=True)
        # Regex filtert gezielt nur den Block des physischen Monitors
        match = re.search(r"HDMI-A-2.*?Enabled:\s+(yes|no)", res.stdout, re.DOTALL)
        if match:
            return match.group(1) == "yes"
        return False


    def _is_browser_running(self) -> bool:
        try:
            return subprocess.run(["pgrep", "chromium"], capture_output=True).returncode == 0
        except Exception:
            return False


    def set_screen(self, turn_on: bool):
        """Manuelle Steuerung von extern."""
        self.activate() if turn_on else self.deactivate()


    def activate(self):
        self.screen_on_target_state = True
        with self._lock:

            # bowser
            if not self._is_browser_running():
                now = datetime.now()
                if now > self.last_browser_attempt + timedelta(seconds=15):
                    self.last_browser_attempt = now
                    self._start_browser_script()
                    sleep(2)  # Kurze Wartezeit, damit der Browser initialisiert wird

            # screen power
            if not self._is_screen_power_on():
                if self._set_power_on():
                    self._notify_listeners()
                else:
                    logging.error("hardware not ready.")


    def deactivate(self):
        self.screen_on_target_state = False
        with self._lock:
            logging.info("Action: Screen OFF")
            self._set_power_off()
            self._stop_browser_script()
            self._notify_listeners()



    def _set_power_on(self) -> bool:
        output = "HDMI-A-2"
        env = self._get_env()

        # Schritt 1: Nur Einschalten (Handshake triggern)
        logging.info(f"Wecke Hardware {output}...")
        # SNur Einschalten (Handshake triggern)
        subprocess.run(["wlr-randr", "--output", output, "--on"], env=env, capture_output=True)

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


    def _set_power_off(self) -> bool:
        output = "HDMI-A-2"
        env = self._get_env()

        logging.info(f"Schalte Hardware {output} AUS.")
        res = subprocess.run(["wlr-randr", "--output", output, "--off"],
                             env=env, capture_output=True, text=True)
        return res.returncode == 0


    def _init_sequence(self):
        # 45 Sek. warten: Host-Compositor & DRM-Master müssen stabil sein
        time.sleep(45)
        logging.info("Init: Setze Basis-Zustand...")

        self.activate()

        time.sleep(5)
        self._initialized = True
        logging.info("Init: System bereit, Repair-Loop aktiv.")


    def _start_browser_script(self):
        if self.start_script:
            logging.info(" Starting browser...")
            try:
                subprocess.Popen(["/bin/bash", self.start_script], env=self._get_env())   # non-blocking
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
            time.sleep(9)
            if not self._initialized:
                continue

            if self._repair_browser():
                sleep(3)
            self._repair_screen_power()


    def _repair_browser(self) -> bool:
        try:
            if self.screen_on_target_state and not self._is_browser_running():
                logging.warning("Repair: Browser nicht aktiv, aber Bildschirm soll an sein.")
                self._start_browser_script()
            else:
                return False
        except Exception as e:
            logging.error(f"Fehler im Browser-Repair: {e}")
        return True


    def _repair_screen_power(self) -> bool:
        try:
            hw_is_on = self._is_screen_power_on()
            if hw_is_on != self.screen_on_target_state:
                logging.warning(f"Repair: HW ist {hw_is_on}, Soll ist {self.screen_on_target_state}")
                self._set_power_on() if self.screen_on_target_state else self._set_power_off()
            else:
                return False
        except Exception as e:
            logging.error(f"Fehler im Repair: {e}")
        return True

