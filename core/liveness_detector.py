"""
LivenessDetector v3 — MediaPipe FaceLandmarker + Blendshapes natifs.

Utilise les 52 valeurs blendshapes pré-calculées par le modèle Google
(valeurs 0→1) au lieu de calculer EAR/MAR à la main.

Blendshapes clés :
  eyeBlinkLeft  / eyeBlinkRight  → 0 = ouvert, 1 = fermé
  mouthSmileLeft / mouthSmileRight → 0 = neutre, 1 = sourire maximal

Challenge-response ALÉATOIRE : à la création de la session, UN SEUL des deux
gestes (sourire OU clignement) est tiré au sort et devient le seul accepté
pour ce challenge. Avant v3, les deux étaient acceptés indifféremment — un
visage filmé en boucle (vidéo, deepfake) peut cligner des yeux par hasard à
un moment ou un autre, ce qui validait le challenge sans jamais avoir posé
de VRAIE question imprévisible. Exiger un geste précis, choisi après coup et
annoncé à l'instant T, est ce qui rend le test réellement anti-spoofing
plutôt qu'un simple "y a-t-il du mouvement sur ce visage ?".

Les PARAMÈTRES du geste sont eux aussi tirés au sort par session (nombre de
clignements requis, durée de maintien du sourire) — pas juste le type de
geste. Des valeurs fixes et connues (toujours 2 clignements, toujours 1,2s
de sourire) sont exactement ce qu'une vidéo générique préparée à l'avance
peut viser ; les faire varier à chaque tentative, dans une fourchette qui
reste rapide pour un utilisateur légitime, rend le test bien plus difficile
à rejouer sans être réellement présent et réactif.

Modèle requis : models/face_landmarker.task (3.6 MB, téléchargé une fois)
"""

import time
import os
import random
import config

LIVENESS_PENDING = "PENDING"
LIVENESS_SUCCESS = "SUCCESS"
LIVENESS_FAILED  = "FAILED"
LIVENESS_TIMEOUT = "TIMEOUT"

CHALLENGE_BLINK = "blink"
CHALLENGE_SMILE = "smile"

MODEL_PATH = "models/face_landmarker.task"

# ------------------------------------------------------------------ #
#  Seuils blendshapes                                                  #
# ------------------------------------------------------------------ #
BLINK_THRESHOLD = 0.35   # score > 0.35 = œil significativement fermé
BLINK_HOLD_MIN  = 1      # 1 frame suffit — le client envoie à ~5fps (200ms/frame), un clignement dure 100-200ms

# Nombre de clignements requis : tiré au sort par session dans cette
# fourchette (voir __init__) plutôt qu'une valeur fixe toujours identique.
BLINKS_REQUIRED_MIN = 2
BLINKS_REQUIRED_MAX = 4

SMILE_THRESHOLD      = 0.40   # abaissé de 0.45 → les pics réels sont 0.60-0.75, marge confortable
SMILE_EXIT_THRESHOLD = 0.25   # hysterèse : le timer ne se réinitialise que si smile descend vraiment bas

# Durée de maintien du sourire : tirée au sort par session dans cette
# fourchette (secondes) — jamais la même durée exacte deux fois de suite.
SMILE_HOLD_MIN = 1.0
SMILE_HOLD_MAX = 2.0


