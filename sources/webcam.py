"""
WebcamSource — Source vidéo depuis une webcam locale.

Utilise OpenCV (cv2.VideoCapture) pour capturer le flux
d'une webcam connectée à la machine.

Phase 0 : Première implémentation concrète de VideoSource.
"""

import cv2
import numpy as np
from sources.base import VideoSource


class WebcamSource(VideoSource):
    """Capture vidéo depuis une webcam locale via OpenCV."""

    def __init__(self, camera_index: int = 0):
        """
        Args:
            camera_index: Index de la webcam (0 = défaut système).
        """
        self._camera_index = camera_index
        self._capture: cv2.VideoCapture | None = None

    def open(self) -> bool:
        """Ouvre la webcam."""
        self._capture = cv2.VideoCapture(self._camera_index)
        if not self._capture.isOpened():
            print(f"[ERREUR] Impossible d'ouvrir la webcam (index={self._camera_index})")
            return False
        print(f"[OK] Webcam ouverte (index={self._camera_index})")
        return True

    def read_frame(self) -> tuple[bool, np.ndarray | None]:
        """Lit une frame depuis la webcam."""
        if self._capture is None or not self._capture.isOpened():
            return False, None
        success, frame = self._capture.read()
        if not success:
            return False, None
        return True, frame

    def release(self) -> None:
        """Libère la webcam."""
        if self._capture is not None:
            self._capture.release()
            self._capture = None
            print("[OK] Webcam libérée.")

    def is_opened(self) -> bool:
        """Vérifie si la webcam est ouverte."""
        return self._capture is not None and self._capture.isOpened()

    @property
    def source_name(self) -> str:
        return f"Webcam (index={self._camera_index})"
