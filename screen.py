import os
import json
import subprocess
import logging
from time import sleep, time
from datetime import datetime
from threading import Thread

# Versuchen psutil zu importieren (für CPU Last Prüfung)
try:
    import psutil
except ImportError:
    psutil = None
    logging.warning("psutil nicht gefunden! CPU-Überwachung deaktiviert.")

class Screen:

    def __init__(self, start_script_path: str = None, stop_script_path: str = None, max_cpu_load: float = 90.0):
        self.__listeners = set()
        self.start_script_path = start_script_path.strip() if start_script_path else None
        self.stop_script_path = stop_script_path.strip() if stop_script_path else None

        # Status Variablen
        self.is_screen_on = False
        self.is_browser_started = False
        self.last_browser_restart_time = datetime.now()

        # CPU Config
        self.max_cpu_load = max_cpu_load
        self.last_cpu_restart_trigger = time()

        # Pfad-Checks
        if self.start_script_path:
            if not os.path.isfile(self.start_script_path):
                logging.error(f"Start script not found: {self.start_script_path}")
            else:
                logging.info(f"Start script path: {self.start_script_path}")

        if self.stop_script_path:
            if not os.path.isfile(self.stop_script_path):
                logging.error(f"Stop script not found: {self.stop_script_path}")
            else:
                logging.info(f"Stop script path: {self.stop_script_path}")

        # Threads starten
        Thread(target=self.__on_init, daemon=True).start()

        if psutil:
            Thread(target=self.__cpu_monitor, daemon=True).start()

    def add_listener(self, listener):
        self.__listeners.add(listener)

    def _notify_listeners(self):
        [listener() for listener in self.__listeners]

    def _get_env(self):
        """Erstellt die Umgebungsvariablen dynamisch für Wayland 0 oder 1."""
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        # Prüfen ob wayland-1 existiert, sonst wayland-0
        if os.path.exists("/run/user/1000/wayland-1"):
            env["WAYLAND_DISPLAY"] = "wayland-1"
        else:
            env["WAYLAND_DISPLAY"] = "wayland-0"
        return env

    def __on_init(self):
        sleep(90)
        logging.info("Late initialization of screen")
        # Einmaliger Reset beim Start
        self.deactivate_screen()
        self.activate_screen()

    def __cpu_monitor(self):
        """Überwacht CPU Last und startet Browser neu wenn nötig."""
        logging.info("CPU Monitor gestartet.")
        while True:
            try:
                # 5 Sekunden Durchschnitt messen
                cpu_usage = psutil.cpu_percent(interval=5)

                # Nur prüfen, wenn Browser läuft und Screen an ist
                if self.is_browser_started and self.is_screen_on:
                    # Cooldown von 60s einhalten
                    if (time() - self.last_cpu_restart_trigger) > 60:
                        if cpu_usage > self.max_cpu_load:
                            logging.warning(f"CPU ALARM: {cpu_usage}% > {self.max_cpu_load}%. Restarting Browser...")
                            self.restart_browser()
                            self.last_cpu_restart_trigger = time()
            except Exception as e:
                logging.error(f"Error in CPU monitor: {e}")
                sleep(10)

    def restart_browser(self):
        logging.info("Führe Browser-Neustart durch...")
        self.__stop_browser()
        sleep(2)
        self.__start_browser()

    def set_screen(self, is_on: bool):
        if is_on:
            self.activate_screen()
        else:
            self.deactivate_screen()

    def activate_screen(self):
        # Erst Browser starten, dann Bildschirm an
        if not self.is_browser_started:
            self.__start_browser()
        self.__set_screen_power(True)

    def deactivate_screen(self):
        # Erst Bildschirm aus, dann Browser killen
        self.__set_screen_power(False)
        self.__stop_browser()

    def __set_screen_power(self, is_on: bool):
        try:
            env = self._get_env()
            state = "--on" if is_on else "--off"

            # Wlr-randr ausführen
            subprocess.run(["wlr-randr", "--output", "HDMI-A-2", state], env=env, check=True)

            sleep(1) # Hardware Zeit geben

            # Überprüfung
            real_state = self.__get_real_screen_state()

            if real_state == is_on:
                logging.info(f"Screen status verified: {'ON' if real_state else 'OFF'}")
            else:
                logging.warning(f"Screen Status Mismatch! Wanted {is_on}, got {real_state}")

            self.is_screen_on = real_state

        except Exception as e:
            logging.warning(f"Error set screen power: {e}")
            self.is_screen_on = self.__get_real_screen_state()

        self._notify_listeners()

    def __get_real_screen_state(self) -> bool:
        env = self._get_env()
        try:
            result = subprocess.run(
                ["wlr-randr", "--json"],
                env=env,
                capture_output=True,
                text=True,
                check=True
            )
            outputs = json.loads(result.stdout)
            for output in outputs:
                if output.get("name") == "HDMI-A-2":
                    return output.get("enabled", False)

            logging.warning("HDMI-A-2 not found in wlr-randr output!")
            return False

        except Exception as e:
            logging.error(f"Error reading screen status: {e}")
            return self.is_screen_on

    def __start_browser(self):
        self.last_browser_restart_time = datetime.now()
        if self.start_script_path and len(self.start_script_path) > 0:
            try:
                env = self._get_env()
                subprocess.Popen(["/bin/bash", self.start_script_path], env=env)
                self.is_browser_started = True
            except Exception as e:
                self.is_browser_started = False
                logging.warning(f"Error executing start script: {e}")
        else:
            self.is_browser_started = True

    def __stop_browser(self):
        self.is_browser_started = False
        if self.stop_script_path and len(self.stop_script_path) > 0:
            try:
                env = self._get_env()
                self.is_browser_started = False
                subprocess.run(["/bin/bash", self.stop_script_path], env=env)
            except Exception as e:
                logging.warning(f"Error executing stop script: {e}")