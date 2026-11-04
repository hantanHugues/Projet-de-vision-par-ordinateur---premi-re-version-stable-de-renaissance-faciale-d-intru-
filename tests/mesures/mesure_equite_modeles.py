"""
Équité des modèles de BioGate selon la région et le sexe : clignement (MediaPipe) et reconnaissance (FaceNet512).

Deux questions, toutes deux posées sur les photos de Wikimedia Commons de mesure_vieillissement_commons.py (licence libre, datées,
nom de la personne dans le nom du fichier ; non copiées dans le dépôt) :

1. Clignement. Le défi de vivacité compte un clignement quand la moyenne des scores blendshapes eyeBlinkLeft/Right dépasse 0,35
   (core/liveness_detector.py). Si le score d'un œil OUVERT est déjà proche de 0,35 chez certaines personnes (paupière plus basse,
   yeux plus fendus, lunettes, sourire qui plisse les yeux), le défi est moins fiable pour elles : clignement « compté » sans clignement,
   ou marge trop faible pour détecter un vrai clignement. On mesure ici le score de base, œil ouvert, et la part de photos au-dessus du seuil.
   NON mesuré : la sensibilité (un œil fermé est-il bien détecté ?). Elle exige des vidéos de clignements réels ou des photos d'yeux fermés
   étiquetées, que ce jeu de données ne fournit pas.

2. Reconnaissance. Pour chaque personne : distance médiane à ses propres photos (même personne) et distance à la PERSONNE DIFFÉRENTE la
   plus proche (le « sosie » : celle qui risque d'être acceptée à tort). Chaîne de BioGate (Haar + MediaPipe puis CLAHE + FaceNet512).
   Les paires « même personne » dépendent de l'exactitude des noms de fichiers ; les paires « personnes différentes » sont sûres.

Unité statistique : la personne (les photos d'une même personne ne sont pas indépendantes). Moyenne par groupe, IC à 95 % par
rééchantillonnage des personnes (graine fixe). Effectifs petits : on décrit, on ne conclut pas à un biais.

Usage :
    .venv-deepface\\Scripts\\python.exe -I tests\\mesures\\mesure_equite_modeles.py <candidats_journal.csv> <dossier_sortie>
"""

import csv
import json
import os
import sys
import tempfile
import time

import cv2
import numpy as np

RACINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from mesure_far_frr import materiel, signature, distance_cosinus  # noqa: E402
import mesure_vieillissement_commons as mv  # noqa: E402

SEUIL_CLIGNEMENT = 0.35  # core/liveness_detector.py : BLINK_THRESHOLD
SEUIL_VISAGE = 0.35
EMB_MAX = 5  # vecteurs gardés par personne (répartis dans le temps) : même nombre de comparaisons pour tous


def blendshapes(landmarker, mp, image):
    """(clignement moyen, sourire moyen) si exactement un visage d'au moins VISAGE_MIN px, sinon None."""
    rgb = np.ascontiguousarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    res = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    if len(res.face_landmarks) != 1:
        return None
    xs = [p.x for p in res.face_landmarks[0]]
    if (max(xs) - min(xs)) * image.shape[1] < mv.VISAGE_MIN:
        return None
    bs = {b.category_name: b.score for b in res.face_blendshapes[0]}
    return (bs.get("eyeBlinkLeft", 0) + bs.get("eyeBlinkRight", 0)) / 2, (bs.get("mouthSmileLeft", 0) + bs.get("mouthSmileRight", 0)) / 2


