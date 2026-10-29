"""
Tests de la purge RGPD des photos d'intrus (automatique et manuelle).

Base SQLite ET dossier de photos TEMPORAIRES : ni la vraie base biométrique ni les vraies
photos de database/snapshots ne sont touchées (tout test qui déclenche une purge redirige
explicitement api.SNAPSHOT_DIR).

    .venv-deepface\\Scripts\\python.exe -m unittest tests.test_rgpd_purge -v
"""

import asyncio
import os
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

import config

config.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="biogate-test-"), "visages.db")

import api  # noqa: E402  (après la redirection de config.DB_PATH)
from fastapi import HTTPException  # noqa: E402

AUTH = "Bearer test-token"
run = asyncio.run


def photo(directory, name, age_hours=0.0):
    """Crée une fausse photo dont la date de modification a `age_hours` heures."""
    path = os.path.join(directory, name)
    with open(path, "wb") as f:
        f.write(b"\xff\xd8\xff\xd9")
    t = time.time() - age_hours * 3600
    os.utime(path, (t, t))
    return path


class PurgeTestCase(unittest.TestCase):
    def setUp(self):
        self.db = api.face_recognizer.db
        self.dir = tempfile.mkdtemp(prefix="biogate-snap-")
        conn = sqlite3.connect(self.db.db_path)
        conn.execute("DELETE FROM event_logs")
        conn.commit()
        conn.close()
        api._dashboard_token = "test-token"

    def log(self, name, age_hours, path=None, event="INTRUDER_CONFIRMED"):
        self.db.log_event(name, 0.0, event_type=event, snapshot_path=path)
        conn = sqlite3.connect(self.db.db_path)
        conn.execute(
            "UPDATE event_logs SET timestamp = datetime('now', ?) WHERE id = (SELECT MAX(id) FROM event_logs)",
            (f"-{age_hours} hours",),
        )
        conn.commit()
        conn.close()

    def rows(self):
        conn = sqlite3.connect(self.db.db_path)
        conn.row_factory = sqlite3.Row
        result = [dict(r) for r in conn.execute("SELECT id, snapshot_path FROM event_logs ORDER BY id")]
        conn.close()
        return result


