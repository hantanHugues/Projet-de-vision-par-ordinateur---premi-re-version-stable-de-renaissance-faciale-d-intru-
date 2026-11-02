"""
Mesure, à la webcam, l'effet de l'apprentissage continu sur UN profil enrôlé.

Pendant la capture, la chaîne est celle de BioGate : YOLOv8 repère la silhouette de la personne, Haar cherche le
visage DANS ce recadrage (et non sur l'image entière : le visage y est plus grand, donc bien mieux trouvé en
faible lumière), le second avis de MediaPipe écarte les faux visages, puis le visage est transformé par le code même
de BioGate (FaceRecognizer._extract_face_signature : CLAHE, FaceNet512, alignement) puis comparée en distance
cosinus. Pour les MÊMES images, on compare la distance :
  - au seul vecteur d'origine du profil (le premier enregistré : l'enrôlement) ;
  - au plus proche de tous les vecteurs du profil (enrôlement + vecteurs ajoutés par l'apprentissage) ;
  - au plus proche des vecteurs des AUTRES profils (marge avant une confusion).

La base est ouverte en lecture seule : aucun vecteur n'est modifié, aucune image n'est enregistrée
(seules les distances le sont).

Usage :
    .venv-deepface\\Scripts\\python.exe tests\\mesures\\mesure_apprentissage_webcam.py <profil> <dossier_sortie> [delai_s] [duree_s] [attente_lumiere_s]

Sorties : distances_webcam.csv (une ligne par image) et rapport_apprentissage_webcam.md.
"""

import csv
import json
import os
import sqlite3
import sys
import tempfile
import time

import cv2
import numpy as np

RACINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from mesure_far_frr import distance_cosinus, materiel  # noqa: E402

SEUIL_BIOGATE = 0.35
LUMINOSITE_MIN = 80    # sur 255 : en dessous, la séance est refusée (la pièce est trop sombre pour une mesure fiable)
IMAGES_MIN = 30       # en dessous, la séance est déclarée insuffisante dans le rapport
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "database", "visages.db")


def lire_vecteurs(profil):
    """Retourne (vecteurs du profil dans l'ordre d'enregistrement, vecteurs des autres profils), base en lecture seule."""
    chemin = os.path.abspath(BASE).replace("\\", "/")
    conn = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
    ligne = conn.execute("SELECT id FROM profiles WHERE name = ?", (profil,)).fetchone()
    if ligne is None:
        raise SystemExit(f"Profil introuvable : {profil}")
    propres = [np.array(json.loads(v), dtype=np.float32) for (v,) in conn.execute(
        "SELECT vector_json FROM embeddings WHERE profile_id = ? ORDER BY id", (ligne[0],))]
    autres = [np.array(json.loads(v), dtype=np.float32) for (v,) in conn.execute(
        "SELECT vector_json FROM embeddings WHERE profile_id != ? ORDER BY id", (ligne[0],))]
    conn.close()
    return propres, autres


def resume(valeurs):
    v = np.array(valeurs)
    return {"moyenne": float(v.mean()), "mediane": float(np.median(v)), "ecart_type": float(v.std()),
            "p90": float(np.percentile(v, 90)), "min": float(v.min()), "max": float(v.max()),
            "reconnues": int((v < SEUIL_BIOGATE).sum())}


def luminosite(cam, secondes=2.0):
    """Luminosité moyenne (0 = noir, 255 = blanc) de la webcam sur quelques secondes, sans rien enregistrer."""
    valeurs, fin = [], time.time() + secondes
    while time.time() < fin:
        ok, image = cam.read()
        if ok:
            valeurs.append(float(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).mean()))
    return float(np.mean(valeurs)) if valeurs else 0.0


def attendre_lumiere(cam, attente_max):
    """Refuse de démarrer tant que l'image est trop sombre ; attend jusqu'à `attente_max` secondes que la pièce soit éclairée."""
    debut = time.time()
    while True:
        lum = luminosite(cam)
        print(f"Luminosité de la webcam : {lum:.0f} sur 255 (minimum exigé : {LUMINOSITE_MIN}).", flush=True)
        if lum >= LUMINOSITE_MIN:
            return lum
        if time.time() - debut >= attente_max:
            raise SystemExit(f"Pièce trop sombre ({lum:.0f} sur 255) : allumez la lumière, ouvrez les rideaux ou placez-vous face à la fenêtre, "
                             "et vérifiez que rien ne cache l'objectif. Aucune mesure n'a été faite.")
        time.sleep(1.0)


