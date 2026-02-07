import os
import subprocess
import logging


class Screen:

    def __init__(self, start_script_path: str = None, stop_script_path: str = None):
        self.start_script_path = start_script_path
        self.stop_script_path = stop_script_path
        self.on = True
        self.set_screen_power(self.on)
        self.__listeners = set()

    def add_listener(self, listener):
        self.__listeners.add(listener)

    def _notify_listeners(self):
        [listener() for listener in self.__listeners]

    def set_screen_power(self, status: bool):
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        env["WAYLAND_DISPLAY"] = "wayland-0"

        state = "--on" if status else "--off"
        try:
            subprocess.run(["wlr-randr", "--output", "HDMI-A-2", state], env=env, check=True)
            self.on = status
            self._notify_listeners()
            logging.info(f"screen is {state}")

            if self.on:
                self.__on_start()
            else:
                self.__on_stop()
        except Exception as e:
            logging.warning(f"Error: {e}")

    def __on_start(self):
        if len(self.start_script_path) > 0:
            try:
                subprocess.Popen([self.start_script_path])
                logging.info("Start script initiated")
            except Exception as e:
                logging.warning(f"Error executing start script: {e}")

    def __on_stop(self):
        if len(self.stop_script_path) > 0:
            try:
                subprocess.run([self.stop_script_path])
                logging.info("Stop script executed successfully")
            except Exception as e:
                logging.warning(f"Error executing stop script: {e}")
        pass
