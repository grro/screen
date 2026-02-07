import os
import subprocess
import logging


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
            is_updated = self.on != status
            self.on = status
            self._notify_listeners()
            logging.info(f"screen is {state}")

            if self.on:
                self.__on_start()
            else:
                if is_updated:
                    self.__on_stop()
        except Exception as e:
            logging.warning(f"Error: {e}")

    def __on_start(self):
        if len(self.start_script_path) > 0:
            try:
                env = os.environ.copy()
                env["XDG_RUNTIME_DIR"] = "/run/user/1000"
                env["WAYLAND_DISPLAY"] = "wayland-0"
                subprocess.Popen([self.start_script_path], env=env)
                logging.info("Start script initiated")
            except Exception as e:
                logging.warning(f"Error executing start script: {e}")

    def __on_stop(self):
        if len(self.stop_script_path) > 0:
            try:
                env = os.environ.copy()
                env["XDG_RUNTIME_DIR"] = "/run/user/1000"
                env["WAYLAND_DISPLAY"] = "wayland-0"
                subprocess.run([self.stop_script_path], env=env)
                logging.info("Stop script executed successfully")
            except Exception as e:
                logging.warning(f"Error executing stop script: {e}")
        pass
