import os
import re
import subprocess
import logging
import time
from threading import Thread, RLock
from datetime import datetime, timedelta
from time import sleep


class Screen:

    def __init__(self, start_script: str = None, stop_script: str = None):
        self._listeners = set()
        self._lock = RLock()
        self._initialized = False  # Verhindert Repair-Eingriffe während des Bootens

        self.start_script = start_script.strip() if start_script else None
        self.stop_script = stop_script.strip() if stop_script else None

        self.screen_on_target_state = False
        self.browser_active = False
        self.last_browser_attempt = datetime.now() - timedelta(seconds=60)

        self.last_hw_action = datetime.now()

        # Threads starten
        Thread(target=self._init_sequence, daemon=True).start()
        Thread(target=self._repair_loop, daemon=True).start()

    def _get_env(self):
        env = os.environ.copy()
        runtime_dir = "/run/user/1000"
        env["XDG_RUNTIME_DIR"] = runtime_dir

        # Suche aktiv nach dem existierenden Socket
        sockets = [f for f in os.listdir(runtime_dir) if f.startswith("wayland-")]
        if sockets:
            # Sortiere nach Zeitstempel, nimm den neuesten
            sockets.sort(key=lambda x: os.path.getmtime(os.path.join(runtime_dir, x)), reverse=True)
            env["WAYLAND_DISPLAY"] = sockets[0]
        return env

    @property
    def is_screen_on(self) -> bool:
        return self.screen_on_target_state


    def _is_screen_power_on(self) -> bool:
        res = subprocess.run(["wlr-randr"], env=self._get_env(), capture_output=True, text=True)
        # Regex filtert gezielt nur den Block des physischen Monitors
        match = re.search(r"HDMI-A-2.*?Enabled:\s+(yes|no)", res.stdout, re.DOTALL)
        if match:
            return match.group(1) == "yes"
        return False


    def _is_browser_running(self) -> bool:
        try:
            return subprocess.run(["pgrep", "chromium"], capture_output=True).returncode == 0
        except Exception:
            return False


    def set_screen(self, turn_on: bool):
        """Manuelle Steuerung von extern."""
        self.activate() if turn_on else self.deactivate()


    def activate(self):
        self.screen_on_target_state = True
        if not self._initialized:
            return

        with self._lock:
            # 1. Browser prüfen/starten
            if not self._is_browser_running():
                self._start_browser_script()
                # Chromium Zeit geben, DRM-Ressourcen zu sortieren
                sleep(5)

            # 2. Hardware wecken (JETZT KORREKT AUSGEHÄNGT)
            if not self._is_screen_power_on():
                # _set_power_on liefert durch deinen Rettungsanker nun True
                self._set_power_on()
                self._notify_listeners()
            else:
                # Falls Monitor schon an war, Listener trotzdem triggern
                self._notify_listeners()


    def deactivate(self):
        self.screen_on_target_state = False

        if not self._initialized:
            logging.warning("Ignoriere deactivate(): System bootet noch.")
        else:
            with self._lock:
                logging.info("Action: Screen OFF")
                self._set_power_off()
                self._stop_browser_script()
                self._notify_listeners()


    def _set_power_on(self) -> bool:
        output = "HDMI-A-2"
        env = self._get_env()
        self.last_hw_action = datetime.now()

        logging.info(f"Hardware-Reset-Sequenz für {output}...")

        # NEU: Ein expliziter Aufruf ohne Parameter triggert oft
        # eine Neuzuordnung der DRM-Ressourcen im Kernel.
        subprocess.run(["wlr-randr"], env=env, capture_output=True)

        # Hard-Reset: Erst aus
        subprocess.run(["wlr-randr", "--output", output, "--off"], env=env, capture_output=True)
        time.sleep(2) # Pause erhöhen

        # Dann an
        subprocess.run(["wlr-randr", "--output", output, "--on"], env=env, capture_output=True)
        time.sleep(5)

        # Modus setzen
        res = subprocess.run(["wlr-randr", "--output", output, "--mode", "1280x800"],
                             env=env, capture_output=True, text=True)

        if res.returncode == 0:
            logging.info(f"Hardware {output} erfolgreich gesetzt.")
            return True

        # Letzter Rettungsanker:
        # Wir versuchen den Monitor einfach 'anzuschubsen', ohne eine Bestätigung abzuwarten.
        logging.warning(f"Modus-Fehler: {res.stderr.strip()}. Erzwinge Auto-On...")
        subprocess.run(["wlr-randr", "--output", output, "--on"], env=env)

        # Wir geben True zurück, weil der Repair-Loop in 20s sowieso nochmal prüft,
        # ob der Monitor durch den 'Schubs' angegangen ist.
        return True


    def _set_power_off(self) -> bool:
        output = "HDMI-A-2"
        env = self._get_env()

        logging.info(f"Schalte Hardware {output} AUS.")
        res = subprocess.run(["wlr-randr", "--output", output, "--off"],
                             env=env, capture_output=True, text=True)
        return res.returncode == 0


    def _init_sequence(self):
        # 45 Sek. warten: Host-Compositor & DRM-Master müssen stabil sein
        time.sleep(45)
        logging.info("Init: Setze Basis-Zustand...")

        # WICHTIG: Erst das Flag auf True setzen, damit activate() durchgelassen wird
        self._initialized = True
        self.activate()

        time.sleep(5)
        logging.info("Init: System bereit, Repair-Loop aktiv.")


    def _start_browser_script(self):
        if self.start_script:
            logging.info(" Starting browser...")
            try:
                subprocess.Popen(["/bin/bash", self.start_script], env=self._get_env())   # non-blocking
                self.browser_active = True
            except Exception as e:
                logging.error(f"Browser start error: {e}")

    def _stop_browser_script(self):
        if self.stop_script:
            logging.info(" Stopping browser...")
            try:
                subprocess.run(["/bin/bash", self.stop_script], env=self._get_env())
                self.browser_active = False
            except Exception as e:
                logging.error(f"Browser stop error: {e}")

    def add_listener(self, listener):
        self._listeners.add(listener)

    def _notify_listeners(self):
        [l() for l in self._listeners if callable(l)]


    def _repair_loop(self):
        while True:
            time.sleep(20)

            if not self._initialized:
                continue

            # OPTIMIERUNG: Wenn gerade erst geschaltet wurde, 15s lang NICHTS tun.
            # Das verhindert, dass der Loop eine laufende Initialisierung stört.
            if datetime.now() < self.last_hw_action + timedelta(seconds=15):
                continue

            if self._repair_browser():
                sleep(3)
            self._repair_screen_power()


    def _repair_browser(self) -> bool:
        try:
            if self.screen_on_target_state and not self._is_browser_running():
                logging.warning("Repair: Browser nicht aktiv, aber Bildschirm soll an sein.")
                with self._lock:
                    self._start_browser_script()
            else:
                return False
        except Exception as e:
            logging.error(f"Fehler im Browser-Repair: {e}")
        return True


    def _repair_screen_power(self) -> bool:
        try:
            hw_is_on = self._is_screen_power_on()
            if hw_is_on != self.screen_on_target_state:
                logging.warning(f"Repair: HW ist {hw_is_on}, Soll ist {self.screen_on_target_state}")

                with self._lock:
                    self._set_power_on() if self.screen_on_target_state else self._set_power_off()
            else:
                return False
        except Exception as e:
            logging.error(f"Fehler im Repair: {e}")
        return True

