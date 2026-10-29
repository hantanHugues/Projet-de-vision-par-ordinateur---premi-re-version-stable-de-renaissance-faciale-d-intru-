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
import re
import tempfile
import time
import types
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


class PipelineAnnotationsTest(unittest.TestCase):
    """
    Régression : identify() renvoie un TEXTE, mais le pipeline multi-caméras (dashboard)
    appelait identity.get("name") dessus. Toute personne non reconnue (inconnu, intrus,
    analyse en cours) levait AttributeError, ce qui faisait perdre TOUTES les annotations de
    l'image : aucun cadre sur la vidéo, et les personnes suivantes n'étaient même pas traitées.
    """

    CAM = "cam_test"

    def setUp(self):
        self.fr = api.face_recognizer
        self.fr.tracking_states.clear()
        self.fr.identified_ids.clear()
        api._cam_trackers.pop(self.CAM, None)
        pic = load_portrait(220, 320)
        canvas = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)
        self.boxes = []
        for x in (30, 350):
            canvas[40:40 + pic.shape[0], x:x + pic.shape[1]] = pic
            self.boxes.append([x, 40, x + pic.shape[1], 40 + pic.shape[0]])
        self.frame = canvas
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for oid in range(4):
            api.trust_mgr.remove(f"{self.CAM}#{oid}")
        api._cam_trackers.pop(self.CAM, None)

    def _run(self, match):
        detections = [{"box": b, "confidence": 0.9} for b in self.boxes]
        with mock.patch.object(api.yolo, "detect_humans", return_value=detections), \
             mock.patch.object(self.fr, "_extract_face_signature", return_value=np.ones(512, dtype=np.float32)), \
             mock.patch.object(self.fr, "_find_in_memory", return_value=match), \
             mock.patch.object(api, "iot"), \
             mock.patch.object(api, "logger") as log:
            annotations = api._run_pipeline_and_annotate(self.frame, self.CAM)
        return annotations, log

    def test_unknown_people_are_annotated_instead_of_aborting_the_frame(self):
        annotations, log = self._run((None, 1.0))
        self.assertEqual(len(annotations), 2, "chaque personne doit avoir son annotation")
        for _oid, _x1, _y1, _x2, _y2, name, _score, _state in annotations:
            self.assertIsInstance(name, str)
            self.assertTrue(name)
        log.warning.assert_not_called()

    def test_a_recognised_vip_is_labelled_with_its_name(self):
        annotations, log = self._run(("Hugues", 0.1))
        self.assertEqual({a[5] for a in annotations}, {"Hugues"})
        log.warning.assert_not_called()


