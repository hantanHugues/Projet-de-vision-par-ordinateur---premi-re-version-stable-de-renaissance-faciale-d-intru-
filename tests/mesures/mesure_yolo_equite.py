"""
Détecteur de silhouettes de BioGate (YOLOv8n) selon la région et le sexe.

Question : quand une personne est devant la caméra, YOLO trouve-t-il sa silhouette aussi souvent quelle que soit son origine
ou son sexe ? C'est la première étape de la chaîne : sans silhouette, aucune reconnaissance n'a lieu.

PROTOCOLE FIXÉ AVANT TOUT RÉSULTAT (aucun réglage après coup) :
- Photos : celles de Wikimedia Commons déjà téléchargées par mesure_equite_modeles.py (même règle d'échantillonnage, mêmes personnes).
  Aucune requête réseau : une photo absente du cache est ignorée.
- Une photo est ADMISE si MediaPipe y voit exactement UN visage d'au moins 70 px : c'est la preuve qu'une personne est présente.
- Appel de YOLO identique à la production : core.yolo_detector.YoloDetector.detect_humans (yolov8n.pt, 320 px, confiance 0,5,
  IoU 0,35, puis NMS à 0,30).
- Réussite d'une photo : au moins une silhouette dont la boîte CONTIENT le centre du visage vu par MediaPipe.
- Unité statistique : la PERSONNE (taux de réussite par personne, au moins 3 photos admises), moyenne par groupe, IC à 95 % par
  rééchantillonnage des personnes (graine fixe).
- Variable de contrôle : taille du visage par rapport à la largeur de l'image (plan large, moyen, gros plan). Un gros plan est une
  scène peu favorable à un détecteur de personnes : sans ce contrôle, un écart entre groupes pourrait venir du cadrage.
- Sensibilité : même mesure à 640 px (la production utilise 320 px pour économiser le processeur).

Limites annoncées d'avance : photos de presse (portraits et plans moyens), pas une caméra de porte avec silhouette entière ; la présence
d'une personne est définie par un visage détectable, donc les personnes sans visage détectable sont exclues ; effectifs de quelques
personnes par groupe : la mesure décrit l'échantillon, elle ne prouve pas un biais.

Usage (depuis la racine du dépôt) :
    .venv-deepface\\Scripts\\python.exe -I tests\\mesures\\mesure_yolo_equite.py <candidats_journal.csv> <dossier_cache_photos> <dossier_sortie> [limite_personnes]

Sorties : yolo_equite_personnes.csv, rapport_yolo_equite.md.
"""

import csv
import json
import os
import platform
import re
import sys
import time

import cv2
import numpy as np

RACINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
import mesure_vieillissement_commons as mv  # noqa: E402

PHOTOS_MIN = 3
PLANS = [("plan large (visage < 15 % de la largeur)", 0.0, 0.15), ("plan moyen (15 à 30 %)", 0.15, 0.30), ("gros plan (≥ 30 %)", 0.30, 9.0)]


