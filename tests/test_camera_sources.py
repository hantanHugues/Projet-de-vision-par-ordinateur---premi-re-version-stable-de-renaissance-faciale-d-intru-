"""
Tests des sources vidéo : un fichier et un flux MJPEG par HTTP protégé par identifiant, lus par
CameraSource comme le fait BioGate (OpenCV ouvre l'adresse telle quelle).

Le faux flux imite ce que fait le programme de la carte BW21 (firmware/bw21_camera_protegee) :
même entête, mêmes morceaux « chunked », même réponse 401 avec « Connection: close ». Il
enregistre chaque requête reçue, ce qui montre comment OpenCV s'authentifie (avant la
première requête, ou après un refus).

Ni YOLO ni FaceNet, aucune caméra réelle. RTSP n'est pas testé : il faudrait un serveur RTSP.

    .venv-deepface\\Scripts\\python.exe -m unittest tests.test_camera_sources -v
"""

import base64
import os
import socket
import tempfile
import threading
import time
import unittest

import cv2
import numpy as np

from core.camera_manager import CameraSource

IDENTIFIANT = "biogate"
CLE = "Cle1234567890Test"
BOUNDARY = "123456789000000000000987654321"


class FauxFlux:
    """Serveur HTTP minimal qui se comporte comme la carte : /stream, identifiant et clé, flux MJPEG."""

    def __init__(self, frontiere_initiale=True):
        # Le programme de la carte envoie la ligne de séparation AVANT la première image
        # (DEBUT_FLUX). Sans elle, OpenCV ne lit aucune image : voir le dernier test.
        self.frontiere_initiale = frontiere_initiale
        self.requetes = []          # (chemin, avec_identifiants, statut)
        self._actif = True
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(5)
        self.port = self._sock.getsockname()[1]
        self._jeton = base64.b64encode(f"{IDENTIFIANT}:{CLE}".encode()).decode()
        threading.Thread(target=self._accepter, daemon=True).start()

    def adresse(self, identifiant=IDENTIFIANT, cle=CLE):
        auth = f"{identifiant}:{cle}@" if identifiant else ""
        return f"http://{auth}127.0.0.1:{self.port}/stream"

    def fermer(self):
        self._actif = False
        try:
            self._sock.close()
        except OSError:
            pass

    def _accepter(self):
        while self._actif:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._servir, args=(conn,), daemon=True).start()

    def _lire_requete(self, conn):
        conn.settimeout(3)
        donnees = b""
        while b"\r\n\r\n" not in donnees and len(donnees) < 4096:
            morceau = conn.recv(1024)
            if not morceau:
                break
            donnees += morceau
        lignes = donnees.decode("latin-1").split("\r\n")
        entetes = {}
        for ligne in lignes[1:]:
            if ":" in ligne:
                nom, valeur = ligne.split(":", 1)
                entetes[nom.strip().lower()] = valeur.strip()
        return lignes[0], entetes

    def _servir(self, conn):
        try:
            ligne, entetes = self._lire_requete(conn)
            chemin = ligne.split(" ")[1] if ligne.count(" ") >= 2 else "?"
            auth = entetes.get("authorization", "")
            if not ligne.startswith("GET /stream "):
                self.requetes.append((chemin, bool(auth), 404))
                conn.sendall(b"HTTP/1.1 404 Not Found\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
            elif auth.lower() != f"basic {self._jeton}".lower():
                self.requetes.append((chemin, bool(auth), 401))
                conn.sendall(b'HTTP/1.1 401 Unauthorized\r\nConnection: close\r\nContent-Length: 0\r\n'
                             b'WWW-Authenticate: Basic realm="BioGate"\r\n\r\n')
            else:
                self.requetes.append((chemin, True, 200))
                self._diffuser(conn)
        except (OSError, socket.timeout):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _diffuser(self, conn):
        def morceau(octets):
            conn.sendall(f"{len(octets):X}\r\n".encode() + octets + b"\r\n")

        conn.sendall(f"HTTP/1.1 200 OK\r\nContent-type: multipart/x-mixed-replace; boundary={BOUNDARY}\r\n"
                     f"Transfer-Encoding: chunked\r\n\r\n".encode())
        if self.frontiere_initiale:
            morceau(f"--{BOUNDARY}\r\n".encode())
        numero = 0
        while self._actif:
            image = np.full((120, 160, 3), (numero * 7) % 255, dtype=np.uint8)
            cv2.putText(image, str(numero), (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            ok, jpg = cv2.imencode(".jpg", image)
            octets = jpg.tobytes()
            morceau(f"Content-Type: image/jpeg\r\nContent-Length: {len(octets)}\r\n\r\n".encode())
            morceau(octets)
            morceau(f"\r\n--{BOUNDARY}\r\n".encode())
            numero += 1
            time.sleep(0.03)


def lire_source(cfg, attendu=5, delai=12):
    """Démarre une CameraSource comme BioGate, attend `attendu` images ou `delai` secondes, l'arrête."""
    images, etats = [], []

    def recevoir(cam_id, frame):
        images.append(frame)
        if len(images) == 1:
            etats.append(source.connected)    # une vidéo se lit si vite qu'elle finit avant la fin du test

    source = CameraSource("test", cfg, on_frame=recevoir, draw_fn=None)
    source.start()
    fin = time.time() + delai
    while time.time() < fin and len(images) < attendu:
        time.sleep(0.1)
    connecte = etats[0] if etats else source.connected
    source._running = False
    return source, images, connecte


class FichierVideoTest(unittest.TestCase):
    def test_a_video_file_is_read_as_a_camera(self):
        dossier = tempfile.mkdtemp(prefix="biogate-test-")
        chemin = os.path.join(dossier, "essai.avi")
        ecrivain = cv2.VideoWriter(chemin, cv2.VideoWriter_fourcc(*"MJPG"), 15, (160, 120))
        for i in range(20):
            ecrivain.write(np.full((120, 160, 3), i * 10, dtype=np.uint8))
        ecrivain.release()

        source, images, connecte = lire_source({"type": "file", "url": chemin})
        self.assertGreaterEqual(len(images), 5)
        self.assertEqual(images[0].shape, (120, 160, 3))
        self.assertTrue(connecte)
        source._thread.join(5)


class FluxHttpProtegeTest(unittest.TestCase):
    def setUp(self):
        self.flux = FauxFlux()
        self.addCleanup(self.flux.fermer)

    def lire(self, adresse, **kw):
        source, images, connecte = lire_source({"type": "mjpeg", "url": adresse}, **kw)
        self.flux.fermer()
        source._thread.join(8)
        return images, connecte

    def test_a_protected_mjpeg_stream_is_read_with_the_credentials_in_the_address(self):
        images, connecte = self.lire(self.flux.adresse())
        self.assertGreaterEqual(len(images), 5, f"requêtes vues par le faux flux : {self.flux.requetes}")
        self.assertEqual(images[0].shape, (120, 160, 3))
        self.assertTrue(connecte)
        self.assertEqual(self.flux.requetes[-1][2], 200)

    def test_the_images_really_change_from_one_frame_to_the_next(self):
        images, _ = self.lire(self.flux.adresse(), attendu=8)
        niveaux = {int(i.mean()) for i in images}
        self.assertGreater(len(niveaux), 3, "les images doivent se suivre, pas se répéter")

    def test_a_wrong_key_gives_no_image(self):
        images, connecte = self.lire(self.flux.adresse(cle="MauvaiseCle1234567"), attendu=1, delai=6)
        self.assertEqual(len(images), 0)
        self.assertFalse(connecte)
        self.assertTrue(all(statut == 401 for _, _, statut in self.flux.requetes), self.flux.requetes)

    def test_no_credentials_gives_no_image(self):
        images, connecte = self.lire(self.flux.adresse(identifiant=None), attendu=1, delai=6)
        self.assertEqual(len(images), 0)
        self.assertFalse(connecte)
        self.assertTrue(all(statut == 401 for _, _, statut in self.flux.requetes), self.flux.requetes)

    def test_without_the_opening_boundary_opencv_reads_nothing(self):
        """
        Pourquoi le programme de la carte envoie DEBUT_FLUX : l'exemple de Realtek ne l'envoyait
        pas, et un navigateur s'en passe, mais OpenCV (donc BioGate) ne lisait alors aucune image.
        """
        self.flux.fermer()
        self.flux = FauxFlux(frontiere_initiale=False)
        self.addCleanup(self.flux.fermer)
        images, connecte = self.lire(self.flux.adresse(), attendu=1, delai=8)
        self.assertEqual(len(images), 0)
        self.assertTrue(any(statut == 200 for _, _, statut in self.flux.requetes),
                        "la connexion est acceptée : c'est bien le format du flux qui bloque")

    def test_how_opencv_authenticates(self):
        """Documente le comportement réel d'OpenCV : une requête sans identifiants avant la bonne, ou directement la bonne."""
        self.lire(self.flux.adresse(), attendu=3)
        premiere = next(i for i, r in enumerate(self.flux.requetes) if r[2] == 200)
        avant_succes = self.flux.requetes[:premiere]
        print(f"\n[OpenCV] requêtes refusées avant la première image : {len(avant_succes)} ; toutes : {self.flux.requetes[:4]}")
        self.assertLessEqual(len(avant_succes), 1, "au plus une requête refusée avant d'envoyer les identifiants")


if __name__ == "__main__":
    unittest.main()
