import os
import re
import subprocess
import logging
import time
from threading import Thread, Lock
from typing import List
from datetime import datetime, timedelta

class Screen:
    def __init__(self, start_script_path: str = None, stop_script_path: str = None):
        self.__listeners = set()
        self.lock = Lock()

        self.start_script_path = start_script_path.strip() if start_script_path else None
        self.stop_script_path = stop_script_path.strip() if stop_script_path else None

        self.is_screen_on = False
        self.is_browser_started = False
        self.last_browser_attempt = datetime.now() - timedelta(seconds=60)

        Thread(target=self.__on_init, daemon=True).start()
        Thread(target=self.__repair_loop, daemon=True).start()

    def __get_env(self):
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        env["WAYLAND_DISPLAY"] = "wayland-1" if os.path.exists("/run/user/1000/wayland-1") else "wayland-0"
        return env

    def __get_available_outputs(self) -> List[str]:
        """ Filtert virtuelle NOOP-Ausgänge strikt aus """
        try:
            result = subprocess.run(["wlr-randr"], env=self.__get_env(), capture_output=True, text=True, timeout=5)
            # Findet alle Bezeichner am Zeilenanfang
            all_found = re.findall(r"^(\S+)\s", result.stdout, re.MULTILINE)
            # Filter: Kein NOOP, keine Header-Keywords
            valid = [o for o in all_found if "NOOP" not in o and o not in ["Make", "Model", "Enabled", "Modes:"]]
            return valid if valid else ["HDMI-A-2"]
        except Exception:
            return ["HDMI-A-2"]

    def __is_browser_running(self) -> bool:
        try:
            res = subprocess.run(["pgrep", "chromium"], capture_output=True)
            return res.returncode == 0
        except:
            return False

    def set_screen(self, is_on: bool):
        """ Manuelle Steuerung von extern """
        if is_on:
            self.activate_screen()
        else:
            self.deactivate_screen()

    def activate_screen(self, force: bool = False):
        with self.lock:
            # 1. Hardware zuerst
            if force or not self.is_screen_on:
                logging.info("Aktion: Bildschirm EIN")
                self.is_screen_on = True
                self.__set_power(True)
                self._notify_listeners()

            # 2. Browser mit Zeit-Schutz (Cooldown)
            now = datetime.now()
            if not self.__is_browser_running():
                if now > self.last_browser_attempt + timedelta(seconds=15):
                    logging.info("Wächter: Browser läuft nicht. Starte neu...")
                    self.last_browser_attempt = now
                    self.__start_browser()
                else:
                    logging.debug("Browser-Start im Cooldown - warte auf Initialisierung...")

    def deactivate_screen(self):
        with self.lock:
            logging.info("Aktion: Bildschirm AUS")
            self.is_screen_on = False
            self.__set_power(False)
            self.__stop_browser()
            self._notify_listeners()

    def __set_power(self, on: bool) -> bool:
        cmd_state = "--on" if on else "--off"
        outputs = self.__get_available_outputs()

        for out in outputs:
            try:
                # Prüfen, ob der Ausgang aktuell wirklich existiert (verhindert NOOP-Leichen)
                res = subprocess.run(["wlr-randr", "--output", out, cmd_state],
                                     env=self.__get_env(), capture_output=True, text=True)

                if res.returncode != 0:
                    logging.warning(f"Hardware verweigert {out}. Versuche Reset...")
                    time.sleep(3)
                    subprocess.run(["wlr-randr", "--output", out, "--off"], env=self.__get_env())
                    time.sleep(2)
                    subprocess.run(["wlr-randr", "--output", out, "--on"], env=self.__get_env())
            except Exception as e:
                logging.error(f"Fehler bei Steuerung von {out}: {e}")
        return True

    def __repair_loop(self):
        while True:
            time.sleep(20)
            try:
                # 1. Hardware-Check
                res = subprocess.run(["wlr-randr"], env=self.__get_env(), capture_output=True, text=True)
                hw_is_on = "Enabled: yes" in res.stdout

                # 2. Reparatur-Logik (nur bei echter Abweichung)
                if hw_is_on != self.is_screen_on:
                    logging.warning(f"Repair: HW ist {hw_is_on}, Soll ist {self.is_screen_on}")
                    self.activate_screen(force=True) if self.is_screen_on else self.deactivate_screen()

                # 3. Browser-Check (Wächter)
                if self.is_browser_started and not self.__is_browser_running():
                    if datetime.now() > self.last_browser_attempt + timedelta(seconds=20):
                        logging.warning("Wächter: Browser-Prozess fehlt.")
                        self.activate_screen(force=False) # Nutzt die interne Logik inkl. Cooldown
            except Exception as e:
                logging.error(f"Fehler im Repair-Loop: {e}")

    def __on_init(self):
        time.sleep(45) # Etwas früher als bisher
        logging.info("Initialisierung: Setze Grundzustand...")
        self.deactivate_screen()
        time.sleep(5)
        self.activate_screen(force=True)

    def __start_browser(self):
        if self.start_script_path:
            try:
                subprocess.Popen(["/bin/bash", self.start_script_path], env=self.__get_env())
                self.is_browser_started = True
            except Exception as e:
                logging.error(f"Browser-Start Error: {e}")

    def __stop_browser(self):
        if self.stop_script_path:
            try:
                subprocess.run(["/bin/bash", self.stop_script_path], env=self.__get_env())
                self.is_browser_started = False
            except Exception as e:
                logging.error(f"Browser-Stop Error: {e}")

    def add_listener(self, listener): self.__listeners.add(listener)
    def _notify_listeners(self): [l() for l in self.__listeners if callable(l)]