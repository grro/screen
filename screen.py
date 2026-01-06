import os
import subprocess
import logging


class Screen:

    def set_screen_power(self, status: bool):
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        env["WAYLAND_DISPLAY"] = "wayland-0"

        state = "--on" if status else "--off"

        try:
            subprocess.run(["wlr-randr", "--output", "HDMI-A-2", state], env=env, check=True)
            logging.info(f"scrren is {state}")
        except Exception as e:
            logging.warning(f"Error: {e}")