def ic(valeurs, graine=1, rep=5000):
    v = np.array(valeurs, dtype=float)
    if len(v) == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(graine)
    m = [rng.choice(v, len(v)).mean() for _ in range(rep)]
    return float(v.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def main(csv_journal, sortie):
    os.makedirs(sortie, exist_ok=True)
    t0 = time.time()
    with open(csv_journal, encoding="utf-8") as f:
        journal = [j for j in csv.DictReader(f) if not j["statut"].startswith("catégorie")]
    import config
    config.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="biogate-equite-"), "visages.db")
    from core.face_recognizer import FaceRecognizer
    from core.logger import VisualLogger
    from deepface import DeepFace
    fr_ = FaceRecognizer(logger=VisualLogger(), trust_mgr=None)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    options = mp_vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=os.path.join(RACINE, "models", "face_landmarker.task")),
        output_face_blendshapes=True, num_faces=2, min_face_detection_confidence=0.5, min_face_presence_confidence=0.5)
    landmarker = mp_vision.FaceLandmarker.create_from_options(options)
    dossier = os.environ.get("BIOGATE_PHOTOS") or tempfile.mkdtemp(prefix="biogate-equite-photos-")

    def lister_en_cache(nom):
        """Liste des photos d'une personne : lue sur le disque si déjà demandée, sinon demandée à Commons puis gardée."""
        chemin_cache = os.path.join(dossier, "listes_commons.json")
        try:
            cache = json.load(open(chemin_cache, encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
        if nom not in cache:
            cache[nom] = mv.lister(nom)
            json.dump(cache, open(chemin_cache, "w", encoding="utf-8"))
        return cache[nom]

    P = []
    for j in journal:
        fichiers = lister_en_cache(j["nom"])
        garde, _ = mv.echantillon(fichiers, j["nom"])
        p = {"nom": j["nom"], "region": j["region"], "sexe": j["sexe"], "photos": 0, "blink": [], "smile": [], "emb": []}
        for f in garde:
            chemin = mv.telecharger(f, dossier)
            image = cv2.imread(chemin) if chemin else None
            if image is None:
                continue
            p["photos"] += 1
            b = blendshapes(landmarker, mp, image)
            if b:
                p["blink"].append(b[0])
                p["smile"].append(b[1])
            rect, _ = mv.visage_unique(fr_, image)
            if rect is not None:
                p["emb"].append(signature(DeepFace, clahe, fr_.face_cascade, image, {"haar": 0, "entiere": 0}))
        P.append(p)
        print(f"  {p['nom']:28s} : {p['photos']:3d} photos, {len(p['blink']):3d} lues par MediaPipe, {len(p['emb']):3d} validées pour FaceNet", flush=True)

    # --- 1. clignement
    for p in P:
        p["blink_med"] = float(np.median(p["blink"])) if len(p["blink"]) >= 3 else None
        p["blink_haut"] = float(np.mean([b > SEUIL_CLIGNEMENT for b in p["blink"]])) if len(p["blink"]) >= 3 else None
    # --- 2. reconnaissance
    for p in P:
        if len(p["emb"]) > EMB_MAX:
            idx = np.linspace(0, len(p["emb"]) - 1, EMB_MAX).round().astype(int)
            p["emb"] = [p["emb"][k] for k in idx]
    for i, p in enumerate(P):
        E = p["emb"]
        gen = [distance_cosinus(E[a], E[b]) for a in range(len(E)) for b in range(a + 1, len(E))]
        p["gen_med"] = float(np.median(gen)) if gen else None
        autres = [distance_cosinus(e, o) for k, q in enumerate(P) if k != i for o in q["emb"] for e in E]
        p["imp_taux"] = float(np.mean([d < SEUIL_VISAGE for d in autres])) if autres and E else None
        p["imp_sous_seuil"] = int(sum(d < SEUIL_VISAGE for d in autres)) if autres else 0
        p["imp_total"] = len(autres)

    with open(os.path.join(sortie, "equite_personnes.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["personne", "sexe", "region", "photos", "photos_lues_mediapipe", "blink_median", "part_blink_sup_0_35", "photos_facenet",
                    "distance_meme_personne_mediane", "part_paires_autres_personnes_sous_0_35"])
        for n, p in enumerate(P, 1):
            w.writerow([f"P{n:02d}", p["sexe"], p["region"], p["photos"], len(p["blink"]),
                        "" if p["blink_med"] is None else f"{p['blink_med']:.4f}", "" if p["blink_haut"] is None else f"{p['blink_haut']:.4f}",
                        len(p["emb"]), "" if p["gen_med"] is None else f"{p['gen_med']:.4f}", "" if p["imp_taux"] is None else f"{p['imp_taux']:.5f}"])

    def table(cle, valeurs, titre, champ, fmt):
        L = [f"| {titre} | Personnes | Moyenne par personne [IC 95 %] |", "|---|---|---|"]
        for v in valeurs:
            S = [p[champ] for p in P if p[cle] == v and p[champ] is not None]
            if S:
                m, lo, hi = ic(S)
                L.append(f"| {v} | {len(S)} | {mv.fr(fmt * m, 3 if fmt == 1 else 1)}{' %' if fmt == 100 else ''} [{mv.fr(fmt * lo, 3 if fmt == 1 else 1)} ; {mv.fr(fmt * hi, 3 if fmt == 1 else 1)}] |")
        return L

    pers_blink = [p for p in P if p["blink_med"] is not None]
    pers_rec = [p for p in P if p["imp_taux"] is not None]
    R = ["# Équité des modèles : clignement et reconnaissance selon la région et le sexe", "",
         f"*Généré par `tests/mesures/mesure_equite_modeles.py` le {time.strftime('%d/%m/%Y à %H:%M')}.*", "",
         "## Protocole", "",
         f"- {len(P)} personnes examinées, {sum(p['photos'] for p in P)} photos de Wikimedia Commons (mêmes règles que `mesure_vieillissement_commons.py`).",
         f"- Clignement : {len(pers_blink)} personnes avec au moins 3 photos où MediaPipe voit un seul visage d'au moins {mv.VISAGE_MIN} px. Score = moyenne de eyeBlinkLeft et eyeBlinkRight, comme `liveness_detector.py` ; seuil de BioGate {SEUIL_CLIGNEMENT}. Une photo prise pendant un vrai clignement fait monter le score : on prend la **médiane** par personne.",
         f"- Reconnaissance : {len(pers_rec)} personnes avec au moins une photo validée par le filtre de BioGate et une autre personne à comparer ; chaîne Haar + MediaPipe, CLAHE, FaceNet512.",
         "- **Unité : la personne.** IC à 95 % par rééchantillonnage des personnes.", "",
         "## 1. Score de clignement d'un œil ouvert (plus bas = plus de marge avant le seuil de 0,35)", ""]
    R += table("region", mv.REGIONS, "Région", "blink_med", 1) + [""] + table("sexe", ["F", "M"], "Sexe", "blink_med", 1)
    R += ["", "Part de photos au-dessus du seuil de clignement (œil supposé ouvert)", ""]
    R += table("region", mv.REGIONS, "Région", "blink_haut", 100) + [""] + table("sexe", ["F", "M"], "Sexe", "blink_haut", 100)
    R += ["", "## 2. Reconnaissance", "", "Distance médiane entre deux photos de la même personne (plus bas = mieux reconnue)", ""]
    R += table("region", mv.REGIONS, "Région", "gen_med", 1) + [""] + table("sexe", ["F", "M"], "Sexe", "gen_med", 1)
    R += ["", f"Part des comparaisons avec une AUTRE personne de l'échantillon qui passent sous le seuil de 0,35 (fausses acceptations potentielles ; au plus {EMB_MAX} photos par personne, pour que chacun ait le même nombre de comparaisons)", ""]
    R += table("region", mv.REGIONS, "Région", "imp_taux", 100) + [""] + table("sexe", ["F", "M"], "Sexe", "imp_taux", 100)
    tot_imp = sum(p["imp_sous_seuil"] for p in P)
    R += ["", f"Au total : {tot_imp} comparaisons sur {sum(p['imp_total'] for p in P)} (chaque paire comptée deux fois, une par personne).", "",
          "## Limites", "",
          "- Le clignement mesuré est le score d'un œil **ouvert**. La sensibilité (détecter un vrai clignement) n'est pas mesurée ici.",
          "- Photos de célébrités, de presse : sourires, maquillage, lunettes, poses variables. Un score élevé peut venir de l'expression et pas de l'œil.",
          "- Région = nationalité. Aucun visage vérifié à la main. Effectifs de quelques personnes par groupe : **ces tableaux décrivent l'échantillon, ils ne prouvent pas un biais.**",
          "", "## Matériel et versions", ""] + [f"- {k} : {v}" for k, v in materiel().items()] + [f"- Durée : {time.time() - t0:.0f} s"]
    with open(os.path.join(sortie, "rapport_equite.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(R) + "\n")
    print("Rapport écrit dans", sortie, flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
