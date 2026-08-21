"""
LivenessDetector v2 — MediaPipe FaceLandmarker + Blendshapes natifs.

Utilise les 52 valeurs blendshapes pré-calculées par le modèle Google
(valeurs 0→1) au lieu de calculer EAR/MAR à la main.

Blendshapes clés :
  eyeBlinkLeft  / eyeBlinkRight  → 0 = ouvert, 1 = fermé
  mouthSmileLeft / mouthSmileRight → 0 = neutre, 1 = sourire maximal

Challenge : 2 clignements complets  OU  sourire tenu 1.5s  → SUCCESS
Un seul des deux suffit.

Modèle requis : models/face_landmarker.task (3.6 MB, téléchargé une fois)
"""

import time
import os
import config

LIVENESS_PENDING = "PENDING"
LIVENESS_SUCCESS = "SUCCESS"
LIVENESS_FAILED  = "FAILED"
LIVENESS_TIMEOUT = "TIMEOUT"

MODEL_PATH = "models/face_landmarker.task"

# ------------------------------------------------------------------ #
#  Seuils blendshapes                                                  #
# ------------------------------------------------------------------ #
BLINK_THRESHOLD = 0.35   # score > 0.35 = œil significativement fermé
BLINK_HOLD_MIN  = 1      # 1 frame suffit — le client envoie à ~5fps (200ms/frame), un clignement dure 100-200ms
BLINKS_REQUIRED = 2      # nombre de clignements complets pour réussir

SMILE_THRESHOLD      = 0.40   # abaissé de 0.45 → les pics réels sont 0.60-0.75, marge confortable
SMILE_EXIT_THRESHOLD = 0.25   # hysterèse : le timer ne se réinitialise que si smile descend vraiment bas
SMILE_HOLD_SEC       = 1.2    # réduit de 1.5s → compense les micro-dips à 5fps