def ic(valeurs, graine=1, rep=5000):
    v = np.array(valeurs, dtype=float)
    if len(v) == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(graine)
    m = [rng.choice(v, len(v)).mean() for _ in range(rep)]
    return float(v.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def visage_mediapipe(landmarker, mp, image):
    """(centre_x, centre_y, fraction de largeur) si exactement un visage d'au moins VISAGE_MIN px, sinon None."""
    rgb = np.ascontiguousarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    res = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    if len(res.face_landmarks) != 1:
        return None
    h, w = image.shape[:2]
    xs = [p.x for p in res.face_landmarks[0]]
    ys = [p.y for p in res.face_landmarks[0]]
    largeur = (max(xs) - min(xs)) * w
    if largeur < mv.VISAGE_MIN:
        return None
    return (min(xs) + max(xs)) / 2 * w, (min(ys) + max(ys)) / 2 * h, largeur / w


def contient(boite, cx, cy):
    x1, y1, x2, y2 = boite
    return x1 <= cx <= x2 and y1 <= cy <= y2


def main(csv_journal, dossier, sortie, limite=None):
    os.makedirs(sortie, exist_ok=True)
    t0 = time.time()
    with open(csv_journal, encoding="utf-8") as f:
        journal = [j for j in csv.DictReader(f) if not j["statut"].startswith("catégorie")]
    if limite:
        journal = journal[:limite]
    with open(os.path.join(dossier, "listes_commons.json"), encoding="utf-8") as f:
        listes = json.load(f)

    from core.logger import VisualLogger
    from core.yolo_detector import YoloDetector
    detecteur = YoloDetector(VisualLogger())
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    options = mp_vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=os.path.join(RACINE, "models", "face_landmarker.task")),
        num_faces=2, min_face_detection_confidence=0.5, min_face_presence_confidence=0.5)
    landmarker = mp_vision.FaceLandmarker.create_from_options(options)

    P, photos = [], []
    for j in journal:
        if j["nom"] not in listes:
            continue
        garde, _ = mv.echantillon(listes[j["nom"]], j["nom"])
        p = {"nom": j["nom"], "region": j["region"], "sexe": j["sexe"], "admises": 0, "ok320": 0, "ok640": 0}
        for f in garde:
            chemin = os.path.join(dossier, re.sub(r"[^A-Za-z0-9]+", "_", f["titre"])[:90] + ".jpg")
            image = cv2.imread(chemin) if os.path.exists(chemin) else None
            if image is None:
                continue
            v = visage_mediapipe(landmarker, mp, image)
            if v is None:
                continue
            cx, cy, frac = v
            r320 = any(contient(d["box"], cx, cy) for d in detecteur.detect_humans(image))
            res640 = detecteur._model(image, conf=0.5, classes=[0], verbose=False, imgsz=640, iou=0.35)
            r640 = any(contient(b.xyxy[0].cpu().numpy(), cx, cy) for r in res640 for b in r.boxes)
            p["admises"] += 1
            p["ok320"] += r320
            p["ok640"] += r640
            photos.append({"nom": j["nom"], "region": j["region"], "sexe": j["sexe"], "frac": frac, "r320": r320, "r640": r640})
        P.append(p)
        print(f"  {p['nom']:28s} : {p['admises']:3d} photos admises, silhouette trouvée à 320 px {p['ok320']:3d}, à 640 px {p['ok640']:3d}", flush=True)

    for p in P:
        p["t320"] = p["ok320"] / p["admises"] if p["admises"] >= PHOTOS_MIN else None
        p["t640"] = p["ok640"] / p["admises"] if p["admises"] >= PHOTOS_MIN else None

    with open(os.path.join(sortie, "yolo_equite_personnes.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["personne", "sexe", "region", "photos_admises", "silhouette_320px", "silhouette_640px"])
        for n, p in enumerate(P, 1):
            w.writerow([f"P{n:02d}", p["sexe"], p["region"], p["admises"], p["ok320"], p["ok640"]])

    retenues = [p for p in P if p["t320"] is not None]

    def table(cle, valeurs, titre):
        L = [f"| {titre} | Personnes | Silhouette trouvée à 320 px (production) [IC 95 %] | À 640 px [IC 95 %] |", "|---|---|---|---|"]
        for v in valeurs:
            G = [p for p in retenues if p[cle] == v]
            if not G:
                continue
            a, la, ha = ic([p["t320"] for p in G])
            b, lb, hb = ic([p["t640"] for p in G])
            L.append(f"| {v} | {len(G)} | {mv.fr(100 * a)} % [{mv.fr(100 * la)} ; {mv.fr(100 * ha)}] | {mv.fr(100 * b)} % [{mv.fr(100 * lb)} ; {mv.fr(100 * hb)}] |")
        return L

    tableau_plans = ["| Cadrage | Photos | Silhouette trouvée à 320 px | À 640 px |", "|---|---|---|---|"]
    for nom, lo, hi in PLANS:
        S = [x for x in photos if lo <= x["frac"] < hi]
        if S:
            tableau_plans.append(f"| {nom} | {len(S)} | {mv.fr(100 * np.mean([x['r320'] for x in S]))} % | {mv.fr(100 * np.mean([x['r640'] for x in S]))} % |")

    taille = {}
    for cle, valeurs in (("region", mv.REGIONS), ("sexe", ["F", "M"])):
        for v in valeurs:
            S = [x["frac"] for x in photos if x[cle] == v]
            if S:
                taille[v] = (len(S), float(np.median(S)))

    R = ["# Détecteur de silhouettes (YOLOv8n) selon la région et le sexe", "",
         f"*Généré par `tests/mesures/mesure_yolo_equite.py` le {time.strftime('%d/%m/%Y à %H:%M')}.*", "",
         "## Protocole (fixé avant tout résultat)", "",
         f"- {len(journal)} personnes examinées, {len(photos)} photos admises (exactement un visage d'au moins {mv.VISAGE_MIN} px vu par MediaPipe), "
         f"{len(retenues)} personnes avec au moins {PHOTOS_MIN} photos admises. Photos de Wikimedia Commons déjà téléchargées pour `mesure_equite_modeles.py`.",
         "- Appel de YOLO identique à la production (`YoloDetector.detect_humans` : yolov8n.pt, 320 px, confiance 0,5, IoU 0,35, NMS 0,30).",
         "- Réussite d'une photo : une silhouette dont la boîte contient le centre du visage.",
         "- **Unité : la personne.** IC à 95 % par rééchantillonnage des personnes. Sensibilité : même mesure à 640 px.", "",
         "## Résultats par groupe", ""] + table("region", mv.REGIONS, "Région") + [""] + table("sexe", ["F", "M"], "Sexe") + [
         "", "## Contrôle du cadrage", "",
         "Un gros plan est peu favorable à un détecteur de personnes. Taux de réussite selon la taille du visage dans l'image (toutes personnes confondues) :", ""] + tableau_plans + [
         "", "Taille médiane du visage (fraction de la largeur de l'image) par groupe : " + ", ".join(f"{k} {mv.fr(100 * m[1], 0)} % ({m[0]} photos)" for k, m in taille.items()) + ".", "",
         "## Limites", "",
         "- Photos de presse, portraits et plans moyens : pas une caméra de porte avec silhouette entière.",
         "- La présence d'une personne est définie par un visage détectable : les personnes sans visage détectable sont exclues.",
         "- Effectifs de quelques personnes par groupe : **cette mesure décrit l'échantillon, elle ne prouve pas un biais.**",
         "- Un écart entre groupes peut venir du cadrage plutôt que de la personne : voir le contrôle ci-dessus.", "",
         "## Matériel et versions", ""]
    import ultralytics
    import mediapipe
    R += [f"- Système : {platform.platform()}", f"- Processeur : {platform.processor()}", f"- Python : {platform.python_version()}",
          f"- Ultralytics : {ultralytics.__version__}", f"- OpenCV : {cv2.__version__}", f"- MediaPipe : {mediapipe.__version__}", f"- Durée : {time.time() - t0:.0f} s"]
    with open(os.path.join(sortie, "rapport_yolo_equite.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(R) + "\n")
    print("Rapport écrit dans", sortie, flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else None)
