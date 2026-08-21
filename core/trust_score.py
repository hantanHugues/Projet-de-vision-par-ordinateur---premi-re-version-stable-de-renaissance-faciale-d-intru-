"""
TrustScore — Moteur MFA (Multi-Factor Authentication) de BioGate.

Gère la machine à états par individu tracké :
  IDLE → ANALYZING → FACE_MATCHED → (FINGERPRINT_PENDING | LIVENESS_PENDING)
       → GRANTED | DENIED | INTRUDER_PENDING → INTRUDER_CONFIRMED

Une instance TrustScoreManager est partagée par api.py.
Elle tient une entrée par object_id actif.
"""

import time
import threading
import config


# ------------------------------------------------------------------ #
#  États possibles                                                     #
# ------------------------------------------------------------------ #
STATE_IDLE                 = "IDLE"
STATE_ANALYZING            = "ANALYZING"
STATE_FACE_MATCHED         = "FACE_MATCHED"        # VIP reconnu, MFA en attente
STATE_FINGERPRINT_PENDING  = "FINGERPRINT_PENDING" # Lecteur réveillé, attend doigt
STATE_LIVENESS_PENDING     = "LIVENESS_PENDING"    # Challenge sourire/clignement en cours
STATE_GRANTED              = "GRANTED"             # Accès autorisé
STATE_DENIED               = "DENIED"              # Accès refusé (timeout MFA)
STATE_INTRUDER_PENDING     = "INTRUDER_PENDING"    # Intrus provisoire, grâce en cours
STATE_INTRUDER_CONFIRMED   = "INTRUDER_CONFIRMED"  # Alerte envoyée


class TrustScore:
    """État MFA pour UN individu tracké (un object_id)."""

    def __init__(self, object_id, on_intruder_confirmed=None):
        self.object_id = object_id
        self._on_intruder_confirmed = on_intruder_confirmed  # callback(object_id, snapshot_path)

        self.state         = STATE_IDLE
        self.vip_name      = None
        self.score         = 0          # % courant (0-100)
        self.snapshot_path = None       # chemin forensic si intrus

        self._state_entered_at = time.time()
        self._grace_timer      = None   # threading.Timer pour l'alerte différée
        self._lock             = threading.Lock()

    # ---------------------------------------------------------------- #
    #  Lecture de la config effective (DB > config.py)                  #
    # ---------------------------------------------------------------- #

    def _cfg(self, key):
        """Lit la config depuis le module config (déjà chargé en mémoire)."""
        return getattr(config, key)

    # ---------------------------------------------------------------- #
    #  Transitions publiques                                            #
    # ---------------------------------------------------------------- #

    def start_analyzing(self):
        with self._lock:
            self.state = STATE_ANALYZING
            self._state_entered_at = time.time()

    def face_matched(self, vip_name, confidence_pct):
        """VIP reconnu par FaceNet512. Démarre la phase MFA si nécessaire."""
        with self._lock:
            self.vip_name = vip_name
            self.score    = round(float(confidence_pct), 1)  # float() : numpy float32 n'est pas JSON-serializable
            mfa_required  = self._cfg("MFA_REQUIRED")

            if not mfa_required:
                self.state = STATE_GRANTED
                # On garde le vrai score FaceNet — il fluctuera à chaque update_score()
            else:
                self.state = STATE_FINGERPRINT_PENDING
                self._state_entered_at = time.time()

    def update_score(self, confidence_pct):
        """Met à jour le score en direct (appelé à chaque RECHECK) sans changer l'état."""
        with self._lock:
            if self.state in (STATE_GRANTED, STATE_FACE_MATCHED, STATE_FINGERPRINT_PENDING):
                self.score = round(float(confidence_pct), 1)

    def request_liveness(self):
        """Bascule de FINGERPRINT_PENDING vers LIVENESS_PENDING (mains occupées)."""
        with self._lock:
            if self.state == STATE_FINGERPRINT_PENDING:
                if not self._cfg("LIVENESS_ENABLED"):
                    return  # liveness désactivé dans la config → on reste en attente empreinte
                self.state = STATE_LIVENESS_PENDING
                self._state_entered_at = time.time()

    def fingerprint_confirmed(self):
        """L'ESP32 confirme que l'empreinte correspond → accès 100%."""
        with self._lock:
            if self.state == STATE_FINGERPRINT_PENDING:
                self.state = STATE_GRANTED
                self.score = self._cfg("TRUST_FINGERPRINT_THRESHOLD")

    def fingerprint_failed(self):
        """L'empreinte ne correspond pas → accès refusé."""
        with self._lock:
            if self.state == STATE_FINGERPRINT_PENDING:
                self.state = STATE_DENIED
                self.score = 0

    def liveness_success(self):
        """Challenge sourire/clignement réussi → accès 85%."""
        with self._lock:
            if self.state == STATE_LIVENESS_PENDING:
                self.state = STATE_GRANTED
                self.score = self._cfg("TRUST_LIVENESS_THRESHOLD")

    def liveness_failed(self):
        """Challenge échoué ou timeout → accès refusé."""
        with self._lock:
            if self.state == STATE_LIVENESS_PENDING:
                self.state = STATE_DENIED
                self.score = 0

    def intruder_detected(self, snapshot_path=None):
        """
        Individu classé intrus provisoire. Démarre la fenêtre de grâce.
        Si aucun VIP n'est confirmé avant expiration → INTRUDER_CONFIRMED.
        """
        with self._lock:
            if self.state in (STATE_INTRUDER_PENDING, STATE_INTRUDER_CONFIRMED):
                return  # déjà en cours
            self.state         = STATE_INTRUDER_PENDING
            self.snapshot_path = snapshot_path
            self._state_entered_at = time.time()

            grace = self._cfg("ALERT_GRACE_PERIOD")
            self._grace_timer = threading.Timer(grace, self._grace_expired)
            self._grace_timer.daemon = True
            self._grace_timer.start()

    def cancel_intruder_alert(self):
        """
        Annule l'alerte provisoire si un VIP est confirmé dans la fenêtre de grâce.
        Retourne True si l'annulation a pu se faire, False si trop tard.
        """
        with self._lock:
            if self.state == STATE_INTRUDER_PENDING:
                if self._grace_timer:
                    self._grace_timer.cancel()
                    self._grace_timer = None
                self.state = STATE_ANALYZING  # repart en analyse propre
                return True
            return False

    def check_mfa_timeout(self):
        """
        À appeler périodiquement depuis face_recognizer pour détecter les timeouts MFA.
        Retourne True si un timeout vient d'être déclenché.
        """
        with self._lock:
            elapsed = time.time() - self._state_entered_at
            if self.state == STATE_FINGERPRINT_PENDING:
                if elapsed > self._cfg("FINGERPRINT_TIMEOUT"):
                    self.state = STATE_DENIED
                    return True
            elif self.state == STATE_LIVENESS_PENDING:
                if elapsed > self._cfg("LIVENESS_CHALLENGE_TIMEOUT"):
                    self.state = STATE_DENIED
                    return True
        return False

    # ---------------------------------------------------------------- #
    #  Lecture                                                           #
    # ---------------------------------------------------------------- #

    def get_state(self):
        with self._lock:
            return {
                "state":         self.state,
                "score":         self.score,
                "vip_name":      self.vip_name,
                "snapshot_path": self.snapshot_path,
                "elapsed":       round(time.time() - self._state_entered_at, 1),
            }

    def is_access_granted(self):
        with self._lock:
            return self.state == STATE_GRANTED

    def is_intruder_confirmed(self):
        with self._lock:
            return self.state == STATE_INTRUDER_CONFIRMED

    def cleanup(self):
        """Annule les timers en suspens quand l'individu quitte le champ."""
        with self._lock:
            if self._grace_timer:
                self._grace_timer.cancel()
                self._grace_timer = None

    # ---------------------------------------------------------------- #
    #  Callback interne — grâce expirée                                 #
    # ---------------------------------------------------------------- #

    def _grace_expired(self):
        with self._lock:
            if self.state == STATE_INTRUDER_PENDING:
                self.state = STATE_INTRUDER_CONFIRMED
        if self._on_intruder_confirmed:
            self._on_intruder_confirmed(self.object_id, self.snapshot_path)


