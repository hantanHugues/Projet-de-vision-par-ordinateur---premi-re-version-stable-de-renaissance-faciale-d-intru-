"""
Tests de la suppression des messages Telegram (core/notifier.py + database/db_manager.py).
Aucun accès réseau : requests est remplacé par un double. La base est TEMPORAIRE : la vraie
base biométrique database/visages.db n'est ni lue ni modifiée.

    .venv-deepface\\Scripts\\python.exe -m unittest tests.test_telegram_purge -v
"""

import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest import mock

import requests

import config
from core.notifier import Notifier
from database.db_manager import DatabaseManager

TOKEN = "123456:SECRET-TOKEN"
CFG = dict(
    ALERT_TELEGRAM_ENABLED=True, TELEGRAM_BOT_TOKEN=TOKEN, TELEGRAM_CHAT_ID="42",
    TELEGRAM_DELETE_AFTER_HOURS=24,
)


def _response(ok=True, payload=None, status=200):
    r = mock.Mock()
    r.ok = ok
    r.status_code = status
    r.json.return_value = {"ok": ok} if payload is None else payload
    return r


def _sent(message_id):
    return _response(payload={"ok": True, "result": {"message_id": message_id}})


class _Logger:
    def __init__(self):
        self.lines = []

    def info(self, msg):
        self.lines.append(msg)

    warning = error = info


class TelegramPurgeTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.multiple(config, **CFG)
        p.start()
        self.addCleanup(p.stop)
        self.dir = tempfile.mkdtemp(prefix="biogate-tg-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.db = DatabaseManager(db_path=os.path.join(self.dir, "visages.db"))
        self.logger = _Logger()
        self.notifier = Notifier(logger=self.logger, store=self.db)

    def _age(self, message_id, hours):
        """Vieillit un message enregistré (l'horodatage est en UTC, comme CURRENT_TIMESTAMP)."""
        conn = sqlite3.connect(self.db.db_path)
        conn.execute(
            "UPDATE telegram_messages SET sent_at = datetime('now', ?) WHERE message_id = ?",
            (f"-{hours} hours", message_id),
        )
        conn.commit()
        conn.close()

    def _stored_ids(self):
        return [r["message_id"] for r in self.db.get_expired_telegram_messages(-1)]

    # ---------------------------------------------------------------- enregistrement

    def test_a_sent_message_is_recorded_with_its_chat(self):
        with mock.patch("core.notifier.requests.post", return_value=_sent(77)):
            self.notifier.send_test("telegram")
        rows = self.db.get_expired_telegram_messages(0)
        self.assertEqual([(r["chat_id"], r["message_id"]) for r in rows], [("42", 77)])

    def test_a_photo_alert_is_recorded_too(self):
        photo = os.path.join(self.dir, "intrus.jpg")
        with open(photo, "wb") as f:
            f.write(b"\xff\xd8\xff\xd9")
        with mock.patch("core.notifier.requests.post", return_value=_sent(78)) as post:
            self.notifier._send_telegram("ALERTE", photo)
        self.assertTrue(post.call_args[0][0].endswith("/sendPhoto"))
        self.assertEqual(self._stored_ids(), [])  # trop récent pour être « expiré »
        self.assertEqual([r["message_id"] for r in self.db.get_expired_telegram_messages(0)], [78])

    def test_a_reply_without_message_id_records_nothing(self):
        with mock.patch("core.notifier.requests.post", return_value=_response()):
            ok, _ = self.notifier.send_test("telegram")
        self.assertTrue(ok)
        self.assertEqual(self.db.get_expired_telegram_messages(0), [])

    def test_a_storage_failure_never_breaks_the_alert(self):
        self.notifier.store = mock.Mock()
        self.notifier.store.record_telegram_message.side_effect = sqlite3.OperationalError("disque plein")
        with mock.patch("core.notifier.requests.post", return_value=_sent(79)):
            ok, _ = self.notifier.send_test("telegram")
        self.assertTrue(ok)

    # ---------------------------------------------------------------- suppression

    def test_only_messages_older_than_the_delay_are_deleted(self):
        for mid in (1, 2):
            self.db.record_telegram_message("42", mid)
        self._age(1, 30)
        with mock.patch("core.notifier.requests.post", return_value=_response()) as post:
            result = self.notifier.purge_telegram_messages()
        self.assertEqual(result, {"deleted": 1, "gone": 0, "failed": 0})
        self.assertEqual(post.call_count, 1)
        url = post.call_args[0][0]
        self.assertTrue(url.endswith(f"/bot{TOKEN}/deleteMessage"))
        self.assertEqual(post.call_args[1]["data"], {"chat_id": "42", "message_id": 1})
        self.assertEqual(self.db.get_expired_telegram_messages(0)[0]["message_id"], 2)
        self.assertEqual(len(self.db.get_expired_telegram_messages(0)), 1)

    def test_a_refused_deletion_is_forgotten_and_counted_as_gone(self):
        self.db.record_telegram_message("42", 5)
        self._age(5, 60)  # plus de 48 h : Telegram refuse
        refused = _response(ok=False, status=400,
                            payload={"ok": False, "description": "Bad Request: message can't be deleted"})
        with mock.patch("core.notifier.requests.post", return_value=refused):
            result = self.notifier.purge_telegram_messages()
        self.assertEqual(result, {"deleted": 0, "gone": 1, "failed": 0})
        self.assertEqual(self.db.get_expired_telegram_messages(0), [])

    def test_a_network_failure_keeps_the_messages_and_stops_at_the_first_one(self):
        for mid in (1, 2, 3):
            self.db.record_telegram_message("42", mid)
            self._age(mid, 30)
        with mock.patch("core.notifier.requests.post",
                        side_effect=requests.exceptions.ConnectionError(TOKEN)) as post:
            result = self.notifier.purge_telegram_messages()
        self.assertEqual(result, {"deleted": 0, "gone": 0, "failed": 1})
        self.assertEqual(post.call_count, 1)
        self.assertEqual(len(self.db.get_expired_telegram_messages(0)), 3)
        self.assertFalse(any(TOKEN in line for line in self.logger.lines))

    def test_the_delay_is_capped_below_the_48_hour_api_limit(self):
        for mid, age in ((1, 46), (2, 48)):
            self.db.record_telegram_message("42", mid)
            self._age(mid, age)
        with mock.patch.object(config, "TELEGRAM_DELETE_AFTER_HOURS", 200), \
             mock.patch("core.notifier.requests.post", return_value=_response()) as post:
            result = self.notifier.purge_telegram_messages()
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(post.call_args[1]["data"]["message_id"], 2)

    def test_a_delay_of_zero_in_the_settings_disables_the_deletion(self):
        self.db.record_telegram_message("42", 1)
        self._age(1, 40)
        with mock.patch.object(config, "TELEGRAM_DELETE_AFTER_HOURS", 0), \
             mock.patch("core.notifier.requests.post") as post:
            result = self.notifier.purge_telegram_messages()
        self.assertEqual(result, {"deleted": 0, "gone": 0, "failed": 0})
        post.assert_not_called()

    def test_an_explicit_zero_deletes_every_message_now(self):
        for mid in (1, 2):
            self.db.record_telegram_message("42", mid)
        with mock.patch("core.notifier.requests.post", return_value=_response()) as post:
            result = self.notifier.purge_telegram_messages(older_than_hours=0)
        self.assertEqual(result["deleted"], 2)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(self.db.get_expired_telegram_messages(0), [])

    def test_nothing_is_sent_without_a_token(self):
        self.db.record_telegram_message("42", 1)
        with mock.patch.object(config, "TELEGRAM_BOT_TOKEN", ""), \
             mock.patch("core.notifier.requests.post") as post:
            result = self.notifier.purge_telegram_messages(older_than_hours=0)
        self.assertEqual(result["deleted"], 0)
        post.assert_not_called()
        self.assertEqual(len(self.db.get_expired_telegram_messages(0)), 1)


if __name__ == "__main__":
    unittest.main()
