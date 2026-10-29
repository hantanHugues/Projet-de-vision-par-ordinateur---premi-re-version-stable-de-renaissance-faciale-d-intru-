"""
Tests de la logique « intrus » après la recette webcam du 29/10 :

  - faux visage : le Haar trouve un « visage » sur le col et le bouton d'une chemise, et un
    intrus était confirmé (photo Telegram d'un torse). Second avis MediaPipe ;
  - un VIP déjà reconnu qui retombe en analyse (ANOMALIE) a 5 s avant d'être soupçonné, pas 1 s ;
  - un intrus provisoire reconnu d'un coup comme un VIP (distance < 0.25) est reclassé tout de suite ;
  - le compteur d'intrus ne repart plus à zéro quand le cache est rechargé.

La chemise est le recadrage de la photo reçue sur Telegram (tests/photos_test_faux_visage).
Base SQLite temporaire, horloge simulée, FaceNet remplacé par un double : la vraie base
biométrique n'est pas touchée.

    .venv-deepface\\Scripts\\python.exe -m unittest tests.test_intruder_logic -v
"""

import os
import tempfile
import types
import unittest
from unittest import mock

import cv2
import numpy as np

import config

config.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="biogate-test-"), "visages.db")

import api  # noqa: E402  (après la redirection de config.DB_PATH)

HERE = os.path.dirname(__file__)
PORTRAIT = os.path.join(HERE, "photos_test_apprentissage_continu", "apres1_2019_Chris_Evans_barbe.jpg")
SHIRT = os.path.join(HERE, "photos_test_faux_visage", "chemise_alerte_telegram.jpg")
CANVAS_W, CANVAS_H = 640, 480


def load(path, max_w, max_h):
    img = cv2.imread(path)
    assert img is not None, f"image de test introuvable : {path}"
    h, w = img.shape[:2]
    scale = min(max_w / w, max_h / h, 1.0)
    return cv2.resize(img, (int(w * scale), int(h * scale)))


def on_canvas(img, x=60, y=20):
    canvas = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)
    h, w = img.shape[:2]
    canvas[y:y + h, x:x + w] = img
    return canvas, [x, y, x + w, y + h]