class AutomaticPurgeTest(PurgeTestCase):
    def test_expired_photo_is_deleted_but_the_journal_line_stays(self):
        old = photo(self.dir, "old.jpg", 100)
        new = photo(self.dir, "new.jpg", 1)
        self.log("Intrus_001", 100, old)
        self.log("Intrus_002", 1, new)

        result = self.db.purge_expired_snapshots(72, self.dir)

        self.assertEqual(result, {"photos": 1, "orphans": 0})
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(new))
        rows = self.rows()
        self.assertEqual(len(rows), 2, "l'historique du journal ne doit jamais être supprimé par la purge automatique")
        self.assertIsNone(rows[0]["snapshot_path"])
        self.assertEqual(rows[1]["snapshot_path"], new)

    def test_old_events_without_photo_are_untouched(self):
        self.log("Hugues", 500, None, event="VIP_ENTRY")
        self.db.purge_expired_snapshots(72, self.dir)
        self.assertEqual(len(self.rows()), 1)

    def test_retention_is_honoured(self):
        path = photo(self.dir, "a.jpg", 30)
        self.log("Intrus_001", 30, path)
        self.assertEqual(self.db.purge_expired_snapshots(48, self.dir)["photos"], 0)
        self.assertTrue(os.path.exists(path))
        self.assertEqual(self.db.purge_expired_snapshots(24, self.dir)["photos"], 1)
        self.assertFalse(os.path.exists(path))

    def test_default_retention_comes_from_the_config(self):
        path = photo(self.dir, "a.jpg", 30)
        self.log("Intrus_001", 30, path)
        with mock.patch.object(config, "RGPD_SNAPSHOT_RETENTION_HOURS", 24):
            self.assertEqual(self.db.purge_expired_snapshots(None, self.dir)["photos"], 1)

    def test_a_fresh_event_survives_a_short_retention_whatever_the_timezone(self):
        # SQLite horodate en UTC ; l'ancienne coupure en heure locale purgeait un événement
        # tout neuf dès que le décalage horaire dépassait la rétention (UTC+1 au Bénin).
        path = photo(self.dir, "a.jpg", 0)
        self.log("Intrus_001", 0, path)
        self.assertEqual(self.db.purge_expired_snapshots(1, self.dir)["photos"], 0)
        self.assertTrue(os.path.exists(path))

    def test_an_event_two_hours_old_is_purged_with_one_hour_retention(self):
        path = photo(self.dir, "a.jpg", 2)
        self.log("Intrus_001", 2, path)
        self.assertEqual(self.db.purge_expired_snapshots(1, self.dir)["photos"], 1)

    def test_missing_file_for_an_expired_event_is_handled(self):
        self.log("Intrus_001", 100, os.path.join(self.dir, "disparue.jpg"))
        self.assertEqual(self.db.purge_expired_snapshots(72, self.dir)["photos"], 1)
        self.assertIsNone(self.rows()[0]["snapshot_path"])

    def test_old_orphan_photo_is_deleted(self):
        orphan = photo(self.dir, "orphan.jpg", 100)
        self.assertEqual(self.db.purge_expired_snapshots(72, self.dir), {"photos": 0, "orphans": 1})
        self.assertFalse(os.path.exists(orphan))

    def test_young_orphan_photo_is_kept(self):
        young = photo(self.dir, "young.jpg", 10)
        self.assertEqual(self.db.purge_expired_snapshots(72, self.dir)["orphans"], 0)
        self.assertTrue(os.path.exists(young))

    def test_orphans_are_never_swept_in_less_than_an_hour_even_with_a_tiny_retention(self):
        # la photo d'une intrusion en cours de confirmation n'a pas encore de ligne de journal
        pending = photo(self.dir, "pending.jpg", 0.5)
        self.assertEqual(self.db.purge_expired_snapshots(0.01, self.dir)["orphans"], 0)
        self.assertTrue(os.path.exists(pending))

    def test_a_referenced_photo_is_never_an_orphan(self):
        path = photo(self.dir, "ref.jpg", 100)  # vieux fichier, mais l'événement est récent
        self.log("Intrus_001", 1, path)
        self.assertEqual(self.db.purge_expired_snapshots(72, self.dir), {"photos": 0, "orphans": 0})
        self.assertTrue(os.path.exists(path))

    def test_only_images_are_swept(self):
        note = photo(self.dir, "notes.txt", 500)
        self.db.purge_expired_snapshots(72, self.dir)
        self.assertTrue(os.path.exists(note))

    def test_missing_snapshot_directory_is_not_an_error(self):
        self.assertEqual(self.db.purge_expired_snapshots(72, os.path.join(self.dir, "absent")), {"photos": 0, "orphans": 0})


class ManualPurgeTest(PurgeTestCase):
    def test_manual_purge_removes_old_events_with_their_photos_and_the_orphans(self):
        old = photo(self.dir, "old.jpg", 100)
        recent = photo(self.dir, "recent.jpg", 1)
        orphan = photo(self.dir, "orphan.jpg", 100)
        self.log("Intrus_001", 100, old)
        self.log("Intrus_002", 1, recent)

        deleted = self.db.purge_old_snapshots(72, self.dir)

        self.assertEqual(deleted, 1)
        self.assertEqual([r["snapshot_path"] for r in self.rows()], [recent])
        self.assertFalse(os.path.exists(old))
        self.assertFalse(os.path.exists(orphan))
        self.assertTrue(os.path.exists(recent))

    def test_manual_purge_does_not_remove_a_fresh_event_either(self):
        path = photo(self.dir, "a.jpg", 0)
        self.log("Intrus_001", 0, path)
        self.assertEqual(self.db.purge_old_snapshots(1, self.dir), 0)
        self.assertEqual(len(self.rows()), 1)


