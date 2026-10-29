"""
CameraManager — moteur multi-sources vidéo pour BioGate.

Gère des sources hétérogènes en parallèle :
  - usb   : webcam locale (auto-détectée via scan OpenCV)
  - mjpeg : flux HTTP MJPEG (BW21-CBV, caméra IP)
  - rtsp  : caméra IP standard
  - file  : fichier vidéo (tests/démo)

Chaque source tourne dans son propre thread daemon.
Le callback on_frame(cam_id, frame_bgr) est appelé à chaque frame capturé
pour déclencher le pipeline IA (YOLO → FaceNet → TrustScore).
"""

import cv2
import threading
import time
import platform
from typing import Optional, Dict, Callable, List

import config


def mirror_annotations(annotations: list, frame_width: int) -> list:
    """Annotations (oid, x1, y1, x2, y2, nom, score, état) pour une image retournée à l'horizontale."""
    return [
        (oid, frame_width - x2, y1, frame_width - x1, y2, *rest)
        for oid, x1, y1, x2, y2, *rest in annotations
    ]


class CameraSource:
    """Thread de capture pour une source vidéo unique."""

    def __init__(self, cam_id: str, cfg: dict, on_frame: Callable, draw_fn: Optional[Callable] = None):
        self.cam_id    = cam_id
        self.name      = cfg.get("name", cam_id)
        self.cam_type  = cfg.get("type", "usb")
        self.url       = cfg.get("url", "")
        self.usb_index = int(cfg.get("usb_index", 0))
        self.zone      = cfg.get("zone", "")

        self._on_frame = on_frame
        # draw_fn(frame_bgr, annotations, cam_id, cam_name) -> frame_bgr annoté.
        # Appelé à CHAQUE frame capturée (vitesse caméra), avec les dernières
        # annotations connues — voir set_annotations(). Le pipeline IA tourne
        # bien plus lentement (2-5 fps sur CPU) dans un thread séparé ; sans ce
        # découplage, le flux affiché n'avance qu'au rythme de l'IA et saccade.
        self._draw_fn    = draw_fn
        self._annotations: list = []
        self._running    = False
        self._thread: Optional[threading.Thread] = None
        self._cap:    Optional[cv2.VideoCapture]  = None
        self._lock       = threading.Lock()
        self._last_jpg:  Optional[bytes] = None   # dernière frame affichée (brute + annotations en cache)

        self.connected  = False
        self.fps_actual = 0.0
        self._fps_ctr   = 0
        # F5 : time.monotonic() — garanti croissant, insensible aux ajustements NTP
        self._fps_ts    = time.monotonic()

    # ── Cycle de vie ──────────────────────────────────────────────────

    def start(self):
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop, daemon=True, name=f"cam-{self.cam_id}"
        )
        self._thread.start()

    def stop(self):
        self._running = False
        if self._cap:
            self._cap.release()

    # ── Ouverture de la source ────────────────────────────────────────

    def _open(self) -> Optional[cv2.VideoCapture]:
        if self.cam_type == "usb":
            # CAP_DSHOW sur Windows pour éviter les délais d'init COM
            backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
            cap = cv2.VideoCapture(self.usb_index, backend)
        else:
            # mjpeg / rtsp / file → OpenCV lit l'URL directement
            cap = cv2.VideoCapture(self.url)

        if cap.isOpened():
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # latence minimale
            return cap
        cap.release()
        return None

    # ── Boucle de capture ─────────────────────────────────────────────

    def _loop(self):
        while self._running:
            # Reconnexion automatique si la source est perdue
            if self._cap is None or not self._cap.isOpened():
                self.connected = False
                self._cap = self._open()
                if self._cap is None:
                    time.sleep(3)
                    continue

            ret, frame = self._cap.read()
            if not ret:
                self.connected = False
                self._cap.release()
                self._cap = None
                time.sleep(1)
                continue

            self.connected = True

            # Compteur FPS réel — F5 : monotonic() pour la mesure de durée
            self._fps_ctr += 1
            now = time.monotonic()
            if now - self._fps_ts >= 1.0:
                self.fps_actual = self._fps_ctr / (now - self._fps_ts)
                self._fps_ctr   = 0
                self._fps_ts    = now

            display_frame = self._render(frame)

            ok, jpg = cv2.imencode(".jpg", display_frame, [cv2.IMWRITE_JPEG_QUALITY, 78])
            if ok:
                with self._lock:
                    self._last_jpg = jpg.tobytes()

            # Le rate-limiting est assuré par queue.Queue(maxsize=4) côté api.py.
            # _cam_on_frame fait put_nowait() — si la queue est pleine le frame
            # est silencieusement abandonné. Ce thread ne bloque jamais.
            if self._on_frame:
                try:
                    self._on_frame(self.cam_id, frame)
                except Exception:
                    pass

    def _render(self, frame):
        """
        Image affichée au dashboard : dernières annotations connues dessinées sur la frame
        fraîche (capturée à la vitesse caméra, pas à celle de l'IA).

        Une webcam locale renvoie souvent l'image en miroir (la main droite apparaît à droite,
        comme dans un selfie). On la remet à l'endroit ICI, à l'affichage seulement : l'image
        envoyée au pipeline IA reste celle de la caméra, donc la reconnaissance, les distances
        mesurées et les photos d'intrus ne changent pas. Les cadres sont retournés avec l'image,
        le texte est dessiné après le retournement et reste lisible.
        """
        flip = self.cam_type == "usb" and config.DISPLAY_FLIP_HORIZONTAL_USB
        display_frame = cv2.flip(frame, 1) if flip else frame
        if self._draw_fn:
            with self._lock:
                annotations = self._annotations
            if flip:
                annotations = mirror_annotations(annotations, frame.shape[1])
            try:
                display_frame = self._draw_fn(display_frame, annotations, self.cam_id, self.name)
            except Exception:
                pass
        return display_frame

    # ── Accès aux frames ──────────────────────────────────────────────

    def set_annotations(self, annotations: list):
        """
        Appelé par le pipeline IA (thread séparé, 2-5 fps) pour mettre à jour
        les dernières boîtes/scores connus. Ne dessine ni n'encode rien ici —
        juste un cache lu par _loop() à la prochaine frame capturée.
        """
        with self._lock:
            self._annotations = annotations

    def get_stream_jpg(self) -> Optional[bytes]:
        """Retourne la dernière frame affichée (brute + annotations en cache)."""
        with self._lock:
            return self._last_jpg

    def info(self) -> dict:
        return {
            "cam_id":    self.cam_id,
            "name":      self.name,
            "type":      self.cam_type,
            "url":       self.url,
            "usb_index": self.usb_index,
            "zone":      self.zone,
            "connected": self.connected,
            "fps":       round(self.fps_actual, 1),
        }