class LivenessDetector:
    """
    Détecteur de vivacité par blendshapes (anti-spoofing actif).
    Une instance par session MFA (par object_id) — le challenge (sourire OU
    clignement) est tiré au sort une seule fois, à la création.
    """

    def __init__(self):
        self._started_at = time.time()
        self._result     = LIVENESS_PENDING
        self._challenge  = random.choice([CHALLENGE_BLINK, CHALLENGE_SMILE])

        # Paramètres du geste tirés au sort à la création — voir docstring
        # du module. Un nombre/une durée fixe et connue à l'avance est ce
        # qu'une vidéo générique peut viser ; les faire varier par tentative
        # rend le rejeu bien plus difficile sans coûter de temps réel à un
        # utilisateur légitime (les bornes restent volontairement courtes).
        self._blinks_required = random.randint(BLINKS_REQUIRED_MIN, BLINKS_REQUIRED_MAX)
        self._smile_hold_sec  = round(random.uniform(SMILE_HOLD_MIN, SMILE_HOLD_MAX), 2)

        # État clignement
        self._blink_count  = 0
        self._blink_frames = 0    # frames consécutives où l'œil est fermé
        self._in_blink     = False

        # État sourire
        self._smile_start  = None

        # Dernières valeurs brutes blendshapes (0→1), pour l'affichage debug
        self._last_blink = 0.0
        self._last_smile = 0.0

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
    #  Évaluation du SEUL challenge tiré au sort                        #
    # ---------------------------------------------------------------- #

    def _evaluate(self, blink: float, smile: float) -> str:
        """
        N'évalue QUE self._challenge — l'autre geste, même parfaitement
        exécuté, ne valide rien. C'est ce qui fait que la question posée à
        l'instant T est effectivement celle qui doit être satisfaite.
        """
        # Valeurs brutes conservées pour l'affichage debug (dashboard) —
        # comme les barres blink/smile de client_camera.py en mode debug (T).
        self._last_blink = blink
        self._last_smile = smile

        if self._challenge == CHALLENGE_BLINK:
            if blink > BLINK_THRESHOLD:
                self._blink_frames += 1
                self._in_blink = True
            else:
                if self._in_blink and self._blink_frames >= BLINK_HOLD_MIN:
                    self._blink_count += 1
                    if self._blink_count >= self._blinks_required:
                        self._result = LIVENESS_SUCCESS
                self._blink_frames = 0
                self._in_blink     = False

        else:  # CHALLENGE_SMILE
            if smile > SMILE_THRESHOLD:
                if self._smile_start is None:
                    self._smile_start = time.time()
                elif time.time() - self._smile_start >= self._smile_hold_sec:
                    self._result = LIVENESS_SUCCESS
            elif smile < SMILE_EXIT_THRESHOLD:
                self._smile_start = None

        return self._result

    # ---------------------------------------------------------------- #
    #  Analyse d'une frame                                              #
    # ---------------------------------------------------------------- #

    def check(self, frame_bgr):
        """
        Analyse une frame BGR et retourne l'état du challenge.
        À appeler à chaque frame tant que le résultat est PENDING.

        Retourne : PENDING | SUCCESS | FAILED | TIMEOUT
        """
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
        bs    = {b.category_name: b.score for b in result.face_blendshapes[0]}
        blink = (bs.get("eyeBlinkLeft", 0) + bs.get("eyeBlinkRight", 0)) / 2
        smile = (bs.get("mouthSmileLeft", 0) + bs.get("mouthSmileRight", 0)) / 2

        return self._evaluate(blink, smile)

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

        return self._evaluate(blink_score, smile_score)

    # ---------------------------------------------------------------- #
    #  État pour l'UI                                                    #
    # ---------------------------------------------------------------- #

    def expired(self, grace_factor: float = 3.0) -> bool:
        """
        True si la session traîne depuis largement plus longtemps que le
        challenge ne devrait durer — sert à purger les sessions abandonnées
        (personne sortie du cadre) sans dépendre de la liste des IDs actifs
        d'une caméra en particulier (object_id est partagé entre caméras).
        """
        elapsed = time.time() - self._started_at
        return elapsed > config.LIVENESS_CHALLENGE_TIMEOUT * grace_factor

    def challenge_label(self) -> str:
        """
        Instruction humaine du geste réellement attendu pour CE challenge —
        construite dynamiquement puisque le nombre de clignements varie
        d'une tentative à l'autre (voir __init__).
        """
        if self._challenge == CHALLENGE_BLINK:
            return f"CLIGNEZ DES YEUX (x{self._blinks_required})"
        return "SOURIEZ"

    def get_progress(self):
        """Retourne un dict d'état pour l'affichage client."""
        remaining = max(
            0,
            config.LIVENESS_CHALLENGE_TIMEOUT - (time.time() - self._started_at)
        )
        return {
            "result":           self._result,
            "challenge":        self._challenge,
            "challenge_label":  self.challenge_label(),
            "blinks":           self._blink_count,
            "blinks_required":  self._blinks_required,
            "smiling":          self._smile_start is not None,
            "remaining":        round(remaining, 1),
            # Valeurs brutes + seuils — même affichage que le mode debug (T)
            # de client_camera.py, mais accessible depuis le dashboard.
            "blink_score":      round(self._last_blink, 3),
            "smile_score":      round(self._last_smile, 3),
            "blink_threshold":  BLINK_THRESHOLD,
            "smile_threshold":  SMILE_THRESHOLD,
        }

    # ---------------------------------------------------------------- #
    #  Libération des ressources                                        #
    # ---------------------------------------------------------------- #

    def release(self):
        if self._landmarker:
            self._landmarker.close()
            self._landmarker = None
