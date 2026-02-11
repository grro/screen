import os
import subprocess
import logging
from time import sleep
from threading import Thread



class Screen:

    def __init__(self, start_script_path: str = None, stop_script_path: str = None):
        self.__listeners = set()
        self.start_script_path = start_script_path.strip() if start_script_path else None
        self.stop_script_path = stop_script_path.strip() if stop_script_path else None
        self.on = False
        self.set_screen_power(self.on)
        if self.start_script_path is not None and len(self.start_script_path) > 0:
            if self.start_script_path and not os.path.isfile(self.start_script_path):
                logging.error(f"start script not found {self.start_script_path}")
            else:
                logging.info("start script path: " + str(self.start_script_path))
        if self.stop_script_path is not None and len(self.stop_script_path) > 0:
            if self.stop_script_path and not os.path.isfile(self.stop_script_path):
                logging.error(f"stop script not found {self.stop_script_path}")
            else:
                logging.info("stop script path: " + str(self.stop_script_path))

        Thread(target=self.__on_init, daemon=True).start()
        Thread(target=self.__auto_restart, daemon=True).start()

    def add_listener(self, listener):
        self.__listeners.add(listener)

    def _notify_listeners(self):
        [listener() for listener in self.__listeners]

    def __on_init(self):
        self.__restart_browser()
        self.set_screen_power(True, reason=" Reason: initial activation after 90s")

    def set_screen_power(self, on: bool, force: bool = False, reason: str = ""):
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        env["WAYLAND_DISPLAY"] = "wayland-0"

        if force or self.on != on:
            try:
                state = "--on" if on else "--off"
                subprocess.run(["wlr-randr", "--output", "HDMI-A-2", state], env=env, check=True)
                logging.info(f"Screen power set to {'ON' if on else 'OFF'}")
                self.on = on
                self._notify_listeners()

            except Exception as e:
                logging.warning(f"Error: {e}")

    def __auto_restart(self):
        while True:
            sleep(30*60)
            if not self.on:
                self.__restart_browser()

    def __restart_browser(self):
        try:
            self.__on_stop_browser()
            self.__on_start_browser()
        except Exception as e:
            logging.warning(f"Error during browser restart: {e}")

    def __on_start_browser(self):
        if len(self.start_script_path) > 0:
            try:
                env = os.environ.copy()
                env["XDG_RUNTIME_DIR"] = "/run/user/1000"
                env["WAYLAND_DISPLAY"] = "wayland-0"
                logging.info("Executing " + self.start_script_path)
                subprocess.Popen([self.start_script_path], env=env)
            except Exception as e:
                logging.warning(f"Error executing start script: {e}")


    def __on_stop_browser(self):
        if len(self.stop_script_path) > 0:
            try:
                env = os.environ.copy()
                env["XDG_RUNTIME_DIR"] = "/run/user/1000"
                env["WAYLAND_DISPLAY"] = "wayland-0"
                logging.info("Executing " + self.stop_script_path + " " + reason)
                subprocess.run([self.stop_script_path], env=env)
            except Exception as e:
                logging.warning(f"Error executing stop script: {e}")