class CameraManager:
    """Gestionnaire de toutes les sources vidéo actives du système."""

    def __init__(self, on_frame: Callable, draw_fn: Optional[Callable] = None):
        """
        on_frame(cam_id: str, frame_bgr: np.ndarray)
        Appelé à chaque frame capturé pour déclencher le pipeline IA.

        draw_fn(frame_bgr, annotations, cam_id, cam_name) -> frame_bgr
        Optionnel : dessine les dernières annotations connues sur la frame
        affichée. Transmis à chaque CameraSource — voir set_annotations().
        """
        self._on_frame = on_frame
        self._draw_fn  = draw_fn
        self._sources: Dict[str, CameraSource] = {}
        self._lock     = threading.Lock()

    # ── Gestion des sources ───────────────────────────────────────────

    def add(self, cam_id: str, cfg: dict, start: bool = True) -> CameraSource:
        """Ajoute ou remplace une source. La démarre automatiquement si start=True."""
        with self._lock:
            if cam_id in self._sources:
                self._sources[cam_id].stop()
            src = CameraSource(cam_id, cfg, self._on_frame, draw_fn=self._draw_fn)
            self._sources[cam_id] = src
        if start:
            src.start()
        return src

    def remove(self, cam_id: str):
        """Arrête et retire une source."""
        with self._lock:
            src = self._sources.pop(cam_id, None)
        if src:
            src.stop()

    def get(self, cam_id: str) -> Optional[CameraSource]:
        return self._sources.get(cam_id)

    def all_info(self) -> List[dict]:
        with self._lock:
            return [src.info() for src in self._sources.values()]

    def set_annotations(self, cam_id: str, annotations: list):
        src = self._sources.get(cam_id)
        if src:
            src.set_annotations(annotations)

    def stop_all(self):
        with self._lock:
            for src in self._sources.values():
                src.stop()
            self._sources.clear()

    # ── Auto-détection USB ────────────────────────────────────────────

    @staticmethod
    def scan_usb(max_index: int = 4) -> List[dict]:
        """
        Sonde les indices USB 0..max_index-1 et retourne les webcams disponibles.

        Sur Windows, CAP_DSHOW (~100ms/indice) est bien plus rapide que MSMF (~3s/indice).
        max_index=4 couvre la quasi-totalité des cas réels tout en restant rapide.
        """
        backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
        found   = []
        for i in range(max_index):
            try:
                cap = cv2.VideoCapture(i, backend)
                if cap.isOpened():
                    # Lire un frame pour confirmer que la caméra est vraiment opérationnelle
                    ret, _ = cap.read()
                    if ret:
                        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        found.append({
                            "usb_index":  i,
                            "resolution": f"{w}x{h}",
                            "label":      f"Webcam USB #{i}  ({w}x{h})",
                        })
                    cap.release()
            except Exception:
                pass   # indice inexistant ou accès refusé — on continue
        return found
