import os
import subprocess
import logging


class Screen:

    def __init__(self):
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
        except Exception as e:
            logging.warning(f"Error: {e}")