class LivenessDetector:
    """
    Détecteur de vivacité par blendshapes (anti-spoofing actif).
    Une instance par session MFA (par object_id).
    """

    def __init__(self):
        self._started_at = time.time()
        self._result     = LIVENESS_PENDING

        # État clignement
        self._blink_count  = 0
        self._blink_frames = 0    # frames consécutives où l'œil est fermé
        self._in_blink     = False

        # État sourire
        self._smile_start  = None

        # FaceLandmarker (Tasks API)
        self._landmarker = None
        self._mp         = None
        self._ready      = False
        self._load_model()

    # ---------------------------------------------------------------- #
    #  Chargement du modèle                                             #
    # ---------------------------------------------------------------- #

    def _load_model(self):
        if not os.path.exists(MODEL_PATH):
            print(f"[LivenessDetector] Modèle absent : {MODEL_PATH}")
            print("[LivenessDetector] Téléchargez-le depuis Google Storage (voir README).")
            return
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision

            base_options = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
            options = mp_vision.FaceLandmarkerOptions(
                base_options=base_options,
                output_face_blendshapes=True,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._landmarker = mp_vision.FaceLandmarker.create_from_options(options)
            self._mp    = mp
            self._ready = True

        except Exception as e:
            self._ready = False
            print(f"[LivenessDetector] Erreur chargement modèle : {e}")

    # ---------------------------------------------------------------- #
    #  Analyse d'une frame                                              #
    # ---------------------------------------------------------------- #

    def check(self, frame_bgr):
        """
        Analyse une frame BGR et retourne l'état du challenge.
        À appeler à chaque frame tant que le résultat est PENDING.

        Retourne : PENDING | SUCCESS | FAILED | TIMEOUT
        """
        # Timeout global
        elapsed = time.time() - self._started_at
        if elapsed > config.LIVENESS_CHALLENGE_TIMEOUT:
            if self._result == LIVENESS_PENDING:
                self._result = LIVENESS_TIMEOUT
            return self._result

        if self._result != LIVENESS_PENDING:
            return self._result

        if not self._ready or self._landmarker is None:
            return LIVENESS_PENDING

        import cv2
        rgb    = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect(mp_img)

        if not result.face_blendshapes:
            return LIVENESS_PENDING

        # Dictionnaire {nom_blendshape: score 0→1}
        bs = {b.category_name: b.score for b in result.face_blendshapes[0]}

        # --- Challenge 1 : Clignement ---
        blink = (bs.get("eyeBlinkLeft", 0) + bs.get("eyeBlinkRight", 0)) / 2

        if blink > BLINK_THRESHOLD:
            self._blink_frames += 1
            self._in_blink = True
        else:
            if self._in_blink and self._blink_frames >= BLINK_HOLD_MIN:
                # Clignement complet détecté
                self._blink_count += 1
                if self._blink_count >= BLINKS_REQUIRED:
                    self._result = LIVENESS_SUCCESS
                    return self._result
            self._blink_frames = 0
            self._in_blink     = False

        # --- Challenge 2 : Sourire (avec hystérésis) ---
        smile = (bs.get("mouthSmileLeft", 0) + bs.get("mouthSmileRight", 0)) / 2

        if smile > SMILE_THRESHOLD:
            if self._smile_start is None:
                self._smile_start = time.time()
            elif time.time() - self._smile_start >= SMILE_HOLD_SEC:
                self._result = LIVENESS_SUCCESS
                return self._result
        elif smile < SMILE_EXIT_THRESHOLD:
            # Réinitialise seulement si le sourire s'effondre vraiment (pas un micro-dip)
            self._smile_start = None

        return LIVENESS_PENDING

    def check_values(self, blink_score: float, smile_score: float) -> str:
        """
        Alternative à check() — accepte des scores blendshapes pré-calculés
        par le client (MediaPipe local à 30fps) au lieu d'analyser une frame.
        Même logique que check(), même état interne.
        """
        elapsed = time.time() - self._started_at
        if elapsed > config.LIVENESS_CHALLENGE_TIMEOUT:
            if self._result == LIVENESS_PENDING:
                self._result = LIVENESS_TIMEOUT
            return self._result

        if self._result != LIVENESS_PENDING:
            return self._result

        # Challenge 1 : Clignement
        if blink_score > BLINK_THRESHOLD:
            self._blink_frames += 1
            self._in_blink = True
        else:
            if self._in_blink and self._blink_frames >= BLINK_HOLD_MIN:
                self._blink_count += 1
                if self._blink_count >= BLINKS_REQUIRED:
                    self._result = LIVENESS_SUCCESS
                    return self._result
            self._blink_frames = 0
            self._in_blink     = False

        # Challenge 2 : Sourire (avec hystérésis)
        if smile_score > SMILE_THRESHOLD:
            if self._smile_start is None:
                self._smile_start = time.time()
            elif time.time() - self._smile_start >= SMILE_HOLD_SEC:
                self._result = LIVENESS_SUCCESS
                return self._result
        elif smile_score < SMILE_EXIT_THRESHOLD:
            self._smile_start = None

        return LIVENESS_PENDING

    # ---------------------------------------------------------------- #
    #  État pour l'UI                                                    #
    # ---------------------------------------------------------------- #

    def get_progress(self):
        """Retourne un dict d'état pour l'affichage client."""
        remaining = max(
            0,
            config.LIVENESS_CHALLENGE_TIMEOUT - (time.time() - self._started_at)
        )
        return {
            "result":           self._result,
            "blinks":           self._blink_count,
            "blinks_required":  BLINKS_REQUIRED,
            "smiling":          self._smile_start is not None,
            "remaining":        round(remaining, 1),
        }

    # ---------------------------------------------------------------- #
    #  Libération des ressources                                        #
    # ---------------------------------------------------------------- #

    def release(self):
        if self._landmarker:
            self._landmarker.close()
            self._landmarker = None