class SchedulerTest(PurgeTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(api, "SNAPSHOT_DIR", self.dir)  # JAMAIS le vrai dossier
        patcher.start()
        self.addCleanup(patcher.stop)
        api._rgpd_status.update(last_run=None, photos=0, orphans=0, error=None)

    @staticmethod
    async def _stop_after_first_pass(_seconds):
        raise asyncio.CancelledError

    def test_loop_purges_then_records_what_it_did(self):
        path = photo(self.dir, "old.jpg", 100)
        self.log("Intrus_001", 100, path)
        with mock.patch.object(api.asyncio, "sleep", self._stop_after_first_pass):
            with self.assertRaises(asyncio.CancelledError):
                run(api._rgpd_purge_loop())
        self.assertFalse(os.path.exists(path))
        self.assertIsNotNone(api._rgpd_status["last_run"])
        self.assertEqual((api._rgpd_status["photos"], api._rgpd_status["orphans"]), (1, 0))
        self.assertIsNone(api._rgpd_status["error"])

    def test_loop_sleeps_for_the_configured_interval(self):
        slept = []

        async def record(seconds):
            slept.append(seconds)
            raise asyncio.CancelledError

        with mock.patch.object(config, "RGPD_PURGE_INTERVAL_MINUTES", 15), \
             mock.patch.object(api.asyncio, "sleep", record):
            with self.assertRaises(asyncio.CancelledError):
                run(api._rgpd_purge_loop())
        self.assertEqual(slept, [15 * 60])

    def test_a_failing_purge_never_kills_the_loop(self):
        with mock.patch.object(self.db, "purge_expired_snapshots", side_effect=RuntimeError("disque plein")), \
             mock.patch.object(api.asyncio, "sleep", self._stop_after_first_pass):
            with self.assertRaises(asyncio.CancelledError):  # atteint le sommeil : l'erreur a bien été absorbée
                run(api._rgpd_purge_loop())
        self.assertEqual(api._rgpd_status["error"], "RuntimeError")

    def test_server_startup_launches_the_task_and_shutdown_stops_it(self):
        async def scenario():
            async with api.lifespan(api.app):
                task = api._rgpd_task
                self.assertIsNotNone(task)
                self.assertFalse(task.done())
            await asyncio.sleep(0.05)
            return task

        task = run(scenario())
        self.assertTrue(task.cancelled())


class RoutesTest(PurgeTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(api, "SNAPSHOT_DIR", self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_every_log_and_rgpd_route_requires_the_token(self):
        calls = (
            lambda a: api.get_logs(limit=5, offset=0, event_type=None, name=None, date_from=None, date_to=None, authorization=a),
            lambda a: api.get_log_stats(authorization=a),
            lambda a: api.purge_logs(retention_hours=None, authorization=a),
            lambda a: api.delete_log(1, authorization=a),
            lambda a: api.rgpd_status(authorization=a),
        )
        for call in calls:
            for bad in (None, "Bearer faux"):
                with self.assertRaises(HTTPException) as ctx:
                    run(call(bad))
                self.assertEqual(ctx.exception.status_code, 401)

    def test_logs_are_served_with_a_valid_token(self):
        self.log("Intrus_001", 1, None)
        resp = run(api.get_logs(limit=5, offset=0, event_type=None, name=None, date_from=None, date_to=None, authorization=AUTH))
        self.assertTrue(resp["success"])
        self.assertEqual(resp["count"], 1)

    def test_manual_purge_route_works_with_a_token(self):
        old = photo(self.dir, "old.jpg", 100)
        self.log("Intrus_001", 100, old)
        resp = run(api.purge_logs(retention_hours=72, authorization=AUTH))
        self.assertEqual(resp, {"success": True, "deleted": 1})
        self.assertFalse(os.path.exists(old))

    def test_deleting_one_log_also_deletes_its_photo(self):
        path = photo(self.dir, "a.jpg", 1)
        self.log("Intrus_001", 1, path)
        log_id = self.rows()[0]["id"]
        run(api.delete_log(log_id, authorization=AUTH))
        self.assertFalse(os.path.exists(path))
        self.assertEqual(self.rows(), [])

    def test_status_reports_the_retention_and_what_is_on_disk(self):
        photo(self.dir, "a.jpg", 5)
        photo(self.dir, "b.jpg", 50)
        status = run(api.rgpd_status(authorization=AUTH))
        self.assertEqual(status["snapshots_on_disk"], 2)
        self.assertAlmostEqual(status["oldest_snapshot_hours"], 50, delta=0.2)
        self.assertEqual(status["retention_hours"], config.RGPD_SNAPSHOT_RETENTION_HOURS)
        self.assertEqual(status["interval_minutes"], config.RGPD_PURGE_INTERVAL_MINUTES)

    def test_status_with_an_empty_folder(self):
        status = run(api.rgpd_status(authorization=AUTH))
        self.assertEqual(status["snapshots_on_disk"], 0)
        self.assertIsNone(status["oldest_snapshot_hours"])


if __name__ == "__main__":
    unittest.main()