class FaceAbsentTest(unittest.TestCase):
    """
    Une silhouette sans visage de face (main devant l'objectif, torse trop près, passant de dos,
    photo mal cadrée) ne doit pas être classée « Intrus » au bout d'une seconde, et la fenêtre
    d'analyse doit démarrer à l'apparition du visage, pas à l'arrivée de la silhouette.
    Horloge simulée : les tests ne dépendent pas du temps réel.
    """

    BBOX = [100, 100, 300, 400]

    def setUp(self):
        self.fr = api.face_recognizer
        self.fr.tracking_states.clear()
        self.fr.identified_ids.clear()
        self.clock = {"t": 1000.0}
        self.blank = np.full((CANVAS_H, CANVAS_W, 3), 128, dtype=np.uint8)
        self.face_frame, self.face_bbox = place(load_portrait(), 60, 40)
        self.match = (None, 1.0)
        fake_time = types.SimpleNamespace(time=lambda: self.clock["t"])
        for patcher in (
            mock.patch("core.face_recognizer.time", fake_time),
            mock.patch.object(self.fr, "_extract_face_signature", return_value=np.ones(512, dtype=np.float32)),
            mock.patch.object(self.fr, "_find_in_memory", side_effect=lambda *a: self.match),
            mock.patch.object(self.fr, "ANALYSIS_TIME_LIMIT", 1.0),
            mock.patch.object(config, "FACE_ABSENT_LIMIT", 5.0),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(lambda: api.trust_mgr.remove("p1"))

    def at(self, t, frame=None, bbox=None):
        self.clock["t"] = 1000.0 + t
        return self.fr.identify(
            self.blank if frame is None else frame, self.BBOX if bbox is None else bbox, "p1"
        )

    def trust_state(self):
        return api.trust_mgr.get("p1").get_state()["state"]

    def test_a_faceless_silhouette_is_not_an_intruder_after_one_second(self):
        self.at(0)
        for t in (1.5, 3.0, 4.9):
            self.assertTrue(self.at(t).startswith("Attente visage"), t)
        self.assertEqual(self.trust_state(), "ANALYZING")
        self.assertEqual(self.fr.tracking_states["p1"]["status"], "ANALYZING")

    def test_a_silhouette_that_stays_faceless_becomes_a_provisional_intruder_after_the_delay(self):
        self.at(0)
        result = self.at(5.2)
        self.assertTrue(result.startswith("Intrus"), result)
        self.assertEqual(self.trust_state(), "INTRUDER_PENDING")

    def test_the_delay_is_configurable(self):
        with mock.patch.object(config, "FACE_ABSENT_LIMIT", 2.0):
            self.at(0)
            self.assertTrue(self.at(1.9).startswith("Attente visage"))
            self.assertTrue(self.at(2.1).startswith("Intrus"))

    def test_the_delay_never_goes_below_the_analysis_window(self):
        with mock.patch.object(config, "FACE_ABSENT_LIMIT", 0.1):
            self.at(0)
            self.assertTrue(self.at(0.9).startswith("Attente visage"))

    def test_a_face_appearing_late_gets_a_full_analysis_window(self):
        self.at(0)                                   # 3 s sans visage
        first = self.at(3.0, self.face_frame, self.face_bbox)
        self.assertTrue(first.startswith("Analyse"), "avant le correctif : « Intrus » dès la première image avec visage")
        self.assertTrue(self.at(3.5, self.face_frame, self.face_bbox).startswith("Analyse"))
        self.assertEqual(self.trust_state(), "ANALYZING")
        self.assertTrue(self.at(4.2, self.face_frame, self.face_bbox).startswith("Intrus"))

    def test_a_vip_whose_face_appears_late_is_recognised_at_once(self):
        self.at(0)
        self.match = ("Hugues", 0.1)
        self.assertEqual(self.at(3.0, self.face_frame, self.face_bbox), "Hugues")

    def test_an_unknown_visible_face_is_still_judged_after_the_analysis_window(self):
        self.at(0, self.face_frame, self.face_bbox)
        self.assertTrue(self.at(0.6, self.face_frame, self.face_bbox).startswith("Analyse"))
        self.assertTrue(self.at(1.2, self.face_frame, self.face_bbox).startswith("Intrus"))

    def test_nothing_is_photographed_nor_logged_while_waiting_for_a_face(self):
        logged_before = len(self.fr.db.get_logs(limit=500, event_type="INTRUDER_PENDING"))
        self.at(0)
        self.at(4.0)
        self.assertIsNone(api.trust_mgr.get("p1").snapshot_path)
        self.assertEqual(len(self.fr.db.get_logs(limit=500, event_type="INTRUDER_PENDING")), logged_before)

    def test_with_the_delay_disabled_a_faceless_silhouette_is_never_an_intruder(self):
        with mock.patch.object(config, "FACE_ABSENT_LIMIT", 0.0):
            logged_before = len(self.fr.db.get_logs(limit=500, event_type="INTRUDER_PENDING"))
            self.at(0)
            for t in (2, 60, 3600):
                self.assertEqual(self.at(t), "Attente visage...", t)
            self.assertEqual(self.trust_state(), "ANALYZING")
            self.assertIsNone(api.trust_mgr.get("p1").snapshot_path)
            self.assertEqual(len(self.fr.db.get_logs(limit=500, event_type="INTRUDER_PENDING")), logged_before)

    def test_the_shipped_default_is_no_verdict_without_a_face(self):
        source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.py"),
                      encoding="utf-8").read()
        self.assertEqual(float(re.search(r"^FACE_ABSENT_LIMIT\s*=\s*([\d.]+)", source, re.M).group(1)), 0.0)
        for profile, values in self.fr.db.get_templates().items():
            expected = 5.0 if profile == "HAUTE_SECURITE" else 0.0
            self.assertEqual(values["FACE_ABSENT_LIMIT"], expected, profile)

    def test_leaving_without_ever_showing_a_face_is_not_a_flight_alert(self):
        self.at(0)
        self.at(3)
        with mock.patch.object(self.fr, "logger") as log:
            self.fr.clear_lost_ids([])
        log.error.assert_not_called()

    def test_leaving_while_a_face_was_being_analysed_is_still_a_flight_alert(self):
        self.at(0, self.face_frame, self.face_bbox)
        with mock.patch.object(self.fr, "logger") as log:
            self.fr.clear_lost_ids([])
        self.assertTrue(any("ALERTE FUITE" in str(c) for c in log.error.call_args_list))

    # ── Traces au journal à la disparition ─────────────────────────────

    def count(self, kind):
        return len(self.fr.db.get_logs(limit=500, event_type=kind))

    def test_a_faceless_silhouette_present_long_enough_leaves_an_audit_trace(self):
        passages, pending = self.count("FACELESS_PASSAGE"), self.count("INTRUDER_PENDING")
        self.at(0)
        self.at(4)
        self.fr.clear_lost_ids([])
        self.assertEqual(self.count("FACELESS_PASSAGE"), passages + 1)
        self.assertEqual(self.count("INTRUDER_PENDING"), pending, "un passage sans visage n'est pas un intrus")
        newest = self.fr.db.get_logs(limit=1, event_type="FACELESS_PASSAGE")[0]
        self.assertEqual(newest["name"], "Inconnu")
        self.assertIsNone(newest["snapshot_path"], "aucune photo pour un passage sans visage")

    def test_a_brief_faceless_detection_is_ignored(self):
        before = self.count("FACELESS_PASSAGE")
        self.at(0)
        self.at(1.0)
        self.fr.clear_lost_ids([])
        self.assertEqual(self.count("FACELESS_PASSAGE"), before)

    def test_the_passage_trace_can_be_disabled(self):
        before = self.count("FACELESS_PASSAGE")
        with mock.patch.object(config, "FACELESS_PASSAGE_MIN_SECONDS", 0):
            self.at(0)
            self.at(60)
            self.fr.clear_lost_ids([])
        self.assertEqual(self.count("FACELESS_PASSAGE"), before)

    def test_fleeing_after_a_face_was_seen_is_written_as_a_flight_alert(self):
        flights, passages = self.count("FLIGHT_ALERT"), self.count("FACELESS_PASSAGE")
        self.at(0, self.face_frame, self.face_bbox)
        self.fr.clear_lost_ids([])
        self.assertEqual(self.count("FLIGHT_ALERT"), flights + 1)
        self.assertEqual(self.count("FACELESS_PASSAGE"), passages)

    def test_a_recognised_vip_leaving_leaves_no_trace(self):
        flights, passages = self.count("FLIGHT_ALERT"), self.count("FACELESS_PASSAGE")
        self.match = ("Hugues", 0.1)
        self.assertEqual(self.at(0, self.face_frame, self.face_bbox), "Hugues")
        self.fr.clear_lost_ids([])
        self.assertEqual((self.count("FLIGHT_ALERT"), self.count("FACELESS_PASSAGE")), (flights, passages))

    def test_an_intruder_already_judged_does_not_also_count_as_a_flight(self):
        flights, passages = self.count("FLIGHT_ALERT"), self.count("FACELESS_PASSAGE")
        self.at(0, self.face_frame, self.face_bbox)
        self.assertTrue(self.at(1.2, self.face_frame, self.face_bbox).startswith("Intrus"))
        self.fr.clear_lost_ids([])
        self.assertEqual((self.count("FLIGHT_ALERT"), self.count("FACELESS_PASSAGE")), (flights, passages))


if __name__ == "__main__":
    unittest.main()
