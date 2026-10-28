"""
Tests du Face Gate (Haar) : une seule détection par personne et par image.

Avant le correctif, /analyze_frame lançait Haar à chaque image pour chaque personne
(encadré de l'interface) EN PLUS de celui d'identify(). Désormais identify() mémorise la
position du visage et api.py la réutilise (FaceRecognizer.get_face_box).

Le module api charge YOLO et FaceNet (lent au démarrage). Base SQLite temporaire :
la vraie base biométrique n'est pas touchée. YOLO et FaceNet sont remplacés par des
doubles pour que les tests soient rapides et déterministes.

    .venv-deepface\\Scripts\\python.exe -m unittest tests.test_face_gate -v
"""

import asyncio
import io
import json
import os
import tempfile
import time
import unittest
from unittest import mock

import cv2
import numpy as np

import config

config.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="biogate-test-"), "visages.db")

import api  # noqa: E402  (après la redirection de config.DB_PATH)
from starlette.datastructures import UploadFile  # noqa: E402

PHOTO = os.path.join(os.path.dirname(__file__), "photos_test_apprentissage_continu",
                     "apres1_2019_Chris_Evans_barbe.jpg")
CANVAS_W, CANVAS_H = 640, 480


def load_portrait(max_w=300, max_h=380):
    img = cv2.imread(PHOTO)
    assert img is not None, f"photo de test introuvable : {PHOTO}"
    h, w = img.shape[:2]
    scale = min(max_w / w, max_h / h)
    return cv2.resize(img, (int(w * scale), int(h * scale)))


def place(portrait, x, y):
    """Portrait collé sur un fond noir 640x480 ; retourne (image, bbox silhouette)."""
    canvas = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)
    h, w = portrait.shape[:2]
    canvas[y:y + h, x:x + w] = portrait
    return canvas, [x, y, x + w, y + h]


class CountingCascade:
    """Enveloppe le classifieur Haar et compte les détections demandées."""

    def __init__(self, real):
        self.real = real
        self.calls = 0

    def detectMultiScale(self, *args, **kwargs):
        self.calls += 1
        return self.real.detectMultiScale(*args, **kwargs)


class FaceGateTest(unittest.TestCase):
    def setUp(self):
        self.fr = api.face_recognizer
        self.fr.tracking_states.clear()
        self.fr.identified_ids.clear()
        self.cascade = CountingCascade(self.fr.face_cascade)
        for patcher in (
            mock.patch.object(self.fr, "face_cascade", self.cascade),
            mock.patch.object(self.fr, "_extract_face_signature", return_value=np.ones(512, dtype=np.float32)),
            mock.patch.object(api.cv2, "imwrite", return_value=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.portrait = load_portrait()

    # ── Niveau reconnaisseur ───────────────────────────────────────────

    def test_identify_remembers_the_face_position_found_by_the_face_gate(self):
        frame, bbox = place(self.portrait, 60, 40)
        self.fr.identify(frame, bbox, "p1")
        rel = self.fr.tracking_states["p1"]["face_rel"]
        self.assertIsNotNone(rel, "Haar devrait trouver le visage du portrait de test")
        self.assertGreaterEqual(rel[2], 30)
        self.assertEqual(self.fr.get_face_box("p1", bbox), [60 + rel[0], 40 + rel[1], rel[2], rel[3]])

    def test_no_face_means_no_box(self):
        blank = np.full((CANVAS_H, CANVAS_W, 3), 128, dtype=np.uint8)
        self.fr.identify(blank, [100, 100, 300, 400], "p1")
        self.assertIsNone(self.fr.tracking_states["p1"]["face_rel"])
        self.assertIsNone(self.fr.get_face_box("p1", [100, 100, 300, 400]))

    def test_unknown_individual_has_no_box_and_does_not_crash(self):
        self.assertIsNone(self.fr.get_face_box("jamais-vu", [0, 0, 10, 10]))

    def test_box_follows_the_person_between_two_face_gate_runs(self):
        frame, bbox = place(self.portrait, 60, 40)
        self.fr.identify(frame, bbox, "p1")
        first = self.fr.get_face_box("p1", bbox)
        moved = [bbox[0] + 40, bbox[1] + 30, bbox[2] + 40, bbox[3] + 30]
        self.assertEqual(self.fr.get_face_box("p1", moved), [first[0] + 40, first[1] + 30, first[2], first[3]])
        self.assertEqual(self.cascade.calls, 1, "suivre le mouvement ne doit lancer aucune détection")

    def test_silhouette_partly_outside_the_image_uses_the_same_origin_as_the_crop(self):
        frame, bbox = place(self.portrait, 0, 0)
        shifted = [-20, -10, bbox[2] - 20, bbox[3] - 10]  # dépasse en haut à gauche
        self.fr.identify(frame, shifted, "p1")
        rel = self.fr.tracking_states["p1"]["face_rel"]
        if rel is not None:
            self.assertEqual(self.fr.get_face_box("p1", shifted)[:2], [rel[0], rel[1]])

    # ── Niveau API : /analyze_frame ────────────────────────────────────

    def _analyze(self, frame, bbox):
        ok, jpg = cv2.imencode(".jpg", frame)
        upload = UploadFile(file=io.BytesIO(jpg.tobytes()), filename="frame.jpg")
        with mock.patch.object(api.yolo, "detect_humans", return_value=[{"box": bbox, "confidence": 0.9}]):
            resp = asyncio.run(api.analyze_frame(file=upload, liveness_blink=0.0, liveness_smile=0.0))
        return json.loads(resp.body)["detections"]

    def test_analyze_frame_runs_the_face_gate_once_per_person_and_frame(self):
        api.tracker = type(api.tracker)()
        frame, bbox = place(self.portrait, 60, 40)
        detections = self._analyze(frame, bbox)
        self.assertEqual(len(detections), 1)
        self.assertEqual(self.cascade.calls, 1, "avant le correctif : 2 (api.py + identify)")
        self.assertIsNotNone(detections[0]["face_box"], "le client doit toujours recevoir l'encadré du visage")

    def test_once_identified_frames_between_rechecks_run_no_detection_at_all(self):
        api.tracker = type(api.tracker)()
        frame, bbox = place(self.portrait, 60, 40)
        first = self._analyze(frame, bbox)[0]
        oid = first["object_id"]

        state = self.fr.tracking_states[oid]
        state.update(status="FINISHED", final_name="Hugues", last_check_time=time.time())
        self.fr.identified_ids[oid] = "Hugues"
        calls_before = self.cascade.calls

        for _ in range(5):
            later = self._analyze(frame, bbox)[0]
        self.assertEqual(self.cascade.calls, calls_before, "avant le correctif : 1 détection par image")
        self.assertEqual(later["face_box"], first["face_box"], "l'encadré reste affiché sans nouvelle détection")

    def test_client_still_receives_a_following_box_when_the_person_moves(self):
        api.tracker = type(api.tracker)()
        frame, bbox = place(self.portrait, 60, 40)
        first = self._analyze(frame, bbox)[0]
        oid = first["object_id"]
        self.fr.tracking_states[oid].update(status="FINISHED", final_name="Hugues", last_check_time=time.time())
        self.fr.identified_ids[oid] = "Hugues"

        frame2, bbox2 = place(self.portrait, 90, 60)  # la personne s'est déplacée de (+30, +20)
        second = self._analyze(frame2, bbox2)[0]
        self.assertEqual(second["bbox"][:2], [90, 60])
        self.assertEqual(second["face_box"][:2], [first["face_box"][0] + 30, first["face_box"][1] + 20])


if __name__ == "__main__":
    unittest.main()
