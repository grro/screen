import os
import subprocess
import logging
from time import sleep
from datetime import datetime, timedelta
from threading import Thread
from typing import Optional
import evdev
from evdev import InputDevice, categorize, ecodes


class Screen:

    def __init__(self, start_script_path: str = None, stop_script_path: str = None):
        self.__listeners = set()
        self.start_script_path = start_script_path.strip() if start_script_path else None
        self.stop_script_path = stop_script_path.strip() if stop_script_path else None
        self.is_screen_on = False
        self.is_browser_started = False
        self.last_browser_restart_time = datetime.now()
        self.last_touch_time = datetime.now()
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
        Thread(target=self.__repair_screen_loop, daemon=True).start()
        Thread(target=self.__touch_loop, daemon=True).start()

    def add_listener(self, listener):
        self.__listeners.add(listener)

    def _notify_listeners(self):
        [listener() for listener in self.__listeners]

    def __on_init(self):
        sleep(90)
        logging.info("late initialization of screen")
        self.deactivate_screen()
        sleep(4)
        self.activate_screen(force=True)

    def __get_env(self):
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        if os.path.exists("/run/user/1000/wayland-1"):
            env["WAYLAND_DISPLAY"] = "wayland-1"
        else:
            env["WAYLAND_DISPLAY"] = "wayland-0"
        return env

    def set_screen(self, is_on: bool):
        if is_on:
            self.activate_screen()
        else:
            self.deactivate_screen()

    def activate_screen(self, force: bool = False):
        if force or not self.is_browser_started:
            self.__start_browser()
        self.__set_screen_power(True)

    def deactivate_screen(self):
        self.__set_screen_power(False)
        self.__stop_browser()

    def __set_screen_power(self, is_on: bool):
        env = self.__get_env()
        try:
            state = "--on" if is_on else "--off"
            subprocess.run(["wlr-randr", "--output", "HDMI-A-2", state], env=env, check=True)
            if self.is_screen_on != is_on:
                logging.info(f"Screen power set to {'ON' if is_on else 'OFF'}")
            self.is_screen_on = is_on
            self._notify_listeners()
        except Exception as e:
            logging.warning(f"Error: {e}")

    def __get_screen_status(self) -> Optional[bool]:
        env = self.__get_env()
        try:
            result = subprocess.run(["wlr-randr"], env=env, capture_output=True, text=True, check=True)
            output = result.stdout

            if "HDMI-A-2" in output:
                lines = output.splitlines()
                target_found = False
                for i, line in enumerate(lines):
                    if "HDMI-A-2" in line:
                        target_found = True
                        for j in range(i+1, min(i+10, len(lines))):
                            if "Enabled: yes" in lines[j]:
                                return True
                            if "Enabled: no" in lines[j]:
                                return False
                            if "  " in lines[j] and "*" in lines[j]:
                                return True
                return target_found
            return False
        except Exception as e:
            logging.warning(f"Failed to check screen status: {e}")
            return None

    def __repair_screen_loop(self):
        while True:
            sleep(9)
            try:
                if self.is_screen_on and self.__get_screen_status() is False:
                    logging.warning("Screen is expected to be ON but appears OFF. Attempting to repair...")
                    self.__set_screen_power(True)
            except Exception as e:
                logging.warning(f"Error repairing screen: {e}")

    def __start_browser(self):
        self.last_browser_restart_time = datetime.now()
        if len(self.start_script_path) > 0:
            try:
                env = self.__get_env()
                subprocess.Popen(["/bin/bash", self.start_script_path], env=env)
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
                env = self.__get_env()
                self.is_browser_started = False
                subprocess.run(["/bin/bash", self.stop_script_path], env=env)
            except Exception as e:
                logging.warning(f"Error executing stop script: {e}")


    def __touch_loop(self):
        while True:
            device_path = self.__find_touch_device_path()
            if not device_path:
                logging.warning("no touch device found. searching...")
                sleep(10)
                continue

            logging.info("touch device found: " + str(device_path))
            try:
                device = InputDevice(device_path)

                for event in device.read_loop():
                    if event.type in [ecodes.EV_ABS, ecodes.EV_KEY]:
                        if datetime.now() + timedelta(seconds=5) > self.last_touch_time:
                            logging.info("touch event")
                            self.last_touch_time = datetime.now()
                            if self.__get_screen_status() is False:
                                logging.info("activate screen due to touch event")
                                self.activate_screen()

            except Exception as e:
                logging.error(f"error reading touch device: {e}")
                sleep(5)

    def __find_touch_device_path(self) -> Optional[str]:
        try:
            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
            for device in devices:
                capabilities = device.capabilities()
                if ecodes.EV_ABS in capabilities:
                    abs_codes = [code[0] for code in capabilities[ecodes.EV_ABS]]
                    if ecodes.ABS_MT_POSITION_X in abs_codes or ecodes.ABS_X in abs_codes:
                        return device.path
        except Exception as e:
            logging.error(f"error detecting touch device: {e}")
        return None