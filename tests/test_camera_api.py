"""
Tests de la clé du flux des caméras IP : elle ne sort jamais en clair de GET /cameras, et changer
seulement l'adresse (l'IP d'une carte change) ne demande pas de la retaper.

Base SQLite temporaire : la vraie base (database/visages.db) n'est ni lue ni modifiée. Aucune
vraie caméra n'est démarrée (le gestionnaire de caméras est remplacé par un double).

    .venv-deepface\\Scripts\\python.exe -m unittest tests.test_camera_api -v
"""

import asyncio
import os
import tempfile
import unittest
from unittest import mock

import config

config.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="biogate-test-"), "visages.db")

import api  # noqa: E402  (après la redirection de config.DB_PATH)
from core.camera_manager import URL_MASK, mask_url_password, restore_url_password  # noqa: E402
from fastapi import HTTPException  # noqa: E402

AUTH = "Bearer test-token"
CLE = "cle-de-test-sans-valeur-0123"
ADRESSE = f"http://biogate:{CLE}@192.168.0.201/stream"


def run(coro):
    return asyncio.run(coro)


class MaskUrlTest(unittest.TestCase):
    def test_the_password_of_an_address_is_replaced_by_stars(self):
        self.assertEqual(mask_url_password(ADRESSE), f"http://biogate:{URL_MASK}@192.168.0.201/stream")

    def test_port_path_and_query_are_kept(self):
        masque = mask_url_password("rtsp://admin:secret@10.0.0.5:554/live/ch0?x=1")
        self.assertEqual(masque, f"rtsp://admin:{URL_MASK}@10.0.0.5:554/live/ch0?x=1")

    def test_an_ipv6_host_keeps_its_brackets(self):
        self.assertEqual(mask_url_password("http://u:p@[fe80::1]:8080/s"), f"http://u:{URL_MASK}@[fe80::1]:8080/s")

    def test_addresses_without_a_password_are_untouched(self):
        for url in ("http://192.168.1.50/stream", "http://biogate@192.168.1.50/stream", "/chemin/video.mp4", "", None):
            self.assertEqual(mask_url_password(url), url)

    def test_the_real_password_is_never_left_in_the_masked_address(self):
        self.assertNotIn(CLE, mask_url_password(ADRESSE))

    def test_changing_only_the_ip_keeps_the_stored_password(self):
        nouvelle = f"http://biogate:{URL_MASK}@192.168.0.77/stream"
        self.assertEqual(restore_url_password(nouvelle, ADRESSE), f"http://biogate:{CLE}@192.168.0.77/stream")

    def test_a_new_password_typed_by_the_user_is_kept(self):
        self.assertEqual(restore_url_password("http://biogate:NouvelleCle99@192.168.0.77/stream", ADRESSE),
                         "http://biogate:NouvelleCle99@192.168.0.77/stream")

    def test_without_a_stored_password_the_address_is_left_as_received(self):
        nouvelle = f"http://biogate:{URL_MASK}@192.168.0.77/stream"
        self.assertEqual(restore_url_password(nouvelle, "http://192.168.0.201/stream"), nouvelle)
        self.assertEqual(restore_url_password(nouvelle, None), nouvelle)

    def test_masking_then_restoring_gives_back_the_original(self):
        self.assertEqual(restore_url_password(mask_url_password(ADRESSE), ADRESSE), ADRESSE)

    def test_addresses_without_stars_are_never_modified(self):
        for url in ("http://192.168.1.50/stream", ADRESSE, "", None):
            self.assertEqual(restore_url_password(url, ADRESSE), url)


class CameraRoutesTest(unittest.TestCase):
    def setUp(self):
        api._dashboard_token = "test-token"
        manager = mock.patch.object(api, "cam_mgr")
        self.cam_mgr = manager.start()
        self.cam_mgr.all_info.return_value = []
        self.addCleanup(manager.stop)
        self.cam_id = run(api.add_camera(
            api._CameraBody(name="Carte test", type="mjpeg", url=ADRESSE, zone="Entrée"), authorization=AUTH
        ))["cam_id"]
        self.addCleanup(lambda: api.face_recognizer.db.delete_camera(self.cam_id))

    def stocke(self):
        return api.face_recognizer.db.get_camera(self.cam_id)["url"]

    def liste(self):
        cameras = run(api.list_cameras(authorization=AUTH))["cameras"]
        return next(c for c in cameras if c["cam_id"] == self.cam_id)

    def test_the_list_shows_the_address_without_the_key(self):
        self.assertEqual(self.liste()["url"], f"http://biogate:{URL_MASK}@192.168.0.201/stream")
        self.assertNotIn(CLE, str(run(api.list_cameras(authorization=AUTH))))

    def test_the_real_key_is_still_stored_and_given_to_the_camera(self):
        self.assertEqual(self.stocke(), ADRESSE)
        cfg = self.cam_mgr.add.call_args.args[1]
        self.assertEqual(cfg["url"], ADRESSE)

    def test_changing_only_the_ip_from_the_masked_address_keeps_the_key(self):
        nouvelle = f"http://biogate:{URL_MASK}@192.168.0.88/stream"
        run(api.update_camera(self.cam_id, api._CameraBody(name="Carte test", type="mjpeg", url=nouvelle, zone="Entrée"),
                              authorization=AUTH))
        self.assertEqual(self.stocke(), f"http://biogate:{CLE}@192.168.0.88/stream")
        self.assertEqual(self.cam_mgr.add.call_args.args[1]["url"], f"http://biogate:{CLE}@192.168.0.88/stream")
        self.assertEqual(self.liste()["url"], f"http://biogate:{URL_MASK}@192.168.0.88/stream")

    def test_a_new_key_typed_in_the_address_replaces_the_old_one(self):
        run(api.update_camera(self.cam_id, api._CameraBody(name="Carte test", type="mjpeg",
                                                           url="http://biogate:AutreCle0000@192.168.0.201/stream"),
                              authorization=AUTH))
        self.assertEqual(self.stocke(), "http://biogate:AutreCle0000@192.168.0.201/stream")

    def test_renaming_with_the_address_sent_back_unchanged_loses_nothing(self):
        """C'est ce que fait la page quand on ne change que le nom : elle renvoie l'adresse masquée."""
        masquee = self.liste()["url"]
        run(api.update_camera(self.cam_id, api._CameraBody(name="Entrée principale", type="mjpeg", url=masquee),
                              authorization=AUTH))
        self.assertEqual(self.stocke(), ADRESSE)
        self.assertEqual(api.face_recognizer.db.get_camera(self.cam_id)["name"], "Entrée principale")

    def test_the_camera_is_restarted_on_the_new_address(self):
        self.cam_mgr.add.reset_mock()
        run(api.update_camera(self.cam_id, api._CameraBody(name="Carte test", type="mjpeg",
                                                           url=f"http://biogate:{URL_MASK}@192.168.0.99/stream"),
                              authorization=AUTH))
        self.cam_mgr.add.assert_called_once()
        self.assertEqual(self.cam_mgr.add.call_args.args[0], self.cam_id)

    def test_updating_an_unknown_camera_is_a_404(self):
        with self.assertRaises(HTTPException) as ctx:
            run(api.update_camera("inconnue", api._CameraBody(name="x"), authorization=AUTH))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_the_camera_routes_require_the_token(self):
        for appel in (
            lambda: api.list_cameras(authorization=None),
            lambda: api.update_camera(self.cam_id, api._CameraBody(name="x"), authorization="Bearer faux"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                run(appel())
            self.assertEqual(ctx.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
