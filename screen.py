import os
import re
import subprocess
import logging
from time import sleep
from threading import Thread, Lock
from typing import Optional, List



class Screen:
    def __init__(self, start_script_path: str = None, stop_script_path: str = None):
        self.__listeners = set()
        self.lock = Lock()  # Verhindert Kollisionen bei wlr-randr Aufrufen

        self.start_script_path = start_script_path.strip() if start_script_path else None
        self.stop_script_path = stop_script_path.strip() if stop_script_path else None

        self.is_screen_on = False
        self.is_browser_started = False

        if self.start_script_path and not os.path.isfile(self.start_script_path):
            logging.error(f"Start-Script nicht gefunden: {self.start_script_path}")
        if self.stop_script_path and not os.path.isfile(self.stop_script_path):
            logging.error(f"Stop-Script nicht gefunden: {self.stop_script_path}")

        Thread(target=self.__on_init, daemon=True).start()
        Thread(target=self.__repair_loop, daemon=True).start()

    def add_listener(self, listener):
        self.__listeners.add(listener)

    def _notify_listeners(self):
        for listener in self.__listeners:
            try:
                listener()
            except Exception as e:
                logging.debug(f"Listener Fehler: {e}")

    def __get_env(self):
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        if os.path.exists("/run/user/1000/wayland-1"):
            env["WAYLAND_DISPLAY"] = "wayland-1"
        else:
            env["WAYLAND_DISPLAY"] = "wayland-0"
        return env

    def __on_init(self):
        sleep(60)
        logging.info("Initialisierung: Setze Bildschirm-Grundzustand...")
        self.deactivate_screen()
        sleep(5)
        self.activate_screen(force=True)

    def __get_available_outputs(self) -> List[str]:
        try:
            result = subprocess.run(["wlr-randr"], env=self.__get_env(), capture_output=True, text=True, timeout=5)
            outputs = re.findall(r"^(\S+)\s", result.stdout, re.MULTILINE)
            return [o for o in outputs if o not in ["Make", "Model", "Enabled", "Modes:"]]
        except Exception:
            return ["HDMI-A-2"]

    def set_screen(self, is_on: bool):
        if is_on:
            self.activate_screen()
        else:
            self.deactivate_screen()

    def activate_screen(self, force: bool = False):
        with self.lock:
            # NUR starten, wenn er nicht läuft. Nicht jedes Mal forcieren!
            if not self.__is_browser_running():
                logging.info("Browser läuft nicht. Starte...")
                self.__start_browser()

            if force or not self.is_screen_on:
                logging.info("Aktion: Bildschirm EIN")
                if self.__set_power(True):
                    self.is_screen_on = True
                    self._notify_listeners()


    def deactivate_screen(self):
        with self.lock:
            logging.info("Aktion: Bildschirm AUS")
            self.is_screen_on = False
            if self.__set_power(False):
                self.__stop_browser()
                self._notify_listeners()


    def __set_power(self, on: bool) -> bool:
        cmd_state = "--on" if on else "--off"
        outputs = self.__get_available_outputs()
        success = True

        for out in outputs:
            try:
                # 1. Versuch
                res = subprocess.run(["wlr-randr", "--output", out, cmd_state],
                                     env=self.__get_env(), capture_output=True, text=True)

                if res.returncode != 0:
                    logging.warning(f"Fehler bei {out}. Warte kurz...")
                    sleep(3) # Längere Pause für den HDMI-Handshake

                    # Pro-Tipp: Manchmal hilft es, einen Mode explizit zu setzen
                    # anstatt nur --on, um den 'failed to apply' Fehler zu umgehen.
                    # Wir versuchen es hier erst nochmal mit einem sauberen 'off' -> 'on'
                    subprocess.run(["wlr-randr", "--output", out, "--off"], env=self.__get_env())
                    sleep(2)
                    res = subprocess.run(["wlr-randr", "--output", out, "--on"],
                                         env=self.__get_env(), capture_output=True, text=True)

                if res.returncode != 0:
                    # Letzter Versuch: Falls es immer noch scheitert,
                    # könnte der DRM-Lease blockiert sein.
                    logging.error(f"Konnte {out} nicht schalten: {res.stderr.strip()}")
                    success = False
            except Exception as e:
                logging.error(f"Subprocess Fehler: {e}")
                success = False
        return success

    def __get_screen_power_status(self) -> Optional[bool]:
        try:
            result = subprocess.run(["wlr-randr"], env=self.__get_env(), capture_output=True, text=True, timeout=5)
            output = result.stdout
            if "Enabled: yes" in output:
                return True
            if "Enabled: no" in output:
                return False
            return None
        except:
            return None

    def __repair_loop(self):
        """ Überwacht permanent den Soll-Zustand """
        while True:
            sleep(20)
            try:
                hw_on = self.__get_screen_power_status()
                if hw_on is None:
                    continue

                # Wenn Hardware-Status vom Software-Status abweicht -> Reparieren
                if hw_on != self.is_screen_on:
                    logging.warning(f"Repair: Hardware ist {hw_on}, sollte sein {self.is_screen_on}")
                    if self.is_screen_on:
                        self.activate_screen(force=True)
                    else:
                        self.deactivate_screen()

                # Browser-Wächter
                if self.is_browser_started:
                    res = subprocess.run(["pgrep", "chromium"], capture_output=True)
                    if res.returncode != 0:
                        logging.warning("Browser-Prozess verschwunden! Starte neu...")
                        self.__start_browser()
            except Exception as e:
                logging.error(f"Fehler im Repair-Loop: {e}")

    def __start_browser(self):
        if self.start_script_path:
            try:
                subprocess.Popen(["/bin/bash", self.start_script_path], env=self.__get_env())
                self.is_browser_started = True
            except Exception as e:
                logging.error(f"Fehler beim Browser-Start: {e}")

    def __stop_browser(self):
        if self.stop_script_path:
            try:
                subprocess.run(["/bin/bash", self.stop_script_path], env=self.__get_env())
                self.is_browser_started = False
            except Exception as e:
                logging.error(f"Fehler beim Browser-Stop: {e}")