def main(profil, sortie, delai=20.0, duree=30.0, attente=0.0):
    os.makedirs(sortie, exist_ok=True)
    propres, autres = lire_vecteurs(profil)
    if len(propres) < 2:
        raise SystemExit("Le profil n'a qu'un vecteur : rien à comparer.")
    print(f"Profil {profil} : {len(propres)} vecteurs ; autres profils : {len(autres)} vecteur(s).", flush=True)

    # Le module de reconnaissance de BioGate, avec une base TEMPORAIRE : la vraie n'est lue qu'en lecture seule plus haut.
    import config
    config.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="biogate-mesure-"), "visages.db")
    from core.face_recognizer import FaceRecognizer
    from core.logger import VisualLogger
    fr = FaceRecognizer(logger=VisualLogger(), trust_mgr=None)
    fr._extract_face_signature(np.zeros((160, 160, 3), np.uint8))   # charge FaceNet avant le décompte
    fr._get_landmarker()                                            # et le second avis MediaPipe
    from ultralytics import YOLO
    yolo = YOLO(os.path.join(RACINE, "yolov8n.pt"))

    cam = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cam.isOpened():
        raise SystemExit("Webcam inaccessible (fermez le serveur BioGate et le tableau de bord).")
    for _ in range(5):
        cam.read()
    lum_debut = attendre_lumiere(cam, attente)
    print(f"Placez-vous devant la webcam. Début dans {delai:.0f} s, durée {duree:.0f} s.", flush=True)
    t_debut = time.time() + delai
    while time.time() < t_debut:
        cam.read()  # garde l'image fraîche
    print("CAPTURE EN COURS", flush=True)

    lignes, sans_visage, rejetes, sans_personne, lums = [], 0, 0, 0, []
    fin = time.time() + duree
    while time.time() < fin:
        ok, image = cam.read()
        if not ok:
            continue
        lums.append(float(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).mean()))
        # 1. Silhouette de la personne (YOLOv8 nano, 320 px, confiance 0,5 : réglages de BioGate)
        boites = yolo.predict(image, imgsz=320, conf=0.5, classes=[0], verbose=False)[0].boxes.xyxy.cpu().numpy()
        if not len(boites):
            sans_personne += 1
            continue
        x1, y1, x2, y2 = (int(v) for v in max(boites, key=lambda b: (b[2] - b[0]) * (b[3] - b[1])))
        silhouette = image[max(0, y1):y2, max(0, x1):x2]
        # 2. Face Gate : Haar dans la silhouette, puis second avis MediaPipe
        gris = cv2.equalizeHist(cv2.cvtColor(silhouette, cv2.COLOR_BGR2GRAY))
        visages = fr.face_cascade.detectMultiScale(gris, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        if not len(visages):
            sans_visage += 1
            continue
        if not fr._confirm_face(silhouette, visages[0]):
            rejetes += 1   # faux visage écarté par MediaPipe, comme le ferait BioGate
            continue
        x, y, w, h = (int(v) for v in visages[0])
        s = fr._extract_face_signature(silhouette[y:y + h, x:x + w])
        if s is None:
            continue
        d_origine = distance_cosinus(s, propres[0])
        d_tous = min(distance_cosinus(s, v) for v in propres)
        d_autres = min((distance_cosinus(s, v) for v in autres), default=float("nan"))
        lignes.append((d_origine, d_tous, d_autres))
    cam.release()
    print(f"Capture terminée : {len(lignes)} images retenues, {rejetes} faux visages écartés, {sans_visage} silhouettes sans visage, {sans_personne} sans personne.", flush=True)
    if not lignes:
        raise SystemExit("Aucun visage détecté pendant la capture.")

    with open(os.path.join(sortie, "distances_webcam.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["image", "distance_vecteur_origine", "distance_profil_complet", "distance_autres_profils"])
        for i, (a, b, c) in enumerate(lignes, 1):
            w.writerow([i, f"{a:.4f}", f"{b:.4f}", "" if np.isnan(c) else f"{c:.4f}"])

    orig, tous = [l[0] for l in lignes], [l[1] for l in lignes]
    autres_d = [l[2] for l in lignes if not np.isnan(l[2])]
    r_o, r_t = resume(orig), resume(tous)
    n = len(lignes)
    gagne = sum(1 for a, b in zip(orig, tous) if b < a)
    marge = [a - t for a, t in zip(autres_d, tous[:len(autres_d)])] if autres_d else []
    lignes_md = [
        f"# Effet de l'apprentissage continu, mesuré à la webcam (profil enrôlé)",
        "",
        f"*Généré par `tests/mesures/mesure_apprentissage_webcam.py` le {time.strftime('%d/%m/%Y à %H:%M')}.*",
        "",
        "## Protocole",
        "",
        f"- Un profil enrôlé de **{len(propres)} vecteurs** : le premier est l'enrôlement d'origine, les autres ont été ajoutés par l'apprentissage continu (confirmation par empreinte).",
        f"- Capture à la webcam pendant {duree:.0f} s, la personne regardant la caméra : **{n} images retenues** (silhouette trouvée par YOLO, visage de face trouvé par Haar dans la silhouette et confirmé par MediaPipe), {rejetes} faux visages écartés par MediaPipe, {sans_visage} silhouettes sans visage de face, {sans_personne} images sans personne détectée.",
        "- Chaîne de BioGate : YOLOv8 (silhouette), Face Gate (Haar dans la silhouette + second avis MediaPipe), puis `FaceRecognizer._extract_face_signature` (CLAHE, FaceNet512, alignement), distance cosinus. La base est lue en lecture seule ; aucune image n'est enregistrée.",
        "- Pour **les mêmes images**, on compare la distance au seul vecteur d'origine et la distance au plus proche des vecteurs du profil complet.",
        f"- **Conditions** : luminosité moyenne de la webcam pendant la séance **{np.mean(lums):.0f} sur 255** (la mesure refuse de démarrer sous {LUMINOSITE_MIN}) ; "
        f"séance du {time.strftime('%d/%m/%Y à %H:%M')}.",
        (f"- **ATTENTION : séance insuffisante** ({n} images retenues, minimum {IMAGES_MIN}) : ne citer aucune de ces valeurs." if n < IMAGES_MIN
         else f"- Séance suffisante : {n} images retenues (minimum {IMAGES_MIN})."),
        "",
        "## Résultats",
        "",
        "| Référence | Moyenne | Médiane | Écart-type | 90e centile | Min | Max | Images sous 0,35 |",
        "|---|---|---|---|---|---|---|---|",
        f"| Vecteur d'origine seul | {r_o['moyenne']:.3f} | {r_o['mediane']:.3f} | {r_o['ecart_type']:.3f} | {r_o['p90']:.3f} | {r_o['min']:.3f} | {r_o['max']:.3f} | {r_o['reconnues']} sur {n} |",
        f"| Profil complet ({len(propres)} vecteurs) | {r_t['moyenne']:.3f} | {r_t['mediane']:.3f} | {r_t['ecart_type']:.3f} | {r_t['p90']:.3f} | {r_t['min']:.3f} | {r_t['max']:.3f} | {r_t['reconnues']} sur {n} |",
        "",
        f"- Baisse de la distance moyenne : **{r_o['moyenne']:.3f} → {r_t['moyenne']:.3f}** (différence {r_o['moyenne'] - r_t['moyenne']:.3f}).",
        f"- Le profil complet est plus proche que le seul vecteur d'origine pour **{gagne} images sur {n}**.",
    ]
    if autres_d:
        lignes_md += [
            f"- Distance au plus proche **autre** profil : moyenne {np.mean(autres_d):.3f}, minimum {min(autres_d):.3f}. "
            f"Écart moyen avec le profil complet : {np.mean(marge):.3f} (une valeur faible ou négative signale un risque de confusion).",
        ]
    lignes_md += [
        "",
        "## Limites",
        "",
        "- Une seule personne, une seule séance, un seul éclairage : l'ordre de grandeur est utile, pas une garantie.",
        "- Les images consécutives sont très proches les unes des autres : leur nombre ne vaut pas un nombre égal de mesures indépendantes.",
        "- Le profil complet contient plus de vecteurs que le vecteur d'origine : prendre le minimum sur plusieurs références baisse mécaniquement la distance. La mesure montre l'ampleur de cet effet sur ce visage, pas une meilleure reconnaissance en toutes conditions.",
        "",
        "## Matériel et versions",
        "",
    ] + [f"- {k} : {v}" for k, v in materiel().items()]
    with open(os.path.join(sortie, "rapport_apprentissage_webcam.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lignes_md) + "\n")
    print(f"Distance moyenne : vecteur d'origine {r_o['moyenne']:.3f} -> profil complet {r_t['moyenne']:.3f}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2],
         float(sys.argv[3]) if len(sys.argv) > 3 else 20.0,
         float(sys.argv[4]) if len(sys.argv) > 4 else 30.0,
         float(sys.argv[5]) if len(sys.argv) > 5 else 0.0)
