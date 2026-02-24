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
        Thread(target=self.__repair_loop, daemon=True).start()
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
        # env has to be set for the docker container to access the wayland socket and run wlr-randr
        #    -e WAYLAND_DISPLAY=wayland-0 \
        #    -e XDG_RUNTIME_DIR=/run/user/1000 \
        #    ...
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
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
        self.__activate_screen_power()

    def deactivate_screen(self):
        self.__deactivate_screen_power()
        self.__stop_browser()

    def __activate_screen_power(self):
        try:
            result = subprocess.run(["wlr-randr", "--output", "HDMI-A-2", "--on"], env=self.__get_env(), check=True)
            if result.returncode == 0:
                if not self.is_screen_on:
                    logging.info(f"Screen power set to ON")
                self.is_screen_on = True
                self._notify_listeners()
            else:
                logging.warning(f"Failed to turn on screen {result}")
        except Exception as e:
            logging.warning(f"Error: {e}")

    def __deactivate_screen_power(self):
        try:
            result = subprocess.run(["wlr-randr", "--output", "HDMI-A-2", "--off"], env=self.__get_env(), check=True)
            if result.returncode == 0:
                if not self.is_screen_on:
                    logging.info(f"Screen power set to OFF")
                self.is_screen_on = False
                self._notify_listeners()
            else:
                logging.warning(f"Failed to turn off screen {result}")
        except Exception as e:
            logging.warning(f"Error: {e}")

    def __get_screen_status(self) -> Optional[bool]:
        try:
            result = subprocess.run(["wlr-randr"], env=self.__get_env(), capture_output=True, text=True, check=True)
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

    def __is_browser_running(self) -> bool:
        try:
            # pgrep returns 0 if process is found
            subprocess.run(["pgrep", "chromium"], check=True, stdout=subprocess.DEVNULL)
            return True
        except subprocess.CalledProcessError:
            return False

    def __repair_loop(self):
        while True:
            sleep(9)
            try:
                # 1. Repair Screen Power
                if self.is_screen_on and self.__get_screen_status() is False:
                    logging.warning("Screen is expected to be ON but hardware is OFF. Repairing power...")
                    self.__activate_screen_power()

                # 2. Repair Browser Process
                if self.is_browser_started and not self.__is_browser_running():
                    logging.warning("Browser is expected to be running but process not found. Restarting...")
                    self.__start_browser()

            except Exception as e:
                logging.warning(f"Error during repair cycle: {e}")

    def __start_browser(self):
        self.last_browser_restart_time = datetime.now()
        if len(self.start_script_path) > 0:
            try:
                subprocess.Popen(["/bin/bash", self.start_script_path], env=self.__get_env())
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
                self.is_browser_started = False
                subprocess.run(["/bin/bash", self.stop_script_path], env=self.__get_env())
            except Exception as e:
                logging.warning(f"Error executing stop script: {e}")


    def __touch_loop(self):
        logging.info("Starting Multi-Device-Scanner...")

        while True:
            try:
                devices = [InputDevice(path) for path in evdev.list_devices()]
                if not devices:
                    logging.warning("No input devices found at all in /dev/input!")
                    sleep(10)
                    continue

                for d in devices:
                    logging.info(f"Monitoring: {d.path} ({d.name})")

                from itertools import chain
                import select

                dev_map = {d.fd: d for d in devices}

                while True:
                    r, w, x = select.select(dev_map.keys(), [], [])
                    for fd in r:
                        for event in dev_map[fd].read():
                            now = datetime.now()
                            if now > self.last_touch_time + timedelta(seconds=5):
                                self.last_touch_time = now
                                logging.info(f"touch from {dev_map[fd].path}: type={event.type} code={event.code} val={event.value}")
                                if not self.is_screen_on:
                                    logging.info("Wake up!")
                                    self.activate_screen()

            except Exception as e:
                logging.error(f"Scanner Error: {e}")
                sleep(5)