# ------------------------------------------------------------------ #
#  Manager global — une entrée par object_id actif                    #
# ------------------------------------------------------------------ #

class TrustScoreManager:
    """
    Registre centralisé des TrustScore actifs.
    Utilisé comme singleton dans api.py.
    """

    def __init__(self, on_intruder_confirmed=None):
        self._scores = {}          # {object_id: TrustScore}
        self._lock   = threading.Lock()
        self._on_intruder_confirmed = on_intruder_confirmed

    def get_or_create(self, object_id) -> TrustScore:
        with self._lock:
            if object_id not in self._scores:
                self._scores[object_id] = TrustScore(
                    object_id,
                    on_intruder_confirmed=self._on_intruder_confirmed,
                )
            return self._scores[object_id]

    def get(self, object_id):
        with self._lock:
            return self._scores.get(object_id)

    def remove(self, object_id):
        with self._lock:
            ts = self._scores.pop(object_id, None)
            if ts:
                ts.cleanup()

    def remove_lost(self, active_ids):
        """Nettoie les entrées dont l'objet a disparu de l'écran."""
        with self._lock:
            lost = [oid for oid in self._scores if oid not in active_ids]
        for oid in lost:
            self.remove(oid)

    def get_all_states(self):
        """Retourne un snapshot de tous les états — utilisé par /access_status."""
        with self._lock:
            return {oid: ts.get_state() for oid, ts in self._scores.items()}

    def cancel_intruder_if_vip_nearby(self):
        """
        Appelé dès qu'un VIP est GRANTED dans la session.
        Annule tous les INTRUDER_PENDING actifs (le VIP n'était pas encore reconnu).
        """
        with self._lock:
            pending = [ts for ts in self._scores.values()
                       if ts.state == STATE_INTRUDER_PENDING]
        for ts in pending:
            ts.cancel_intruder_alert()
