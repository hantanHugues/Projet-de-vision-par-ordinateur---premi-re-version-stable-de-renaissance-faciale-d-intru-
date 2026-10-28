"""
Tests du module d'alertes (core/notifier.py) et de la gestion des photos
d'intrus (core/trust_score.py). Aucun accès réseau : requests et smtplib
sont remplacés par des doubles.

    .venv-deepface\\Scripts\\python.exe -m unittest tests.test_notifier -v
"""

import os
import smtplib
import tempfile
import threading
import unittest
from unittest import mock

import requests

import config
from core.notifier import MASK, Notifier, drop_masked, mask_secrets
from core.trust_score import STATE_INTRUDER_CONFIRMED, TrustScore

_REAL_SPAWN = Notifier._spawn  # avant que les tests ne le remplacent par une version synchrone

TOKEN = "123456:SECRET-TOKEN"
PASSWORD_WITH_SPACES = "abcd efgh ijkl mnop"

TELEGRAM_CFG = dict(
    ALERT_TELEGRAM_ENABLED=True, TELEGRAM_BOT_TOKEN=TOKEN, TELEGRAM_CHAT_ID="42",
)
EMAIL_CFG = dict(
    ALERT_EMAIL_ENABLED=True, SMTP_HOST="smtp.example.org", SMTP_PORT=587,
    SMTP_USER="bot@example.org", SMTP_PASSWORD=PASSWORD_WITH_SPACES,
    ALERT_EMAIL_TO="owner@example.org; second@example.org",
)
NO_CHANNEL = dict(
    ALERT_TELEGRAM_ENABLED=False, TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="",
    ALERT_EMAIL_ENABLED=False, SMTP_HOST="", SMTP_USER="", SMTP_PASSWORD="", ALERT_EMAIL_TO="",
    ALERT_COOLDOWN_SECONDS=0,
)


def _response(ok=True, payload=None, status=200):
    r = mock.Mock()
    r.ok = ok
    r.status_code = status
    r.json.return_value = {"ok": ok} if payload is None else payload
    return r


def _fake_jpeg():
    f = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    f.write(b"\xff\xd8\xff\xd9")
    f.close()
    return f.name


class SecretsMaskingTest(unittest.TestCase):
    def test_non_empty_secrets_are_masked_and_empty_ones_stay_empty(self):
        cfg = {"TELEGRAM_BOT_TOKEN": TOKEN, "SMTP_PASSWORD": "", "SMTP_HOST": "h"}
        masked = mask_secrets(cfg)
        self.assertEqual(masked["TELEGRAM_BOT_TOKEN"], MASK)
        self.assertEqual(masked["SMTP_PASSWORD"], "")
        self.assertEqual(masked["SMTP_HOST"], "h")

    def test_masked_value_sent_back_does_not_overwrite_the_real_secret(self):
        updates = {"TELEGRAM_BOT_TOKEN": MASK, "SMTP_PASSWORD": "new", "SMTP_HOST": "h"}
        self.assertEqual(drop_masked(updates), {"SMTP_PASSWORD": "new", "SMTP_HOST": "h"})


class TelegramTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.multiple(config, **{**NO_CHANNEL, **TELEGRAM_CFG})
        p.start()
        self.addCleanup(p.stop)
        self.photo = _fake_jpeg()
        self.addCleanup(os.remove, self.photo)

    def test_test_message_uses_sendMessage(self):
        with mock.patch("core.notifier.requests.post", return_value=_response()) as post:
            ok, msg = Notifier().send_test("telegram")
        self.assertTrue(ok, msg)
        url = post.call_args[0][0]
        self.assertTrue(url.endswith("/sendMessage"))
        self.assertEqual(post.call_args[1]["data"]["chat_id"], "42")

    def test_alert_with_photo_uses_sendPhoto_and_attaches_the_file(self):
        with mock.patch("core.notifier.requests.post", return_value=_response()) as post:
            Notifier()._send_telegram("texte", self.photo)
        self.assertTrue(post.call_args[0][0].endswith("/sendPhoto"))
        self.assertIn("photo", post.call_args[1]["files"])

    def test_network_error_never_leaks_the_token(self):
        boom = requests.exceptions.ConnectionError(f"HTTPSConnectionPool: /bot{TOKEN}/sendMessage")
        with mock.patch("core.notifier.requests.post", side_effect=boom):
            ok, msg = Notifier().send_test("telegram")
        self.assertFalse(ok)
        self.assertNotIn(TOKEN, msg)
        self.assertNotIn("SECRET", msg)

    def test_timeout_message(self):
        with mock.patch("core.notifier.requests.post", side_effect=requests.exceptions.Timeout()):
            ok, msg = Notifier().send_test("telegram")
        self.assertFalse(ok)
        self.assertIn("à temps", msg)

    def test_telegram_refusal_is_explained_without_the_token(self):
        refused = _response(ok=False, status=401, payload={"ok": False, "description": f"Unauthorized {TOKEN}"})
        with mock.patch("core.notifier.requests.post", return_value=refused):
            ok, msg = Notifier().send_test("telegram")
        self.assertFalse(ok)
        self.assertIn("Unauthorized", msg)
        self.assertNotIn(TOKEN, msg)

    def test_missing_credentials_are_reported(self):
        with mock.patch.multiple(config, TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID=""):
            ok, msg = Notifier().send_test("telegram")
        self.assertFalse(ok)
        self.assertIn("jeton", msg)

    def test_chat_id_detection_takes_the_latest_message(self):
        updates = {"ok": True, "result": [
            {"message": {"chat": {"id": 1, "first_name": "Ancien"}}},
            {"message": {"chat": {"id": 987654, "first_name": "Hugues"}}},
        ]}
        with mock.patch("core.notifier.requests.post", return_value=_response(payload=updates)):
            chat_id, label = Notifier().discover_telegram_chat()
        self.assertEqual((chat_id, label), ("987654", "Hugues"))

    def test_chat_id_detection_without_any_message_explains_what_to_do(self):
        with mock.patch("core.notifier.requests.post", return_value=_response(payload={"ok": True, "result": []})):
            with self.assertRaises(Exception) as ctx:
                Notifier().discover_telegram_chat()
        self.assertIn("salut", str(ctx.exception))


class EmailTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.multiple(config, **{**NO_CHANNEL, **EMAIL_CFG})
        p.start()
        self.addCleanup(p.stop)
        self.photo = _fake_jpeg()
        self.addCleanup(os.remove, self.photo)

    def test_starttls_flow_strips_spaces_from_the_app_password(self):
        with mock.patch("core.notifier.smtplib.SMTP") as smtp:
            ok, msg = Notifier().send_test("email")
        self.assertTrue(ok, msg)
        server = smtp.return_value
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("bot@example.org", "abcdefghijklmnop")
        sent = server.send_message.call_args[0][0]
        self.assertEqual(sent["To"], "owner@example.org, second@example.org")

    def test_alert_attaches_the_photo(self):
        with mock.patch("core.notifier.smtplib.SMTP") as smtp:
            Notifier()._send_email("sujet", "corps", self.photo)
        sent = smtp.return_value.send_message.call_args[0][0]
        attachments = list(sent.iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_content_type(), "image/jpeg")

    def test_port_465_uses_implicit_ssl(self):
        with mock.patch.multiple(config, SMTP_PORT=465), \
             mock.patch("core.notifier.smtplib.SMTP_SSL") as ssl_cls, \
             mock.patch("core.notifier.smtplib.SMTP") as plain:
            ok, msg = Notifier().send_test("email")
        self.assertTrue(ok, msg)
        ssl_cls.assert_called_once()
        plain.assert_not_called()
        ssl_cls.return_value.starttls.assert_not_called()

    def test_rejected_login_mentions_the_app_password(self):
        with mock.patch("core.notifier.smtplib.SMTP") as smtp:
            smtp.return_value.login.side_effect = smtplib.SMTPAuthenticationError(535, b"refused")
            ok, msg = Notifier().send_test("email")
        self.assertFalse(ok)
        self.assertIn("mot de passe d'application", msg)
        self.assertNotIn("abcdefghijklmnop", msg)

    def test_unreachable_server(self):
        with mock.patch("core.notifier.smtplib.SMTP", side_effect=OSError("boom")):
            ok, msg = Notifier().send_test("email")
        self.assertFalse(ok)
        self.assertIn("injoignable", msg)

    def test_missing_recipient_is_reported(self):
        with mock.patch.multiple(config, ALERT_EMAIL_TO=""):
            ok, msg = Notifier().send_test("email")
        self.assertFalse(ok)
        self.assertIn("destinataire", msg)


class NotifyIntruderTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.multiple(config, **NO_CHANNEL)
        p.start()
        self.addCleanup(p.stop)
        sync = mock.patch.object(Notifier, "_spawn", lambda self, label, fn: fn())
        sync.start()
        self.addCleanup(sync.stop)
        self.photo = _fake_jpeg()
        self.addCleanup(os.remove, self.photo)

    def test_nothing_is_sent_when_every_channel_is_disabled(self):
        n = Notifier()
        with mock.patch.object(n, "_send_telegram") as tg, mock.patch.object(n, "_send_email") as em:
            n.notify_intruder("Intrus_001", self.photo, "cam1")
        tg.assert_not_called()
        em.assert_not_called()

    def test_both_channels_receive_the_alert_with_the_photo(self):
        n = Notifier()
        with mock.patch.multiple(config, **TELEGRAM_CFG, **EMAIL_CFG), \
             mock.patch.object(n, "_send_telegram") as tg, mock.patch.object(n, "_send_email") as em:
            n.notify_intruder("Intrus_001", self.photo, "cam1")
        text, photo = tg.call_args[0]
        self.assertIn("Intrus_001", text)
        self.assertIn("cam1", text)
        self.assertEqual(photo, self.photo)
        self.assertEqual(em.call_args[0][2], self.photo)

    def test_missing_photo_file_still_sends_the_text(self):
        n = Notifier()
        with mock.patch.multiple(config, **TELEGRAM_CFG), mock.patch.object(n, "_send_telegram") as tg:
            n.notify_intruder("Intrus_001", "database/snapshots/inexistante.jpg", "")
        self.assertIsNone(tg.call_args[0][1])

    def test_enabled_channel_with_incomplete_credentials_is_skipped(self):
        n = Notifier()
        with mock.patch.multiple(config, ALERT_TELEGRAM_ENABLED=True, TELEGRAM_BOT_TOKEN=TOKEN, TELEGRAM_CHAT_ID=""), \
             mock.patch.object(n, "_send_telegram") as tg:
            n.notify_intruder("Intrus_001", self.photo, "")
        tg.assert_not_called()

    def test_cooldown_blocks_the_second_alert(self):
        n = Notifier()
        with mock.patch.multiple(config, ALERT_COOLDOWN_SECONDS=30, **TELEGRAM_CFG), \
             mock.patch.object(n, "_send_telegram") as tg:
            n.notify_intruder("Intrus_001", None, "")
            n.notify_intruder("Intrus_002", None, "")
        self.assertEqual(tg.call_count, 1)

    def test_a_failing_channel_never_raises_into_the_pipeline(self):
        n = Notifier()
        n._spawn = _REAL_SPAWN.__get__(n)  # vraie version : thread + capture des erreurs
        done = threading.Event()

        def boom(*_a, **_k):
            done.set()
            raise requests.exceptions.ConnectionError("réseau coupé")

        with mock.patch.multiple(config, **TELEGRAM_CFG), mock.patch.object(n, "_send_telegram", side_effect=boom):
            n.notify_intruder("Intrus_001", None, "")
            self.assertTrue(done.wait(2))


class IntruderSnapshotLifecycleTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.multiple(config, ALERT_GRACE_PERIOD=60)
        p.start()
        self.addCleanup(p.stop)

    def test_snapshot_is_set_only_once(self):
        ts = TrustScore("cam1#1")
        a, b = _fake_jpeg(), _fake_jpeg()
        self.addCleanup(lambda: [os.path.exists(x) and os.remove(x) for x in (a, b)])
        ts.set_snapshot(a)
        ts.set_snapshot(b)
        self.assertEqual(ts.snapshot_path, a)

    def test_snapshot_is_deleted_when_a_vip_cancels_the_alert(self):
        ts = TrustScore("cam1#1")
        ts.intruder_detected()
        path = _fake_jpeg()
        ts.set_snapshot(path)
        self.assertTrue(ts.cancel_intruder_alert())
        self.assertFalse(os.path.exists(path))
        self.assertIsNone(ts.snapshot_path)

    def test_snapshot_is_deleted_when_the_person_leaves_before_confirmation(self):
        ts = TrustScore("cam1#1")
        ts.intruder_detected()
        path = _fake_jpeg()
        ts.set_snapshot(path)
        ts.cleanup()
        self.assertFalse(os.path.exists(path))

    def test_confirmed_intruder_keeps_the_snapshot_referenced_by_the_log(self):
        ts = TrustScore("cam1#1")
        path = _fake_jpeg()
        self.addCleanup(os.remove, path)
        ts.set_snapshot(path)
        ts.state = STATE_INTRUDER_CONFIRMED
        ts.cleanup()
        self.assertTrue(os.path.exists(path))

    def test_confirmation_callback_receives_the_snapshot_path(self):
        received, done = {}, threading.Event()

        def on_confirmed(object_id, snapshot_path):
            received.update(object_id=object_id, snapshot_path=snapshot_path)
            done.set()

        with mock.patch.multiple(config, ALERT_GRACE_PERIOD=0.05):
            ts = TrustScore("cam1#7", on_intruder_confirmed=on_confirmed)
            ts.intruder_detected()
            path = _fake_jpeg()
            self.addCleanup(os.remove, path)
            ts.set_snapshot(path)
            self.assertTrue(done.wait(2))
        self.assertEqual(received, {"object_id": "cam1#7", "snapshot_path": path})


if __name__ == "__main__":
    unittest.main()
