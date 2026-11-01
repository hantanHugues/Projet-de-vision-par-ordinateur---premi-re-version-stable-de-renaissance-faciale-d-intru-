"""
Télécharge le modèle MediaPipe « face_landmarker.task » dans models/.

Il sert au test de vivacité et au second avis contre les faux visages (un pli de vêtement pris pour un
visage). Il n'est pas dans le dépôt Git (les fichiers .task sont ignorés) : sans lui, le test de vivacité
ne démarre pas et le filtre de visage retombe sur la seule détection de Haar.

    .venv-deepface\\Scripts\\python.exe telecharger_modeles.py

L'empreinte SHA-256 du fichier est vérifiée : un fichier incomplet ou modifié est refusé.
YOLOv8 et FaceNet512 n'ont pas besoin de cette étape : leurs poids se téléchargent seuls au premier usage.
"""

import hashlib
import os
import sys
import tempfile

import requests

URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
DESTINATION = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "face_landmarker.task")


def _empreinte(chemin):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def telecharger(destination=DESTINATION, url=URL, sha256=SHA256):
    """Retourne « present » (déjà là et conforme) ou « telecharge ». Lève RuntimeError sinon."""
    if os.path.isfile(destination) and _empreinte(destination) == sha256:
        return "present"

    os.makedirs(os.path.dirname(destination), exist_ok=True)
    fd, temporaire = tempfile.mkstemp(dir=os.path.dirname(destination), suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            try:
                reponse = requests.get(url, timeout=60)
                reponse.raise_for_status()
            except requests.exceptions.RequestException as exc:
                raise RuntimeError(f"Téléchargement impossible ({exc.__class__.__name__}). Vérifiez la connexion Internet.") from None
            f.write(reponse.content)
        if _empreinte(temporaire) != sha256:
            raise RuntimeError("Le fichier reçu n'a pas l'empreinte attendue : il est refusé.")
        os.replace(temporaire, destination)
    finally:
        if os.path.exists(temporaire):
            os.remove(temporaire)
    return "telecharge"


if __name__ == "__main__":
    try:
        etat = telecharger()
    except RuntimeError as exc:
        print(f"Échec : {exc}")
        sys.exit(1)
    print("Modèle déjà présent et conforme." if etat == "present" else f"Modèle téléchargé : {DESTINATION}")
