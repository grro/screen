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
        self._initialized = False  # Verhindert Eingriffe während der 45s Boot-Phase

        self.start_script = start_script.strip() if start_script else None
        self.stop_script = stop_script.strip() if stop_script else None

        self.screen_on_target_state = False
        self.browser_active = False
        self.last_browser_attempt = datetime.now() - timedelta(seconds=60)
        self.last_hw_action = datetime.now() # Sperre für den Repair-Loop

        # Hintergrund-Überwachung starten
        Thread(target=self._init_sequence, daemon=True).start()
        Thread(target=self._repair_loop, daemon=True).start()

    def _get_env(self):
        """Erstellt die Umgebungsvariablen für Wayland-Zugriff."""
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = "/run/user/1000"
        env["WAYLAND_DISPLAY"] = "wayland-1" if os.path.exists("/run/user/1000/wayland-1") else "wayland-0"
        return env

    @property
    def is_screen_on(self) -> bool:
        return self.screen_on_target_state

    def _is_screen_power_on(self) -> bool:
        """Prüft den echten Hardware-Status via wlr-randr."""
        try:
            res = subprocess.run(["wlr-randr"], env=self._get_env(), capture_output=True, text=True, timeout=5)
            match = re.search(r"HDMI-A-2.*?Enabled:\s+(yes|no)", res.stdout, re.DOTALL)
            if match:
                return match.group(1) == "yes"
        except Exception as e:
            logging.error(f"Fehler beim Status-Check: {e}")
        return False

    def _is_browser_running(self) -> bool:
        """Prüft, ob Chromium-Prozesse existieren."""
        try:
            return subprocess.run(["pgrep", "chromium"], capture_output=True).returncode == 0
        except Exception:
            return False

    def set_screen(self, turn_on: bool):
        """Manuelle Steuerung (z.B. via API)."""
        self.activate() if turn_on else self.deactivate()

    def activate(self):
        """Aktiviert Browser und Hardware in der richtigen Reihenfolge (Vorhang-Effekt)."""
        self.screen_on_target_state = True

        if not self._initialized:
            logging.warning("Ignoriere activate(): System bootet noch (Warte auf Init-Sequenz).")
            return

        with self._lock:
            # 1. BROWSER: Starten, während das Bild noch aus ist (verhindert OS-Sichtbarkeit)
            if not self._is_browser_running():
                now = datetime.now()
                if now > self.last_browser_attempt + timedelta(seconds=15):
                    self.last_browser_attempt = now
                    self._start_browser_script()
                    sleep(3)  # Zeit für Chromium zum Rendern

            # 2. HARDWARE: Jetzt erst das Licht an
            if not self._is_screen_power_on():
                if self._set_power_on():
                    self._notify_listeners()
                else:
                    logging.error("Hardware konnte nicht aktiviert werden.")
            else:
                self._notify_listeners()

    def deactivate(self):
        """Schaltet Hardware aus und stoppt den Browser."""
        self.screen_on_target_state = False

        if not self._initialized:
            logging.warning("Ignoriere deactivate(): System bootet noch.")
            return

        with self._lock:
            logging.info("Action: Screen OFF")
            self._set_power_off()
            self._stop_browser_script()
            self._notify_listeners()

    def _set_power_on(self) -> bool:
        """Die robuste Einschalt-Sequenz mit Hard-Reset und Fallback."""
        output = "HDMI-A-2"
        env = self._get_env()
        self.last_hw_action = datetime.now()

        logging.info(f"Hardware-Reset-Sequenz für {output}...")

        # Kernel-Trigger (Versuch den Port direkt aufzuwecken)
        try:
            kernel_path = f"/sys/class/drm/card1-{output}/enabled"
            if os.path.exists(kernel_path):
                with open(kernel_path, 'w') as f:
                    f.write('on')
        except Exception as e:
            logging.debug(f"Kernel-Direktzugriff (sysfs) nicht möglich: {e}")

        # Schritt 1: Reset (Zustand im Grafikstack klären)
        subprocess.run(["wlr-randr", "--output", output, "--off"], env=env, capture_output=True)
        time.sleep(1)

        # Schritt 2: Weckruf
        subprocess.run(["wlr-randr", "--output", output, "--on"], env=env, capture_output=True)
        time.sleep(5) # Wichtig: Monitor Zeit für den Handshake geben

        # Schritt 3: Modus erzwingen
        res = subprocess.run(["wlr-randr", "--output", output, "--mode", "1280x800"],
                             env=env, capture_output=True, text=True)

        if res.returncode == 0:
            logging.info(f"Hardware {output} erfolgreich auf 1280x800 gesetzt.")
            return True

        # SCHRITT 4: Fallback (Wenn Modus fehlschlägt)
        logging.warning(f"Modus-Fehler: {res.stderr.strip()}. Versuche Auto-On Fallback...")
        res_fb = subprocess.run(["wlr-randr", "--output", output, "--on"], env=env, capture_output=True, text=True)

        if res_fb.returncode == 0:
            logging.info("Auto-On Fallback erfolgreich.")
            return True

        logging.error(f"Hardware-Fehler: {res_fb.stderr.strip()}")
        return False

    def _set_power_off(self) -> bool:
        """Schaltet den Ausgang sauber ab."""
        output = "HDMI-A-2"
        env = self._get_env()
        self.last_hw_action = datetime.now()

        logging.info(f"Schalte Hardware {output} AUS.")
        res = subprocess.run(["wlr-randr", "--output", output, "--off"],
                             env=env, capture_output=True, text=True)
        return res.returncode == 0

    def _init_sequence(self):
        """Wartet beim Booten auf die Verfügbarkeit des Grafikstacks."""
        time.sleep(45)
        logging.info("Init: Setze Basis-Zustand...")

        # Flag auf True setzen, damit der erste activate() durchkommt
        self._initialized = True
        self.activate()

        time.sleep(5)
        logging.info("Init: System bereit, Repair-Loop aktiv.")

    def _start_browser_script(self):
        if self.start_script:
            logging.info(" Starting browser...")
            try:
                subprocess.Popen(["/bin/bash", self.start_script], env=self._get_env())
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
        """Überwacht permanent den Soll-Zustand von Browser und Hardware."""
        while True:
            time.sleep(20) # Beruhigter Intervall für Langzeit-Stabilität

            if not self._initialized:
                continue

            # Gnadenfrist: Nach einer HW-Aktion 15s lang nicht 'reinpfuschen'
            if datetime.now() < self.last_hw_action + timedelta(seconds=15):
                continue

            # Browser reparieren (wenn nötig)
            if self._repair_browser():
                sleep(3) # Zeit geben vor dem HW-Check

            # Hardware reparieren (wenn nötig)
            self._repair_screen_power()

    def _repair_browser(self) -> bool:
        try:
            if self.screen_on_target_state and not self._is_browser_running():
                logging.warning("Repair: Browser tot. Reanimierung...")
                with self._lock:
                    self._start_browser_script()
                return True
        except Exception as e:
            logging.error(f"Fehler im Browser-Repair: {e}")
        return False

    def _repair_screen_power(self) -> bool:
        try:
            hw_is_on = self._is_screen_power_on()
            if hw_is_on != self.screen_on_target_state:
                logging.warning(f"Repair: HW-Status ({hw_is_on}) entspricht nicht Soll ({self.screen_on_target_state})")
                with self._lock:
                    if self.screen_on_target_state:
                        self._set_power_on()
                    else:
                        self._set_power_off()
                return True
        except Exception as e:
            logging.error(f"Fehler im Screen-Repair: {e}")
        return False