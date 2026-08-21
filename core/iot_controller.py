"""
IoTController — Couche de communication vers les actionneurs ESP32.

Quand IOT_ENABLED=False : mode mock — toutes les commandes sont simulées
localement et tracées dans les logs. Rien n'est envoyé sur le réseau.

Quand IOT_ENABLED=True  : signaux HTTP GET envoyés aux ESP32 sur le LAN.
Les ESP32 exposent des routes simples : /open, /close, /wake, /light/welcome…

Architecture des modules IoT attendus :
  - Lecteur d'empreinte  → GET http://[FINGERPRINT_ESP32_IP]/wake
                           GET http://[FINGERPRINT_ESP32_IP]/sleep
  - Gâche électrique     → GET http://[DOOR_ESP32_IP]/open
                           GET http://[DOOR_ESP32_IP]/close
  - Éclairage d'accueil  → GET http://[LIGHT_ESP32_IP]/welcome
                           GET http://[LIGHT_ESP32_IP]/alert
                           GET http://[LIGHT_ESP32_IP]/off
"""

import time
import threading
import requests
import config


# États possibles de la porte (pour l'UI)
DOOR_LOCKED = "LOCKED"
DOOR_OPEN   = "OPEN"

# États du lecteur d'empreinte
FP_IDLE     = "IDLE"
FP_WAITING  = "WAITING"
FP_OK       = "OK"
FP_FAIL     = "FAIL"

# États de l'éclairage
LIGHT_OFF     = "OFF"
LIGHT_WELCOME = "WELCOME"
LIGHT_ALERT   = "ALERT"


class IoTController:
    """
    Contrôleur unique pour tous les actionneurs du système BioGate.
    Instancié une seule fois dans api.py.
    """

    def __init__(self, logger=None):
        self.logger      = logger
        self._door_state = DOOR_LOCKED
        self._fp_state   = FP_IDLE
        self._light_state = LIGHT_OFF
        self._door_timer  = None   # timer pour refermer la porte automatiquement
        self._lock        = threading.Lock()

    # ---------------------------------------------------------------- #
    #  Propriétés d'état — pour l'UI et /access_status                 #
    # ---------------------------------------------------------------- #

    @property
    def door_state(self):
        return self._door_state

    @property
    def fingerprint_state(self):
        return self._fp_state

    @property
    def light_state(self):
        return self._light_state

    def get_status(self):
        """Snapshot de l'état de tous les actionneurs."""
        return {
            "door":        self._door_state,
            "fingerprint": self._fp_state,
            "light":       self._light_state,
            "iot_enabled": config.IOT_ENABLED,
        }

    # ---------------------------------------------------------------- #
    #  Lecteur d'empreinte                                              #
    # ---------------------------------------------------------------- #

    def wake_fingerprint(self):
        """Réveille le lecteur et le met en mode attente."""
        with self._lock:
            self._fp_state = FP_WAITING
        self._log("info", "[IoT] Lecteur d'empreinte : EN ATTENTE")
        self._send(config.FINGERPRINT_ESP32_IP, "/wake")

    def sleep_fingerprint(self):
        """Rendort le lecteur (après timeout ou résultat)."""
        with self._lock:
            self._fp_state = FP_IDLE
        self._log("info", "[IoT] Lecteur d'empreinte : EN VEILLE")
        self._send(config.FINGERPRINT_ESP32_IP, "/sleep")

    def fingerprint_result(self, success: bool):
        """Met à jour l'état visuel suite au retour de l'ESP32."""
        with self._lock:
            self._fp_state = FP_OK if success else FP_FAIL
        # Après 3s, retour en veille automatique
        threading.Timer(3.0, self.sleep_fingerprint).start()

    # ---------------------------------------------------------------- #
    #  Gâche électrique                                                 #
    # ---------------------------------------------------------------- #

    def open_door(self, auto_close_seconds=5):
        """
        Ouvre la gâche électrique.
        Se referme automatiquement après auto_close_seconds.
        """
        with self._lock:
            self._door_state = DOOR_OPEN
            if self._door_timer:
                self._door_timer.cancel()
        self._log("info", f"[IoT] Porte : OUVERTE (refermeture dans {auto_close_seconds}s)")
        self._send(config.DOOR_ESP32_IP, "/open")
        self._door_timer = threading.Timer(auto_close_seconds, self.close_door)
        self._door_timer.daemon = True
        self._door_timer.start()

    def close_door(self):
        """Ferme et verrouille la gâche."""
        with self._lock:
            self._door_state = DOOR_LOCKED
        self._log("info", "[IoT] Porte : VERROUILLÉE")
        self._send(config.DOOR_ESP32_IP, "/close")

    def toggle_door(self):
        """Bascule l'état de la porte (utile pour les tests depuis le terminal)."""
        if self._door_state == DOOR_LOCKED:
            self.open_door()
        else:
            self.close_door()

    # ---------------------------------------------------------------- #
    #  Éclairage d'accueil                                              #
    # ---------------------------------------------------------------- #

    def set_light_welcome(self):
        """Lumière verte d'accueil — VIP reconnu."""
        with self._lock:
            self._light_state = LIGHT_WELCOME
        self._log("info", "[IoT] Éclairage : ACCUEIL (vert)")
        self._send(config.LIGHT_ESP32_IP, "/welcome")

    def set_light_alert(self):
        """Lumière rouge clignotante — intrus confirmé."""
        with self._lock:
            self._light_state = LIGHT_ALERT
        self._log("info", "[IoT] Éclairage : ALERTE (rouge)")
        self._send(config.LIGHT_ESP32_IP, "/alert")

    def set_light_off(self):
        """Éteindre l'éclairage."""
        with self._lock:
            self._light_state = LIGHT_OFF
        self._log("info", "[IoT] Éclairage : ÉTEINT")
        self._send(config.LIGHT_ESP32_IP, "/off")

    # ---------------------------------------------------------------- #
    #  Envoi HTTP vers ESP32                                            #
    # ---------------------------------------------------------------- #

    def _send(self, ip, path):
        """
        Envoie la commande HTTP à l'ESP32.
        En mode mock (IOT_ENABLED=False) : log seulement, pas de requête réseau.
        Toujours non-bloquant (timeout 1s, dans un thread séparé).
        """
        if not config.IOT_ENABLED:
            self._log("info", f"[IoT MOCK] → http://{ip}{path}")
            return

        url = f"http://{ip}{path}"

        def _fire():
            try:
                resp = requests.get(url, timeout=1.0)
                self._log("info", f"[IoT] {url} → {resp.status_code}")
            except requests.exceptions.RequestException as e:
                self._log("error", f"[IoT] {url} injoignable : {e}")

        t = threading.Thread(target=_fire, daemon=True)
        t.start()

    # ---------------------------------------------------------------- #
    #  Logging                                                          #
    # ---------------------------------------------------------------- #

    def _log(self, level, msg):
        if self.logger:
            getattr(self.logger, level)(msg)
        else:
            print(f"[{level.upper()}] {msg}")
