"""
Tests du téléchargement du modèle MediaPipe (telecharger_modeles.py). Aucun accès réseau : requests est
remplacé par un double et tout se passe dans un dossier temporaire (models/ n'est pas touché).

    .venv-deepface\\Scripts\\python.exe -m unittest tests.test_telecharger_modeles -v
"""

import hashlib
import os
import shutil
import tempfile
import unittest
from unittest import mock

import requests

import telecharger_modeles as tm

CONTENU = b"contenu-du-modele"
EMPREINTE = hashlib.sha256(CONTENU).hexdigest()


def _reponse(contenu):
    r = mock.Mock()
    r.content = contenu
    r.raise_for_status.return_value = None
    return r


class TelechargerModelesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="biogate-modeles-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.cible = os.path.join(self.dir, "models", "face_landmarker.task")

    def _telecharger(self):
        return tm.telecharger(self.cible, url="http://exemple.test/m.task", sha256=EMPREINTE)

    def test_a_missing_model_is_downloaded_and_written(self):
        with mock.patch("telecharger_modeles.requests.get", return_value=_reponse(CONTENU)) as get:
            self.assertEqual(self._telecharger(), "telecharge")
        get.assert_called_once()
        self.assertEqual(open(self.cible, "rb").read(), CONTENU)
        self.assertEqual(os.listdir(os.path.dirname(self.cible)), ["face_landmarker.task"])  # pas de .part

    def test_a_conforming_model_is_not_downloaded_again(self):
        os.makedirs(os.path.dirname(self.cible))
        with open(self.cible, "wb") as f:
            f.write(CONTENU)
        with mock.patch("telecharger_modeles.requests.get") as get:
            self.assertEqual(self._telecharger(), "present")
        get.assert_not_called()

    def test_a_corrupted_download_is_refused_and_leaves_nothing(self):
        with mock.patch("telecharger_modeles.requests.get", return_value=_reponse(b"incomplet")):
            with self.assertRaises(RuntimeError):
                self._telecharger()
        self.assertEqual(os.listdir(os.path.dirname(self.cible)), [])

    def test_a_corrupted_local_model_is_replaced(self):
        os.makedirs(os.path.dirname(self.cible))
        with open(self.cible, "wb") as f:
            f.write(b"abime")
        with mock.patch("telecharger_modeles.requests.get", return_value=_reponse(CONTENU)):
            self.assertEqual(self._telecharger(), "telecharge")
        self.assertEqual(open(self.cible, "rb").read(), CONTENU)

    def test_a_network_failure_gives_a_readable_error(self):
        with mock.patch("telecharger_modeles.requests.get", side_effect=requests.exceptions.ConnectionError("x")):
            with self.assertRaises(RuntimeError) as ctx:
                self._telecharger()
        self.assertIn("Internet", str(ctx.exception))
        self.assertFalse(os.path.exists(self.cible))


if __name__ == "__main__":
    unittest.main()
