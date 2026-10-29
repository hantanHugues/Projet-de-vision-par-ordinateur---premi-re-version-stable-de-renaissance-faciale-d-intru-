"""
Tests de l'image affichée au dashboard : une webcam locale renvoie souvent un miroir, remis à
l'endroit à l'affichage seulement. Le pipeline IA doit continuer à recevoir l'image de la caméra.

Aucune caméra réelle : une fausse capture fournit l'image. Ne charge ni YOLO ni FaceNet.

    .venv-deepface\\Scripts\\python.exe -m unittest tests.test_camera_display -v
"""

import unittest
from unittest import mock

import cv2
import numpy as np

import config
from core.camera_manager import CameraSource, mirror_annotations

W, H = 200, 100


def make_frame():
    """Moitié gauche rouge, moitié droite bleue (BGR) : le sens se lit sur un seul pixel."""
    frame = np.zeros((H, W, 3), dtype=np.uint8)
    frame[:, : W // 2] = (0, 0, 255)
    frame[:, W // 2:] = (255, 0, 0)
    return frame


class Recorder:
    """draw_fn de remplacement : mémorise ce qu'on lui demande de dessiner."""

    def __init__(self):
        self.frame = None
        self.annotations = None

    def __call__(self, frame, annotations, cam_id, cam_name):
        self.frame, self.annotations = frame, annotations
        return frame


class FakeCapture:
    def __init__(self, source, frame):
        self.source, self.frame = source, frame

    def isOpened(self):
        return True

    def read(self):
        self.source._running = False   # une seule image, puis la boucle s'arrête
        return True, self.frame.copy()

    def release(self):
        pass


class MirrorAnnotationsTest(unittest.TestCase):
    def test_boxes_are_mirrored_around_the_image_width(self):
        got = mirror_annotations([(7, 10, 20, 50, 80, "Ash", 91.0, "GRANTED")], W)
        self.assertEqual(got, [(7, 150, 20, 190, 80, "Ash", 91.0, "GRANTED")])

    def test_mirroring_twice_gives_back_the_original(self):
        original = [(1, 0, 0, 40, 60, "Inconnu", 0.0, "ANALYZING"), (2, 120, 10, 199, 90, "Nadish", 80.0, "GRANTED")]
        self.assertEqual(mirror_annotations(mirror_annotations(original, W), W), original)

    def test_a_box_stays_well_formed(self):
        for _, x1, _, x2, *_ in mirror_annotations([(1, 30, 0, 90, 10, "x", 0.0, "s")], W):
            self.assertLess(x1, x2)

    def test_no_annotations(self):
        self.assertEqual(mirror_annotations([], W), [])


class RenderTest(unittest.TestCase):
    def source(self, cam_type="usb"):
        self.rec = Recorder()
        return CameraSource("cam", {"type": cam_type, "name": "Webcam"}, on_frame=None, draw_fn=self.rec)

    def test_a_usb_webcam_is_shown_the_right_way_round(self):
        src = self.source("usb")
        src.set_annotations([(1, 10, 20, 50, 80, "Ash", 90.0, "GRANTED")])
        shown = src._render(make_frame())
        self.assertEqual(tuple(shown[0, 5]), (255, 0, 0), "le bleu, à droite sur l'image brute, passe à gauche")
        self.assertEqual(tuple(shown[0, W - 5]), (0, 0, 255))
        self.assertEqual(self.rec.annotations, [(1, 150, 20, 190, 80, "Ash", 90.0, "GRANTED")])

    def test_the_box_stays_on_the_same_person_after_the_flip(self):
        """Un visage dessiné à gauche de l'image brute doit être encadré au même endroit une fois retourné."""
        src = self.source("usb")
        raw = make_frame()
        raw[20:80, 10:50] = (0, 255, 0)
        src.set_annotations([(1, 10, 20, 50, 80, "Ash", 0.0, "GRANTED")])
        shown = src._render(raw)
        x1, y1, x2, y2 = self.rec.annotations[0][1:5]
        zone = shown[y1:y2, x1:x2]
        self.assertTrue((zone == (0, 255, 0)).all())

    def test_with_the_option_off_nothing_changes(self):
        with mock.patch.object(config, "DISPLAY_FLIP_HORIZONTAL_USB", False):
            src = self.source("usb")
            src.set_annotations([(1, 10, 20, 50, 80, "Ash", 90.0, "GRANTED")])
            shown = src._render(make_frame())
        self.assertEqual(tuple(shown[0, 5]), (0, 0, 255))
        self.assertEqual(self.rec.annotations, [(1, 10, 20, 50, 80, "Ash", 90.0, "GRANTED")])

    def test_an_ip_camera_is_never_flipped(self):
        for cam_type in ("mjpeg", "rtsp", "file"):
            src = self.source(cam_type)
            src.set_annotations([(1, 10, 20, 50, 80, "Ash", 90.0, "GRANTED")])
            shown = src._render(make_frame())
            self.assertEqual(tuple(shown[0, 5]), (0, 0, 255), cam_type)
            self.assertEqual(self.rec.annotations[0][1:5], (10, 20, 50, 80), cam_type)

    def test_the_captured_frame_is_not_modified(self):
        src = self.source("usb")
        raw = make_frame()
        before = raw.copy()
        src._render(raw)
        self.assertTrue((raw == before).all())

    def test_a_failing_drawing_still_shows_the_corrected_image(self):
        src = CameraSource("cam", {"type": "usb"}, on_frame=None, draw_fn=mock.Mock(side_effect=RuntimeError("boom")))
        shown = src._render(make_frame())
        self.assertEqual(tuple(shown[0, 5]), (255, 0, 0))

    def test_without_a_drawing_function_the_image_is_still_flipped(self):
        src = CameraSource("cam", {"type": "usb"}, on_frame=None, draw_fn=None)
        shown = src._render(make_frame())
        self.assertEqual(tuple(shown[0, 5]), (255, 0, 0))


class CaptureLoopTest(unittest.TestCase):
    def test_the_ai_pipeline_receives_the_camera_image_and_the_stream_the_corrected_one(self):
        received = []
        src = CameraSource("cam", {"type": "usb"}, on_frame=lambda cam_id, frame: received.append(frame), draw_fn=None)
        src._running = True
        src._cap = FakeCapture(src, make_frame())
        src._loop()

        self.assertEqual(len(received), 1)
        self.assertEqual(tuple(received[0][0, 5]), (0, 0, 255), "l'IA reçoit l'image brute de la caméra")
        streamed = cv2.imdecode(np.frombuffer(src._last_jpg, np.uint8), cv2.IMREAD_COLOR)
        self.assertGreater(streamed[50, 5][0], 200, "le flux montré est retourné : bleu à gauche")
        self.assertGreater(streamed[50, W - 5][2], 200)


if __name__ == "__main__":
    unittest.main()
