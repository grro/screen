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
        self.is_screen_on = False
        self.is_browser_started = False
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

        self.deactivate_screen()
        Thread(target=self.__on_init, daemon=True).start()

    def add_listener(self, listener):
        self.__listeners.add(listener)

    def _notify_listeners(self):
        [listener() for listener in self.__listeners]

    def __on_init(self):
        sleep(90)
        logging.info("late initialization of screen")
        self.activate_screen(force=True)

    def set_screen(self, force: bool):
        if force or self.is_screen_on:
            self.activate_screen(force=force)
        else:
            self.deactivate_screen()

    def activate_screen(self, force: bool = False):
        logging.info("activate screen")
        if force or not self.is_browser_started:
            self.__start_browser()

        if force or not self.is_screen_on:
            self.__set_screen_power(True)

    def deactivate_screen(self):
        logging.info("deactivate screen")
        if self.is_browser_started:
            self.__stop_browser()

        if self.is_screen_on:
            self.__set_screen_power(False)

    def __set_screen_power(self, on: bool):
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        env["WAYLAND_DISPLAY"] = "wayland-0"
        try:
            state = "--on" if on else "--off"
            subprocess.run(["wlr-randr", "--output", "HDMI-A-2", state], env=env, check=True)
            logging.info(f"Screen power set to {'ON' if on else 'OFF'}")
            self.is_screen_on = on
            self._notify_listeners()

        except Exception as e:
            logging.warning(f"Error: {e}")

    def __start_browser(self):
        if len(self.start_script_path) > 0:
            try:
                env = os.environ.copy()
                env["XDG_RUNTIME_DIR"] = "/run/user/1000"
                env["WAYLAND_DISPLAY"] = "wayland-0"
                logging.info("Executing " + self.start_script_path)
                subprocess.Popen([self.start_script_path], env=env)
                self.is_browser_started = True
            except Exception as e:
                self.is_browser_started = False
                logging.warning(f"Error executing start script: {e}")
        else:
            self.is_browser_started = True

    def __stop_browser(self):
        self.is_browser_started = False
        if len(self.stop_script_path) > 0:
            try:
                env = os.environ.copy()
                env["XDG_RUNTIME_DIR"] = "/run/user/1000"
                env["WAYLAND_DISPLAY"] = "wayland-0"
                logging.info("Executing " + self.stop_script_path)
                subprocess.run([self.stop_script_path], env=env)
            except Exception as e:
                logging.warning(f"Error executing stop script: {e}")
