import os
import re
import subprocess
import logging
import time
from threading import Thread, Lock
from typing import List
from datetime import datetime, timedelta



class Screen:
    def __init__(self, start_script: str = None, stop_script: str = None):
        self._listeners = set()
        self._lock = Lock()

        self.start_script = start_script.strip() if start_script else None
        self.stop_script = stop_script.strip() if stop_script else None

        self.target_state_is_on = False
        self.browser_active = False
        self.last_browser_attempt = datetime.now() - timedelta(seconds=60)

        Thread(target=self._init_sequence, daemon=True).start()
        Thread(target=self._repair_loop, daemon=True).start()


    @property
    def is_screen_on(self) -> bool:
        return self.target_state_is_on

    def _get_env(self):
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        # Check for Wayland display availability
        env["WAYLAND_DISPLAY"] = "wayland-1" if os.path.exists("/run/user/1000/wayland-1") else "wayland-0"
        return env

    def _get_outputs(self) -> List[str]:
        """Filters out virtual NOOP outputs."""
        try:
            res = subprocess.run(["wlr-randr"], env=self._get_env(), capture_output=True, text=True, timeout=5)
            # Find identifiers at the start of lines
            found = re.findall(r"^(\S+)\s", res.stdout, re.MULTILINE)
            # Filter: No NOOP, no header keywords
            ignore = {"Make", "Model", "Enabled", "Modes:"}
            valid = [o for o in found if "NOOP" not in o and o not in ignore]
            return valid if valid else ["HDMI-A-2"]
        except Exception:
            return ["HDMI-A-2"]

    def _is_browser_running(self) -> bool:
        try:
            return subprocess.run(["pgrep", "chromium"], capture_output=True).returncode == 0
        except Exception:
            return False

    def set_screen(self, turn_on: bool):
        """Manual control from external source."""
        self.activate() if turn_on else self.deactivate()

    def activate(self, force: bool = False):
        with self._lock:
            # 1. First try to turn on hardware
            hw_success = True
            if force or not self.target_state_is_on:
                logging.info("Action: Screen ON")
                self.target_state_is_on = True
                hw_success = self._set_power(True)
                if hw_success:
                    self._notify_listeners()
                else:
                    logging.error("Aborting browser start, hardware not ready.")
                    return # IMPORTANT: Abort here!

            # 2. Start browser ONLY if hardware check passed
            if hw_success and not self._is_browser_running():
                now = datetime.now()
                if now > self.last_browser_attempt + timedelta(seconds=15):
                    logging.info("Watchdog: Hardware OK. Starting browser...")
                    self.last_browser_attempt = now
                    self._start_browser_script()

    def deactivate(self):
        with self._lock:
            logging.info("Action: Screen OFF")
            self.target_state_is_on = False
            self._set_power(False)
            self._stop_browser_script()
            self._notify_listeners()

    def _set_power(self, on: bool) -> bool:
        output = "HDMI-A-2"
        env = self._get_env()

        if on:
            logging.info(f"Wecke Hardware {output}...")
            # Schritt 1: Nur Einschalten
            subprocess.run(["wlr-randr", "--output", output, "--on"], env=env)

            # Schritt 2: Dem Monitor Zeit geben, den Handshake zu machen
            time.sleep(3)

            # Schritt 3: Modus explizit setzen (das stabilisiert das Bild)
            res = subprocess.run(["wlr-randr", "--output", output, "--mode", "1280x800"],
                                 env=env, capture_output=True, text=True)

            if res.returncode == 0:
                logging.info(f"Hardware {output} erfolgreich auf 1280x800 gesetzt.")
                return True
            else:
                logging.error(f"Fehler beim Setzen des Modus: {res.stderr.strip()}")
                return False
        else:
            # Ausschalten ist meist unkritisch
            logging.info(f"Schalte Hardware {output} AUS.")
            res = subprocess.run(["wlr-randr", "--output", output, "--off"],
                                 env=env, capture_output=True, text=True)
            return res.returncode == 0

    def _run_randr(self, output: str, state: str) -> bool:
        env = self._get_env()

        # Wir nutzen DPMS (Energy Saving) statt den Ausgang komplett zu deaktivieren
        dpms_state = "on" if state == "--on" else "off"

        # Befehl: wlr-randr --output HDMI-A-2 --power on/off
        cmd = ["wlr-randr", "--output", output, "--power", dpms_state]

        logging.info(f"Sende DPMS {dpms_state} an {output}...")
        res = subprocess.run(cmd, env=env, capture_output=True, text=True)

        if res.returncode == 0:
            return True

        # Fallback: Falls --power nicht unterstützt wird, nutze --on/--off mit Modus
        logging.warning(f"DPMS fehlgeschlagen, versuche Mode-Erzwingung...")
        if state == "--on":
            cmd = ["wlr-randr", "--output", output, "--on", "--mode", "1280x800"]
        else:
            cmd = ["wlr-randr", "--output", output, "--off"]

        res = subprocess.run(cmd, env=env, capture_output=True, text=True)
        return res.returncode == 0

    def _repair_loop(self):
        while True:
            time.sleep(20)
            try:
                res = subprocess.run(["wlr-randr"], env=self._get_env(), capture_output=True, text=True)

                # Wir suchen gezielt nur im Block von HDMI-A-2
                # Das verhindert Fehlalarme durch virtuelle NOOP-Devices
                match = re.search(r"HDMI-A-2.*?Enabled:\s+(yes|no)", res.stdout, re.DOTALL)

                if match:
                    hw_is_on = (match.group(1) == "yes")
                    with self._lock:
                        if hw_is_on != self.target_state_is_on:
                            logging.warning(f"Repair: HW ist {hw_is_on}, Soll ist {self.target_state_is_on}")
                            self.activate(force=True) if self.target_state_is_on else self.deactivate()
            except Exception as e:
                logging.error(f"Fehler im Repair-Loop: {e}")

    def _init_sequence(self):
        time.sleep(45) # Slightly earlier than before
        logging.info("Init: Setting base state...")
        self.deactivate()
        time.sleep(5)
        self.activate(force=True)

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