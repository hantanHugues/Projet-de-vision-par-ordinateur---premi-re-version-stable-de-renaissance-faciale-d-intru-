"""
Tests des routes d'alerte de api.py (config masquée, test d'envoi, photo d'intrus).

Le module api charge YOLO et FaceNet : ce test est lent au démarrage (quelques
secondes à une minute). Il pointe vers une base SQLite TEMPORAIRE : la vraie base
biométrique database/visages.db n'est ni lue ni modifiée.

    .venv-deepface\\Scripts\\python.exe -m unittest tests.test_alerts_api -v
"""

import asyncio
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

import config

_TMP = tempfile.mkdtemp(prefix="biogate-test-")
config.DB_PATH = os.path.join(_TMP, "visages.db")

import api  # noqa: E402  (doit venir après la redirection de config.DB_PATH)
from core.notifier import MASK  # noqa: E402
from core.trust_score import TrustScore  # noqa: E402
from fastapi import HTTPException  # noqa: E402

AUTH = "Bearer test-token"


def run(coro):
    return asyncio.run(coro)


class ConfigSecretsTest(unittest.TestCase):
    def setUp(self):
        api._dashboard_token = "test-token"
        saved = {k: getattr(config, k) for k in (
            "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SMTP_PASSWORD", "SMTP_USER",
            "ALERT_TELEGRAM_ENABLED", "ALERT_EMAIL_ENABLED",
        )}
        self.addCleanup(lambda: [setattr(config, k, v) for k, v in saved.items()])

    def test_every_config_route_requires_the_token(self):
        for call in (
            lambda: api.get_config(authorization=None),
            lambda: api.update_config({}, authorization="Bearer faux"),
            lambda: api.alerts_test(api.AlertTestRequest(channel="telegram"), authorization=None),
            lambda: api.alerts_telegram_detect(authorization=None),
        ):
            with self.assertRaises(HTTPException) as ctx:
                run(call())
            self.assertEqual(ctx.exception.status_code, 401)

    def test_secrets_are_stored_but_never_returned_in_clear(self):
        result = run(api.update_config(
            {"TELEGRAM_BOT_TOKEN": "111:ABC", "TELEGRAM_CHAT_ID": "42", "SMTP_PASSWORD": "motdepasse"},
            authorization=AUTH,
        ))
        self.assertEqual(result["applied"]["TELEGRAM_BOT_TOKEN"], MASK)
        self.assertEqual(result["applied"]["TELEGRAM_CHAT_ID"], "42")

        cfg = run(api.get_config(authorization=AUTH))
        self.assertEqual(cfg["TELEGRAM_BOT_TOKEN"], MASK)
        self.assertEqual(cfg["SMTP_PASSWORD"], MASK)
        self.assertEqual(cfg["TELEGRAM_CHAT_ID"], "42")
        # ... mais ils sont bien appliqués en mémoire, donc utilisables tout de suite.
        self.assertEqual(config.TELEGRAM_BOT_TOKEN, "111:ABC")
        self.assertEqual(config.SMTP_PASSWORD, "motdepasse")

    def test_autosave_of_the_whole_config_page_keeps_the_real_secrets(self):
        run(api.update_config({"TELEGRAM_BOT_TOKEN": "111:ABC"}, authorization=AUTH))
        page_state = run(api.get_config(authorization=AUTH))  # contient le masque
        run(api.update_config(page_state, authorization=AUTH))  # ce que fait la page Configuration
        self.assertEqual(config.TELEGRAM_BOT_TOKEN, "111:ABC")

    def test_empty_secret_can_be_cleared_on_purpose(self):
        run(api.update_config({"SMTP_PASSWORD": "abc"}, authorization=AUTH))
        run(api.update_config({"SMTP_PASSWORD": ""}, authorization=AUTH))
        self.assertEqual(config.SMTP_PASSWORD, "")
        self.assertEqual(run(api.get_config(authorization=AUTH))["SMTP_PASSWORD"], "")

    def test_orphan_whatsapp_keys_are_gone_from_the_config(self):
        api.face_recognizer.db.set_config("ALERT_WHATSAPP_ENABLED", True)  # reste d'une ancienne version
        cfg = run(api.get_config(authorization=AUTH))
        self.assertNotIn("ALERT_WHATSAPP_ENABLED", cfg)
        applied = run(api.update_config({"ALERT_WHATSAPP_ENABLED": False}, authorization=AUTH))["applied"]
        self.assertEqual(applied, {})

    def test_templates_drive_the_new_alert_flags(self):
        templates = api.face_recognizer.db.get_templates()
        for name, values in templates.items():
            self.assertIn("ALERT_TELEGRAM_ENABLED", values, name)
            self.assertIn("ALERT_EMAIL_ENABLED", values, name)
            self.assertNotIn("ALERT_WHATSAPP_ENABLED", values, name)


