import os
import subprocess
import logging
from time import sleep
from threading import Thread
from datetime import datetime, timedelta
from evdev import InputDevice, ecodes


class TouchListener:
    def __init__(self, device_path, on_touch_callback):
        self.device_path = device_path
        self.callback = on_touch_callback
        self.running = False
        self.thread = None
        self.last_touch = datetime.now()

    def start(self):
        self.running = True
        self.thread = Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        logging.info(f"[TouchListener] listen on: {self.device_path}")

    def stop(self):
        self.running = False

    def _listen_loop(self):
        try:
            device = InputDevice(self.device_path)

            for event in device.read_loop():
                if not self.running:
                    break

                if event.type == ecodes.EV_KEY or event.type == ecodes.EV_ABS:
                    if datetime.now() - self.last_touch > timedelta(seconds=5):
                        logging.info(f"[TouchListener] touch detected")
                        self.callback()
                        self.last_touch = datetime.now()
        except FileNotFoundError:
            logging.warning(f"[TouchListener] CRITICAL: Device {self.device_path} not found")
        except Exception as e:
            logging.warning(f"[TouchListener] error: {e}")



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
        self.touch_listener = TouchListener(device_path="/dev/input/event0",
                                            on_touch_callback=lambda: self.set_screen_power(True, reason="Reason: touch detected"))
        self.touch_listener.start()

    def add_listener(self, listener):
        self.__listeners.add(listener)

    def _notify_listeners(self):
        [listener() for listener in self.__listeners]

    def __on_init(self):
        sleep(90)
        self.set_screen_power(True, reason=" Reason: initial activation after 90s")

    def set_screen_power(self, on: bool, force: bool = False, reason: str = ""):
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        env["WAYLAND_DISPLAY"] = "wayland-0"

        if force or self.on != on:
            try:
                if on:
                    self.__on_start(reason)
                else:
                    self.__on_stop(reason)
            except Exception as e:
                logging.warning(f"Error executing scripts: {e}")

            try:
                state = "--on" if on else "--off"
                subprocess.run(["wlr-randr", "--output", "HDMI-A-2", state], env=env, check=True)
                logging.info(f"Screen power set to {'ON' if on else 'OFF'}")
                self.on = on
                self._notify_listeners()

            except Exception as e:
                logging.warning(f"Error: {e}")

    def __on_start(self, reason: str):
        if len(self.start_script_path) > 0:
            try:
                env = os.environ.copy()
                env["XDG_RUNTIME_DIR"] = "/run/user/1000"
                env["WAYLAND_DISPLAY"] = "wayland-0"
                logging.info("Executing " + self.start_script_path + " " + reason)
                subprocess.Popen([self.start_script_path], env=env)
            except Exception as e:
                logging.warning(f"Error executing start script: {e}")


    def __on_stop(self, reason: str):
        if len(self.stop_script_path) > 0:
            try:
                env = os.environ.copy()
                env["XDG_RUNTIME_DIR"] = "/run/user/1000"
                env["WAYLAND_DISPLAY"] = "wayland-0"
                logging.info("Executing " + self.stop_script_path + " " + reason)
                subprocess.run([self.stop_script_path], env=env)
            except Exception as e:
                logging.warning(f"Error executing stop script: {e}")