class IntruderLogicBase(unittest.TestCase):
    def setUp(self):
        self.fr = api.face_recognizer
        self.fr.tracking_states.clear()
        self.fr.identified_ids.clear()
        self.clock = {"t": 1000.0}
        self.face_frame, self.face_bbox = on_canvas(load(PORTRAIT, 300, 380))
        # Taille réelle : réduite, la chemise ne trompe plus le Haar (le faux visage fait 67 px)
        self.shirt_frame = load(SHIRT, 10000, 10000)
        self.shirt_bbox = [0, 0, self.shirt_frame.shape[1], self.shirt_frame.shape[0]]
        self.match = (None, 1.0)
        fake_time = types.SimpleNamespace(time=lambda: self.clock["t"])
        for patcher in (
            mock.patch("core.face_recognizer.time", fake_time),
            mock.patch.object(self.fr, "_extract_face_signature", return_value=np.ones(512, dtype=np.float32)),
            mock.patch.object(self.fr, "_find_in_memory", side_effect=lambda *a: self.match),
            mock.patch.object(self.fr, "ANALYSIS_TIME_LIMIT", 1.0),
            mock.patch.object(config, "FACE_ABSENT_LIMIT", 0.0),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(lambda: api.trust_mgr.remove("p1"))

    def at(self, t, frame=None, bbox=None):
        self.clock["t"] = 1000.0 + t
        return self.fr.identify(
            self.face_frame if frame is None else frame,
            self.face_bbox if bbox is None else bbox,
            "p1",
        )

    def trust_state(self):
        return api.trust_mgr.get("p1").get_state()["state"]

    def make_vip(self, name="Hugues"):
        self.match = (name, 0.1)
        self.assertEqual(self.at(0), name)
        self.match = (None, 1.0)


class FalseFaceTest(IntruderLogicBase):
    def test_the_shirt_really_fools_haar(self):
        """Condition de départ : sans second avis, le Haar voit bien un visage sur la chemise."""
        gray = cv2.equalizeHist(cv2.cvtColor(self.shirt_frame, cv2.COLOR_BGR2GRAY))
        faces = self.fr.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        self.assertGreater(len(faces), 0)

    def test_a_shirt_is_never_judged_as_an_unknown_face(self):
        self.assertTrue(self.at(0, self.shirt_frame, self.shirt_bbox).startswith("Attente visage"))
        for t in (1.5, 3.0, 20.0):
            self.assertTrue(self.at(t, self.shirt_frame, self.shirt_bbox).startswith("Attente visage"), t)
        self.assertEqual(self.trust_state(), "ANALYZING")
        self.assertIsNone(api.trust_mgr.get("p1").snapshot_path)
        self.assertIsNone(self.fr.get_face_box("p1", self.shirt_bbox))

    def test_a_real_face_is_still_analysed_then_judged(self):
        self.assertTrue(self.at(0).startswith("Analyse"))
        self.assertTrue(self.at(1.2).startswith("Intrus"))
        self.assertIsNotNone(self.fr.get_face_box("p1", self.face_bbox))

    def test_a_real_vip_face_is_still_recognised(self):
        self.match = ("Hugues", 0.1)
        self.assertEqual(self.at(0), "Hugues")

    def test_without_the_second_opinion_the_shirt_is_judged_again(self):
        """Contre-épreuve : c'est bien le second avis qui protège (comportement d'avant)."""
        with mock.patch.object(config, "FACE_VALIDATION_ENABLED", False):
            self.assertTrue(self.at(0, self.shirt_frame, self.shirt_bbox).startswith("Analyse"))
            self.assertTrue(self.at(1.2, self.shirt_frame, self.shirt_bbox).startswith("Intrus"))

    def test_if_the_second_opinion_is_unavailable_haar_decides_alone(self):
        with mock.patch.object(self.fr, "_get_landmarker", return_value=None):
            self.assertTrue(self.at(0, self.shirt_frame, self.shirt_bbox).startswith("Analyse"))

    def test_a_failing_second_opinion_never_blocks_a_real_face(self):
        broken = mock.Mock()
        broken.detect.side_effect = RuntimeError("boom")
        with mock.patch.object(self.fr, "_get_landmarker", return_value=broken), \
             mock.patch.object(self.fr, "_mp", create=True, new=mock.MagicMock()):
            self.assertTrue(self.at(0).startswith("Analyse"))


class ReanalysisTest(IntruderLogicBase):
    def anomaly(self):
        """Un VIP reconnu, puis trois re-vérifications sans correspondance."""
        self.make_vip()
        for t in (1, 2):
            self.at(t)
        self.assertEqual(self.at(3), "Re-Analyse...")
        self.assertEqual(self.fr.tracking_states["p1"]["status"], "ANALYZING")

    def test_a_recognised_vip_is_not_suspected_after_one_second(self):
        self.anomaly()
        self.assertTrue(self.at(4.0).startswith("Analyse"))
        self.assertTrue(self.at(5.5).startswith("Analyse"), "avant : « Intrus » dès 1 s")
        self.assertTrue(self.at(8.0).startswith("Analyse"))

    def test_but_still_suspected_after_the_longer_window(self):
        self.anomaly()
        self.at(4.0)
        self.assertTrue(self.at(9.5).startswith("Intrus"))

    def test_a_vip_found_again_during_the_reanalysis_is_back_to_normal(self):
        self.anomaly()
        self.at(4.0)
        self.match = ("Hugues", 0.2)
        self.assertEqual(self.at(5.0), "Hugues")
        state = self.fr.tracking_states["p1"]
        self.assertEqual(state["status"], "FINISHED")
        self.assertNotIn("analysis_limit", state)

    def test_the_longer_window_is_gone_once_the_verdict_is_given(self):
        self.anomaly()
        self.at(4.0)
        self.at(9.5)
        self.assertNotIn("analysis_limit", self.fr.tracking_states["p1"])

    def test_a_newcomer_never_seen_before_still_gets_the_short_window(self):
        self.assertTrue(self.at(0).startswith("Analyse"))
        self.assertTrue(self.at(1.2).startswith("Intrus"))

    def test_the_window_is_configurable(self):
        with mock.patch.object(config, "REANALYSIS_TIME_LIMIT", 2.0):
            self.anomaly()
            self.at(4.0)
            self.assertTrue(self.at(5.5).startswith("Analyse"))
            self.assertTrue(self.at(6.5).startswith("Intrus"))

    def test_the_longer_window_never_goes_below_the_normal_one(self):
        with mock.patch.object(config, "REANALYSIS_TIME_LIMIT", 0.1):
            self.anomaly()
            self.at(4.0)
            self.assertTrue(self.at(4.6).startswith("Analyse"))


class StrongMatchTest(IntruderLogicBase):
    def provisional_intruder(self):
        self.assertTrue(self.at(0).startswith("Analyse"))
        name = self.at(1.2)
        self.assertTrue(name.startswith("Intrus"), name)
        self.assertEqual(self.trust_state(), "INTRUDER_PENDING")
        return name

    def test_one_strong_match_cancels_the_provisional_intruder_at_once(self):
        self.provisional_intruder()
        self.match = ("Hugues", 0.20)
        self.assertEqual(self.at(2.5), "Hugues")
        self.assertNotEqual(self.trust_state(), "INTRUDER_PENDING")
        self.assertEqual(self.fr.identified_ids["p1"], "Hugues")

    def test_a_weak_match_still_needs_the_usual_agreement(self):
        name = self.provisional_intruder()
        self.match = ("Hugues", 0.30)
        self.assertEqual(self.at(2.5), name)
        self.assertEqual(self.trust_state(), "INTRUDER_PENDING")
        self.assertEqual(self.fr.tracking_states["p1"]["recheck_fail_count"], 1)
        self.at(3.5)
        self.assertEqual(self.at(4.5), "Hugues", "trois résultats concordants : comme avant")

    def test_the_strong_distance_is_configurable(self):
        with mock.patch.object(config, "FACE_STRONG_MATCH_DISTANCE", 0.10):
            name = self.provisional_intruder()
            self.match = ("Hugues", 0.20)
            self.assertEqual(self.at(2.5), name)

    def test_a_vip_who_changes_to_another_vip_is_not_a_strong_match(self):
        """Seul un intrus provisoire gagne le raccourci : entre deux VIP, l'hystérèse reste."""
        self.make_vip("Hugues")
        self.match = ("Nadish", 0.10)
        self.assertEqual(self.at(1.0), "Hugues")
        self.assertEqual(self.fr.tracking_states["p1"]["recheck_fail_count"], 1)


class IntruderCounterTest(unittest.TestCase):
    def test_reloading_the_cache_never_lowers_the_intruder_counter(self):
        fr = api.face_recognizer
        before = fr.next_intruder_index
        fr.next_intruder_index = before + 7
        try:
            fr.reload_cache()
            self.assertEqual(fr.next_intruder_index, before + 7)
        finally:
            fr.next_intruder_index = before

    def test_the_counter_still_starts_from_the_intruders_stored_in_the_cache(self):
        fr = api.face_recognizer
        before = fr.next_intruder_index
        fr.next_intruder_index = 0
        try:
            with mock.patch.object(fr.db, "get_all_embeddings",
                                   return_value={"Hugues": [np.ones(4)], "Intrus_001": [np.ones(4)],
                                                 "Intrus_002": [np.ones(4)]}):
                fr.reload_cache()
            self.assertEqual(fr.next_intruder_index, 2)
        finally:
            fr.next_intruder_index = before
            fr.reload_cache()


if __name__ == "__main__":
    unittest.main()