class AlertTestRouteTest(unittest.TestCase):
    def setUp(self):
        api._dashboard_token = "test-token"

    def test_unknown_channel_is_a_400(self):
        resp = run(api.alerts_test(api.AlertTestRequest(channel="sms"), authorization=AUTH))
        self.assertEqual(resp.status_code, 400)

    def test_unconfigured_channel_explains_what_is_missing(self):
        with mock.patch.multiple(config, TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID=""):
            resp = run(api.alerts_test(api.AlertTestRequest(channel="telegram"), authorization=AUTH))
        self.assertFalse(resp["success"])
        self.assertIn("jeton", resp["message"])

    def test_configured_channel_sends_through_the_notifier(self):
        ok = mock.Mock(ok=True, status_code=200)
        ok.json.return_value = {"ok": True}
        with mock.patch.multiple(config, TELEGRAM_BOT_TOKEN="111:ABC", TELEGRAM_CHAT_ID="42"), \
             mock.patch("core.notifier.requests.post", return_value=ok) as post:
            resp = run(api.alerts_test(api.AlertTestRequest(channel="telegram"), authorization=AUTH))
        self.assertTrue(resp["success"], resp)
        post.assert_called_once()

    def test_telegram_detection_reports_a_missing_token(self):
        with mock.patch.multiple(config, TELEGRAM_BOT_TOKEN=""):
            resp = run(api.alerts_telegram_detect(authorization=AUTH))
        self.assertFalse(resp["success"])


class IntruderSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.snap_dir = tempfile.mkdtemp(prefix="biogate-snap-")
        p = mock.patch.object(api, "SNAPSHOT_DIR", self.snap_dir)
        p.start()
        self.addCleanup(p.stop)
        self.frame = np.full((120, 160, 3), 128, dtype=np.uint8)
        self.bbox = (20, 10, 100, 110)

    def _files(self):
        return os.listdir(self.snap_dir)

    def _pending_intruder(self):
        ts = TrustScore("cam1#3")
        ts.intruder_detected()
        self.addCleanup(ts.cleanup)
        return ts

    def test_a_suspected_intruder_gets_a_photo(self):
        ts = self._pending_intruder()
        api._attach_intruder_snapshot(ts, self.frame, self.bbox, "cam1_ID3")
        self.assertEqual(len(self._files()), 1)
        self.assertTrue(os.path.isfile(ts.snapshot_path))
        self.assertIn("cam1_ID3", ts.snapshot_path)

    def test_the_photo_is_taken_once(self):
        ts = self._pending_intruder()
        api._attach_intruder_snapshot(ts, self.frame, self.bbox, "cam1_ID3")
        api._attach_intruder_snapshot(ts, self.frame, self.bbox, "cam1_ID3")
        self.assertEqual(len(self._files()), 1)

    def test_a_vip_is_never_photographed(self):
        ts = TrustScore("cam1#4")
        ts.start_analyzing()
        ts.face_matched("Hugues", 88.0)
        api._attach_intruder_snapshot(ts, self.frame, self.bbox, "cam1_ID4")
        self.assertEqual(self._files(), [])
        self.assertIsNone(ts.snapshot_path)

    def test_unsafe_camera_names_cannot_escape_the_snapshot_folder(self):
        ts = self._pending_intruder()
        api._attach_intruder_snapshot(ts, self.frame, self.bbox, "../../etc/cam 1_ID3")
        self.assertEqual(len(self._files()), 1)
        self.assertEqual(os.path.dirname(os.path.abspath(ts.snapshot_path)), os.path.abspath(self.snap_dir))

    def test_client_mode_reuses_the_silhouette_already_on_disk(self):
        existing = os.path.join(self.snap_dir, "deja_la.jpg")
        with open(existing, "wb") as f:
            f.write(b"\xff\xd8\xff\xd9")
        ts = self._pending_intruder()
        api._attach_intruder_snapshot(ts, self.frame, self.bbox, "ID3", known_path=existing)
        self.assertEqual(ts.snapshot_path, existing)
        self.assertEqual(self._files(), ["deja_la.jpg"])

    def test_a_degenerate_box_does_not_crash(self):
        ts = self._pending_intruder()
        api._attach_intruder_snapshot(ts, self.frame, (500, 500, 600, 600), "cam1_ID3")
        self.assertEqual(self._files(), [])


class ConfirmationCallbackTest(unittest.TestCase):
    def test_confirmed_intrusion_is_logged_with_its_photo_and_notified(self):
        snap = os.path.join(_TMP, "intrus.jpg")
        with open(snap, "wb") as f:
            f.write(b"\xff\xd8\xff\xd9")
        with mock.patch.object(api.notifier, "notify_intruder") as notify, \
             mock.patch.object(api.iot, "set_light_alert"):
            api._on_intruder_confirmed("cam1#9", snap)
        name, path, source = notify.call_args[0]
        self.assertEqual(path, snap)
        self.assertEqual(source, "cam1")
        logs = api.face_recognizer.db.get_logs(limit=5, event_type="INTRUDER_CONFIRMED")
        self.assertTrue(any(row.get("snapshot_path") == snap for row in logs), logs)


if __name__ == "__main__":
    unittest.main()
