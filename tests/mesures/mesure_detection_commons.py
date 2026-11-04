"""
Filtre de visage de BioGate (Haar puis second avis MediaPipe) contre MediaPipe seul, sur les photos de Wikimedia Commons
examinées par mesure_vieillissement_commons.py, selon la région et le sexe.

Pourquoi : BioGate ne lance FaceNet que si Haar trouve UN visage de face. Si ce premier filtre laisse passer moins souvent
certaines personnes ou certaines conditions, ces personnes sont moins bien servies AVANT même la reconnaissance. Cette mesure
chiffre le taux de validation du filtre actuel et celui d'un filtre MediaPipe seul, sur les mêmes photos.

Unité statistique : la PERSONNE (les photos d'une même personne ne sont pas indépendantes) : taux par personne, moyenne par groupe,
intervalle de confiance à 95 % par rééchantillonnage des personnes. Les photos viennent de Commons (licence libre, datées, nom de la
personne dans le nom du fichier) ; elles ne sont pas copiées dans le dépôt.

Limites à retenir : les motifs de rejet dépendent aussi du type de photo (événement, groupe, pose) et pas seulement de la personne ;
MediaPipe détecte un visage quelle que soit la pose, alors que Haar exige un visage de face (nécessaire à FaceNet) : le MediaPipe seul
n'est donc pas, tel quel, un remplaçant ; la mesure dit où le premier filtre perd des visages, pas quoi mettre à la place.

Usage :
    .venv-deepface\\Scripts\\python.exe tests\\mesures\\mesure_detection_commons.py <dossier_vieillissement> <dossier_sortie>
    (le dossier de la mesure précédente contient candidats_journal.csv et photos_temporaires/)

Sorties : detection_personnes.csv, rapport_detection.md.
"""

import csv
import os
import sys
import tempfile
import time

import cv2
import numpy as np

RACINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from mesure_far_frr import materiel  # noqa: E402
import mesure_vieillissement_commons as mv  # noqa: E402


def mediapipe_seul(landmarker, mp, image):
    """Nombre de visages d'au moins VISAGE_MIN px vus par MediaPipe (toutes poses)."""
    rgb = np.ascontiguousarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    res = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    w = image.shape[1]
    n = 0
    for pts in res.face_landmarks:
        xs = [p.x for p in pts]
        if (max(xs) - min(xs)) * w >= mv.VISAGE_MIN:
            n += 1
    return n


def resume_groupe(lignes, cle, valeurs, champ):
    T = []
    for v in valeurs:
        P = [l for l in lignes if l[cle] == v and l["testees"] > 0]
        if not P:
            continue
        taux = [l[champ] / l["testees"] for l in P]
        m, lo, hi = mv.ic_moyenne(taux)
        T.append((v, len(P), sum(l["testees"] for l in P), m, lo, hi))
    return T


def main(dossier_v, sortie):
    os.makedirs(sortie, exist_ok=True)
    t0 = time.time()
    with open(os.path.join(dossier_v, "candidats_journal.csv"), encoding="utf-8") as f:
        journal = [j for j in csv.DictReader(f) if not j["statut"].startswith("catégorie")]
    import config
    config.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="biogate-det-"), "visages.db")
    from core.face_recognizer import FaceRecognizer
    from core.logger import VisualLogger
    fr_ = FaceRecognizer(logger=VisualLogger(), trust_mgr=None)
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    options = mp_vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=os.path.join(RACINE, "models", "face_landmarker.task")),
        num_faces=4, min_face_detection_confidence=0.5, min_face_presence_confidence=0.5)
    landmarker = mp_vision.FaceLandmarker.create_from_options(options)
    dossier = os.path.join(dossier_v, "photos_temporaires")

    lignes = []
    for j in journal:
        fichiers = mv.lister(j["nom"])
        garde, _ = mv.echantillon(fichiers, j["nom"])
        c = {"nom": j["nom"], "region": j["region"], "sexe": j["sexe"], "testees": 0, "haar_mp_ok": 0, "mp_un": 0, "mp_aucun": 0, "mp_plusieurs": 0}
        for f in garde:
            chemin = mv.telecharger(f, dossier)
            image = cv2.imread(chemin) if chemin else None
            if image is None:
                continue
            c["testees"] += 1
            rect, _ = mv.visage_unique(fr_, image)
            c["haar_mp_ok"] += rect is not None
            n = mediapipe_seul(landmarker, mp, image)
            c["mp_un"] += n == 1
            c["mp_aucun"] += n == 0
            c["mp_plusieurs"] += n > 1
        lignes.append(c)
        print(f"  {j['nom']:28s} : {c['testees']:3d} photos, filtre de BioGate {c['haar_mp_ok']:3d}, MediaPipe seul (un visage) {c['mp_un']:3d}", flush=True)

    with open(os.path.join(sortie, "detection_personnes.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["personne", "sexe", "region", "photos_testees", "filtre_BioGate_valide", "mediapipe_seul_un_visage", "mediapipe_aucun", "mediapipe_plusieurs"])
        for i, c in enumerate(lignes, 1):
            w.writerow([f"P{i:02d}", c["sexe"], c["region"], c["testees"], c["haar_mp_ok"], c["mp_un"], c["mp_aucun"], c["mp_plusieurs"]])

    def table(cle, valeurs, titre):
        A, B = resume_groupe(lignes, cle, valeurs, "haar_mp_ok"), resume_groupe(lignes, cle, valeurs, "mp_un")
        L = [f"| {titre} | Personnes | Photos testées | Filtre actuel de BioGate (Haar + MediaPipe) : un visage de face validé | MediaPipe seul : exactement un visage |", "|---|---|---|---|---|"]
        for a, b in zip(A, B):
            L.append(f"| {a[0]} | {a[1]} | {a[2]} | {mv.fr(100 * a[3])} % [{mv.fr(100 * a[4])} ; {mv.fr(100 * a[5])}] | {mv.fr(100 * b[3])} % [{mv.fr(100 * b[4])} ; {mv.fr(100 * b[5])}] |")
        return L

    tot = sum(c["testees"] for c in lignes)
    R = [
        "# Le filtre de visage de BioGate selon la région et le sexe",
        "",
        f"*Généré par `tests/mesures/mesure_detection_commons.py` le {time.strftime('%d/%m/%Y à %H:%M')}.*",
        "",
        "## Protocole",
        "",
        f"- {len(lignes)} personnes, {tot} photos de Wikimedia Commons (licence libre, datées, nom de la personne dans le nom du fichier, largeur d'au moins 400 px), les mêmes que `mesure_vieillissement_commons.py`.",
        "- Pour chaque photo : (1) le filtre actuel de BioGate : Haar de face, un seul visage d'au moins 70 px, confirmé par MediaPipe ; (2) MediaPipe seul : exactement un visage d'au moins 70 px, quelle que soit la pose.",
        "- **Unité statistique : la personne.** Taux de validation par personne, moyenne par groupe, intervalle de confiance à 95 % (entre crochets) par rééchantillonnage des personnes.",
        "",
        "## Résultats",
        "",
    ] + table("region", mv.REGIONS, "Région") + [""] + table("sexe", ["F", "M"], "Sexe") + [
        "",
        "Les effectifs par groupe sont petits et les photos varient (événements, groupes, poses) : **ces tableaux décrivent l'échantillon, ils ne prouvent pas un biais du détecteur**. "
        "Ils justifient en revanche de **tester le filtre de visage sur des visages variés avant tout déploiement**, ce que le chapitre 3 doit présenter comme limite et perspective.",
        "",
        "## Limites",
        "",
        "- Les motifs de rejet dépendent du type de photo : photos d'événement avec plusieurs personnes (« plusieurs visages »), poses de profil, lumière de scène.",
        "- MediaPipe seul détecte un visage quelle que soit la pose, alors que Haar exige un visage de face (nécessaire à FaceNet) : il n'est pas, tel quel, un remplaçant du filtre actuel.",
        "- Échantillon de célébrités, photos de presse : pas une caméra de porte. Les effectifs par groupe interdisent toute conclusion sur des différences entre groupes.",
        "",
        "## Matériel et versions",
        "",
    ] + [f"- {k} : {v}" for k, v in materiel().items()] + [f"- Durée : {time.time() - t0:.0f} s"]
    with open(os.path.join(sortie, "rapport_detection.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(R) + "\n")
    print(f"Rapport écrit dans {sortie}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
