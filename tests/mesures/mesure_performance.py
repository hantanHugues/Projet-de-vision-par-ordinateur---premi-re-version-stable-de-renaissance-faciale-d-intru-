"""
Mesure de performance du pipeline de BioGate, avec les VRAIES fonctions du serveur (module api).

Quatre mesures, sur un ordinateur sans autre charge, CPU seul :
  1. Étapes isolées : YOLO à 320 et à 640 pixels (alternés image par image pour annuler la dérive), NMS maison, Haar, second avis
     MediaPipe, CLAHE, FaceNet512 ; appariement avec les vecteurs en mémoire (cache RAM) comparé à une relecture de SQLite à chaque
     image, pour 16 à 16 000 vecteurs.
  2. Régimes de fonctionnement (api._run_pipeline_and_annotate) : première image d'un inconnu, première image d'un résident, régime
     stable (personne déjà identifiée, images à 5 par seconde, revérification toutes les 0,8 s), débit maximal sans pause.
  3. Temps de décision : de la première image d'une personne jusqu'à « accès accordé » (résident, second facteur désactivé) ou
     jusqu'à « intrus provisoire » (inconnu), images à 5 par seconde.
  4. Endurance : débit maximal pendant `duree_endurance` secondes, avec l'usage du processeur et de la mémoire du processus
     (psutil), pour repérer une dégradation ou une fuite.

Précautions : les premières images (échauffement) sont écartées ; médiane, 90e et 95e centiles sont donnés en plus de la moyenne ;
base SQLite et dossier de photos TEMPORAIRES (la vraie base n'est ni lue ni modifiée) ; aucune alerte envoyée ; les trois photos
sont celles de tests/photos_test_apprentissage_continu (images libres de droits, licences indiquées dans le mémoire).

Limite à retenir : la scène est une photo fixe collée sur fond noir (reproductible), pas une vidéo : les coûts d'une scène réelle
(plusieurs personnes, mouvement) ne sont pas mesurés ici.

Usage :
    .venv-deepface\\Scripts\\python.exe tests\\mesures\\mesure_performance.py <dossier_sortie> [--rapide]

Sorties : performance_etapes.csv, performance_regimes.csv, performance_endurance.csv, performance.png, rapport_performance.md.
"""

import csv
import os
import statistics
import sys
import tempfile
import time

import cv2
import numpy as np

RACINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.chdir(RACINE)

import config  # noqa: E402
from mesure_far_frr import materiel  # noqa: E402

api = None  # le serveur est chargé par preparer() : l'importer lance YOLO et FaceNet


def preparer():
    """Charge le vrai serveur sur une base et un dossier de photos TEMPORAIRES, sans alertes ni second facteur."""
    global api
    config.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="biogate-perf-"), "visages.db")
    config.ALERT_TELEGRAM_ENABLED = False
    config.ALERT_EMAIL_ENABLED = False
    config.MFA_REQUIRED = False
    import api as serveur  # après la redirection de config.DB_PATH
    api = serveur
    api.SNAPSHOT_DIR = tempfile.mkdtemp(prefix="biogate-perf-snap-")


PHOTOS = os.path.join(RACINE, "tests", "photos_test_apprentissage_continu")
ECHAUFFEMENT = 5


# ----------------------------------------------------------------------------- outils

def scene(nom, max_w=380, max_h=450, x=130, y=15):
    """Photo collée sur un fond noir 640x480, comme dans les tests du Face Gate."""
    img = cv2.imread(os.path.join(PHOTOS, nom))
    assert img is not None, f"photo introuvable : {nom}"
    h, w = img.shape[:2]
    k = min(max_w / w, max_h / h)
    img = cv2.resize(img, (int(w * k), int(h * k)))
    toile = np.zeros((480, 640, 3), np.uint8)
    toile[y:y + img.shape[0], x:x + img.shape[1]] = img
    return toile


def stats(valeurs):
    v = np.asarray(valeurs, dtype=float)
    return {"n": len(v), "moyenne": float(v.mean()), "ecart_type": float(v.std()), "mediane": float(np.median(v)),
            "p90": float(np.percentile(v, 90)), "p95": float(np.percentile(v, 95)), "min": float(v.min()), "max": float(v.max())}


def chrono(fn, *args):
    t0 = time.perf_counter()
    r = fn(*args)
    return (time.perf_counter() - t0) * 1000.0, r


def fr(x, d=1):
    return f"{x:.{d}f}".replace(".", ",")


# ----------------------------------------------------------------------------- préparation

def enroler(nom_photo):
    """Enrôle la photo comme résident « Sujet_test » dans la base TEMPORAIRE (même chaîne que l'enrôlement réel)."""
    fr_ = api.face_recognizer
    image = scene(nom_photo)
    det = api.yolo.detect_humans(image)
    assert det, "YOLO ne trouve aucune personne dans la scène d'enrôlement"
    x1, y1, x2, y2 = (int(v) for v in det[0]["box"])
    silhouette = image[y1:y2, x1:x2]
    gris = cv2.equalizeHist(cv2.cvtColor(silhouette, cv2.COLOR_BGR2GRAY))
    visages = fr_.face_cascade.detectMultiScale(gris, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    assert len(visages), "Haar ne trouve aucun visage dans la scène d'enrôlement"
    x, y, w, h = (int(v) for v in visages[0])
    sig = fr_._extract_face_signature(silhouette[y:y + h, x:x + w])
    fr_.db.add_embedding("Sujet_test", sig, role="VIP")
    fr_.reload_cache()
    return image, (x1, y1, x2, y2), (x, y, w, h)


# ----------------------------------------------------------------------------- 1. étapes

def mesurer_etapes(frame_vip, n):
    yolo, fr_ = api.yolo, api.face_recognizer
    lignes = []

    def ajouter(nom, valeurs, remarque=""):
        s = stats(valeurs)
        lignes.append({"etape": nom, **s, "remarque": remarque})

    # YOLO 320 contre 640, alternés image par image
    t = {320: [], 640: []}
    taille0 = config.YOLO_IMAGE_SIZE
    for i in range(n + ECHAUFFEMENT):
        for taille in (320, 640):
            config.YOLO_IMAGE_SIZE = taille
            dt, det = chrono(yolo.detect_humans, frame_vip)
            if i >= ECHAUFFEMENT:
                t[taille].append(dt)
    config.YOLO_IMAGE_SIZE = taille0
    ajouter("Détection des personnes, YOLOv8n à 320 px (réglage de BioGate)", t[320])
    ajouter("Détection des personnes, YOLOv8n à 640 px", t[640], "pour comparaison")

    config.YOLO_IMAGE_SIZE = 320
    det = yolo.detect_humans(frame_vip)
    x1, y1, x2, y2 = (int(v) for v in det[0]["box"])
    silhouette = frame_vip[y1:y2, x1:x2]

    # NMS maison, sur six boîtes qui se recouvrent
    boites = [{"box": [100 + 5 * i, 50, 300 + 5 * i, 400], "confidence": 0.9 - 0.05 * i} for i in range(6)]
    reps = 5000
    t0 = time.perf_counter()
    for _ in range(reps):
        yolo._nms(boites, 0.30)
    ajouter("NMS maison (6 boîtes qui se recouvrent)", [(time.perf_counter() - t0) / reps * 1000.0], "moyenne sur 5 000 appels")

    # Face Gate
    th, tm, tc, tf = [], [], [], []
    visage = None
    for i in range(n + ECHAUFFEMENT):
        def haar():
            g = cv2.equalizeHist(cv2.cvtColor(silhouette, cv2.COLOR_BGR2GRAY))
            return fr_.face_cascade.detectMultiScale(g, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        d1, faces = chrono(haar)
        rect = tuple(int(v) for v in faces[0])
        d2, _ = chrono(fr_._confirm_face, silhouette, rect)
        x, y, w, h = rect
        roi = silhouette[y:y + h, x:x + w]
        d3, _ = chrono(fr_._apply_clahe_bgr, roi)
        d4, _ = chrono(fr_._extract_face_signature, roi)
        if i >= ECHAUFFEMENT:
            th.append(d1); tm.append(d2); tc.append(d3); tf.append(d4)
        visage = roi
    ajouter("Face Gate : détecteur de Haar (silhouette)", th)
    ajouter("Face Gate : second avis MediaPipe", tm)
    ajouter("Correction de contraste CLAHE seule", tc)
    ajouter("Embedding FaceNet512 (CLAHE incluse)", tf, "l'étape la plus coûteuse, lancée seulement si un visage de face est confirmé")

    # Appariement : cache RAM contre relecture de SQLite, selon le nombre de vecteurs
    sig = fr_._extract_face_signature(visage)
    cache0 = fr_._embeddings_cache
    rng = np.random.default_rng(0)
    import sqlite3
    for total in (16, 160, 1600, 16000):
        profils = max(1, total // 8)
        vecteurs = {f"P{i:05d}": [v for v in rng.normal(size=(8, 512)).astype(np.float32)] for i in range(profils)}
        fr_._embeddings_cache = vecteurs
        reps_ram = 200 if total <= 1600 else 20
        ram = [chrono(fr_._find_in_memory, sig, "perf")[0] for _ in range(reps_ram)]
        ajouter(f"Appariement, cache en mémoire, {total} vecteurs", ram[ECHAUFFEMENT:] if len(ram) > ECHAUFFEMENT else ram)
        # même base dans une base SQLite temporaire, relue à chaque image
        chemin = os.path.join(tempfile.mkdtemp(prefix="biogate-perf-db-"), "v.db")
        base = api.DatabaseManager(db_path=chemin)
        ids = {nom: base.add_profile_if_not_exists(nom, role="VIP") for nom in vecteurs}
        conn = sqlite3.connect(chemin)
        conn.executemany("INSERT INTO embeddings (profile_id, vector_json) VALUES (?, ?)",
                         [(ids[nom], "[" + ",".join(repr(float(x)) for x in v) + "]") for nom, liste in vecteurs.items() for v in liste])
        conn.commit()
        conn.close()
        reps_db = 10 if total <= 1600 else 3
        db = [chrono(base.get_all_embeddings)[0] for _ in range(reps_db)]
        ajouter(f"Relecture de SQLite à chaque image, {total} vecteurs", db, "ce que le cache en mémoire évite")
    fr_._embeddings_cache = cache0
    return lignes


# ----------------------------------------------------------------------------- 2 et 3. régimes

def appeler(frame, cam):
    return chrono(api._run_pipeline_and_annotate, frame, cam)


def etat(annotations):
    return annotations[0][7] if annotations else "AUCUNE_DETECTION"


def mesurer_regimes(frame_vip, frame_inconnu, n, duree_stable, duree_max):
    lignes, decision = [], []

    def ajouter(nom, valeurs, remarque=""):
        s = stats(valeurs)
        lignes.append({"regime": nom, **s, "images_par_seconde": 1000.0 / s["moyenne"], "remarque": remarque})

    # première image, à froid (nouvelle caméra donc nouveau suivi à chaque essai)
    for nom, frame, remarque in (("Première image d'un inconnu (identification)", frame_inconnu, "YOLO + suivi + Haar + MediaPipe + FaceNet"),
                                 ("Première image d'un résident (identification)", frame_vip, "même chaîne, appariement réussi")):
        vals = []
        for i in range(n + 2):
            dt, ann = appeler(frame, f"perf_{nom[:6]}_{i}_{time.time_ns()}")
            if i >= 2:
                vals.append(dt)
        ajouter(nom, vals, remarque)

    # régime stable : personne déjà identifiée, images à 5 par seconde
    cam = f"perf_stable_{time.time_ns()}"
    for _ in range(60):
        _, ann = appeler(frame_vip, cam)
        if etat(ann) == "GRANTED":
            break
        time.sleep(0.2)
    vals = []
    fin = time.time() + duree_stable
    while time.time() < fin:
        debut = time.time()
        dt, ann = appeler(frame_vip, cam)
        vals.append(dt)
        time.sleep(max(0.0, 0.2 - (time.time() - debut)))
    ajouter("Régime stable, résident identifié, images à 5 par seconde", vals,
            f"état {etat(ann)} ; revérification toutes les {fr(config.FACE_RECHECK_INTERVAL)} s ; cadence imposée de 5 images par seconde")

    # débit maximal, sans pause
    vals = []
    fin = time.time() + duree_max
    while time.time() < fin:
        dt, ann = appeler(frame_vip, cam)
        vals.append(dt)
    ajouter("Débit maximal, résident identifié, sans pause", vals, "images par seconde = débit d'analyse du serveur")

    # temps de décision, images à 5 par seconde
    for nom, frame, cible in (("Résident : de la première image à « accès accordé »", frame_vip, ("GRANTED",)),
                              ("Inconnu : de la première image à « intrus provisoire »", frame_inconnu, ("INTRUDER_PENDING", "INTRUDER_CONFIRMED"))):
        vals = []
        for i in range(max(8, n // 2)):
            cam = f"perf_dec_{nom[:4]}_{i}_{time.time_ns()}"
            t0 = time.perf_counter()
            while True:
                debut = time.time()
                _, ann = appeler(frame, cam)
                ecoule = time.perf_counter() - t0
                if etat(ann) in cible or ecoule > 15:
                    break
                time.sleep(max(0.0, 0.2 - (time.time() - debut)))
            vals.append(ecoule * 1000.0 if etat(ann) in cible else float("nan"))
        valides = [v for v in vals if not np.isnan(v)]
        decision.append({"decision": nom, "essais": len(vals), "atteints": len(valides), **(stats(valides) if valides else {})})
    return lignes, decision


# ----------------------------------------------------------------------------- 4. endurance

def endurance(frame_vip, duree):
    import psutil
    proc = psutil.Process()
    cam = f"perf_endurance_{time.time_ns()}"
    for _ in range(60):
        _, ann = appeler(frame_vip, cam)
        if etat(ann) == "GRANTED":
            break
        time.sleep(0.2)
    proc.cpu_percent(None)
    coeurs = psutil.cpu_count(logical=True)
    serie, appels, t_fenetre = [], 0, time.time()
    debut = time.time()
    rss0 = proc.memory_info().rss / 1e6
    while time.time() - debut < duree:
        appeler(frame_vip, cam)
        appels += 1
        if time.time() - t_fenetre >= 5.0:
            ecoule = time.time() - t_fenetre
            cpu = proc.cpu_percent(None)   # un seul appel par fenêtre : il mesure depuis l'appel précédent
            serie.append({"t_s": time.time() - debut, "images_par_seconde": appels / ecoule,
                          "cpu_processus_pct_d_un_coeur": cpu,
                          "cpu_machine_pct": cpu / coeurs,
                          "memoire_mo": proc.memory_info().rss / 1e6})
            appels, t_fenetre = 0, time.time()
    return serie, rss0, coeurs


# ----------------------------------------------------------------------------- sortie

def figure(etapes, serie, chemin):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    choix = [("YOLOv8n 320 px", "Détection des personnes, YOLOv8n à 320 px"), ("YOLOv8n 640 px", "Détection des personnes, YOLOv8n à 640 px"),
             ("Haar", "Face Gate : détecteur de Haar"), ("MediaPipe", "Face Gate : second avis"),
             ("FaceNet512 + CLAHE", "Embedding FaceNet512"), ("Appariement (RAM, 1 600)", "Appariement, cache en mémoire, 1600 vecteurs"),
             ("SQLite relu (1 600)", "Relecture de SQLite à chaque image, 1600 vecteurs")]
    noms, med, p95 = [], [], []
    for court, debut in choix:
        for e in etapes:
            if e["etape"].startswith(debut):
                noms.append(court); med.append(e["mediane"]); p95.append(e["p95"])
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.3))
    y = np.arange(len(noms))[::-1]
    ax[0].barh(y, med, color="tab:blue", label="médiane")
    ax[0].plot(p95, y, "k|", markersize=12, label="95e centile")
    ax[0].set_yticks(y)
    ax[0].set_yticklabels(noms, fontsize=8)
    ax[0].set_xscale("log")
    ax[0].set_xlabel("ms par appel (échelle logarithmique)")
    ax[0].legend(fontsize=8)
    ax[0].set_title("Coût de chaque étape (CPU seul)", fontsize=10)
    t = [s["t_s"] for s in serie]
    ax[1].plot(t, [s["images_par_seconde"] for s in serie], "tab:blue", label="images analysées par seconde")
    ax[1].set_xlabel("temps (s)")
    ax[1].set_ylabel("images par seconde", color="tab:blue")
    ax2 = ax[1].twinx()
    ax2.plot(t, [s["memoire_mo"] for s in serie], "tab:red", label="mémoire du processus")
    ax2.set_ylabel("mémoire du processus (Mo)", color="tab:red")
    ax[1].set_ylim(0, max(s["images_par_seconde"] for s in serie) * 1.2)
    ax2.set_ylim(0, max(s["memoire_mo"] for s in serie) * 1.2)
    ax[1].set_title("Endurance, débit maximal (axes à partir de zéro)", fontsize=10)
    fig.tight_layout()
    fig.savefig(chemin, dpi=130)
    plt.close(fig)


def ecrire_csv(chemin, lignes):
    cles = list(dict.fromkeys(k for l in lignes for k in l))
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cles)
        w.writeheader()
        for l in lignes:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in l.items()})


def synthese(etapes, regimes, decision, serie):
    """Phrases construites à partir des mesures (rien n'est écrit à l'avance)."""
    def e(debut):
        return next(x for x in etapes if x["etape"].startswith(debut))

    def r(debut):
        return next(x for x in regimes if x["regime"].startswith(debut))

    y320, y640 = e("Détection des personnes, YOLOv8n à 320"), e("Détection des personnes, YOLOv8n à 640")
    fn, ram, sql = e("Embedding FaceNet512"), e("Appariement, cache en mémoire, 1600 vecteurs"), e("Relecture de SQLite à chaque image, 1600 vecteurs")
    ident, stable, maxi = r("Première image d'un inconnu"), r("Régime stable"), r("Débit maximal")
    dec = decision[0]
    lignes = [
        f"- **Identification d'une personne** (première image) : {fr(ident['mediane'], 0)} ms (médiane), soit environ {fr(1000 / ident['mediane'], 1)} image par seconde ; "
        f"FaceNet512 en représente {fr(100 * fn['mediane'] / ident['mediane'], 0)} %.",
        f"- **Régime stable** (personne déjà identifiée) : médiane de {fr(stable['mediane'], 0)} ms par image, 95e centile de {fr(stable['p95'], 0)} ms (les revérifications), "
        f"et un débit d'analyse maximal de {fr(maxi['images_par_seconde'], 1)} images par seconde.",
        f"- **Réglage de YOLO à 320 pixels** : {fr(y320['mediane'], 0)} ms contre {fr(y640['mediane'], 0)} ms à 640 pixels, soit {fr(y640['mediane'] / y320['mediane'], 1)} fois moins.",
        f"- **Cache en mémoire** : à 1 600 vecteurs, {fr(ram['mediane'], 1)} ms contre {fr(sql['mediane'], 0)} ms pour relire SQLite à chaque image, soit {fr(sql['mediane'] / ram['mediane'], 0)} fois moins.",
    ]
    if dec.get("atteints"):
        lignes.append(f"- **Décision pour un résident** : {fr(dec['mediane'] / 1000, 2)} s de la première image à « accès accordé » (médiane).")
    return lignes


def rapport(etapes, regimes, decision, serie, rss0, coeurs, params, duree):
    def ligne_etape(e):
        return f"| {e['etape']} | {fr(e['mediane'], 2)} | {fr(e['p95'], 2)} | {fr(e['moyenne'], 2)} ± {fr(e['ecart_type'], 2)} | {e['n']} | {e.get('remarque', '')} |"

    moitie = len(serie) // 2
    premier = np.mean([s["images_par_seconde"] for s in serie[:max(1, len(serie) // 5)]])
    dernier = np.mean([s["images_par_seconde"] for s in serie[-max(1, len(serie) // 5):]])
    mem_fin = serie[-1]["memoire_mo"]
    mem_max = max(s["memoire_mo"] for s in serie)
    cpu = np.mean([s["cpu_machine_pct"] for s in serie])
    cpu_c = np.mean([s["cpu_processus_pct_d_un_coeur"] for s in serie])
    T = [
        "# Performance du pipeline de BioGate",
        "",
        f"*Généré par `tests/mesures/mesure_performance.py` le {time.strftime('%d/%m/%Y à %H:%M')}.*",
        "",
        "## Protocole",
        "",
        "- Les **vraies fonctions du serveur** sont appelées (`api._run_pipeline_and_annotate`, `YoloDetector`, `FaceRecognizer`), sur CPU seul, sans autre charge (serveur et tableau de bord arrêtés). "
        "Base SQLite et dossier de photos **temporaires** : la vraie base n'est ni lue ni modifiée ; aucune alerte n'est envoyée ; second facteur désactivé.",
        "- **Scène** : une photo (images libres de droits des tests d'apprentissage) collée sur un fond noir de 640 × 480, donc reproductible. Un résident est enrôlé avec la photo de 2019 ; "
        "la photo de 2024 est reconnue (résident), celle de 2014 ne l'est pas (inconnu).",
        f"- Les {ECHAUFFEMENT} premiers appels de chaque mesure sont écartés (échauffement). Chaque valeur est donnée en **médiane**, **95e centile** et moyenne ± écart-type. "
        "YOLO à 320 et à 640 pixels est mesuré en **alternant** les deux réglages image par image, pour annuler la dérive de la machine.",
        f"- Nombre de mesures par étape : {params['n']} ; régime stable : {params['stable']} s ; débit maximal : {params['maxi']} s ; endurance : {params['endurance']} s.",
        "",
        "## Ce qu'il faut retenir",
        "",
    ] + synthese(etapes, regimes, decision, serie) + [
        "",
        "## 1. Coût de chaque étape",
        "",
        "| Étape | Médiane (ms) | 95e centile (ms) | Moyenne ± écart-type (ms) | Mesures | Remarque |",
        "|---|---|---|---|---|---|",
    ] + [ligne_etape(e) for e in etapes] + [
        "",
        "Lecture : chaque ligne est un coût **par appel**. Le cache en mémoire évite de relire et de décoder les vecteurs dans SQLite à chaque image ; l'écart croît avec le nombre de vecteurs.",
        "",
        "## 2. Régimes de fonctionnement (pipeline complet)",
        "",
        "| Régime | Médiane (ms) | 95e centile (ms) | Moyenne ± écart-type (ms) | Images par seconde (1 / moyenne) | Mesures | Remarque |",
        "|---|---|---|---|---|---|---|",
    ] + [f"| {r['regime']} | {fr(r['mediane'], 0)} | {fr(r['p95'], 0)} | {fr(r['moyenne'], 0)} ± {fr(r['ecart_type'], 0)} | {fr(r['images_par_seconde'], 1)} | {r['n']} | {r['remarque']} |" for r in regimes] + [
        "",
        "## 3. Temps de décision (images à 5 par seconde)",
        "",
        "| Décision | Médiane (s) | 95e centile (s) | Moyenne (s) | Essais réussis |",
        "|---|---|---|---|---|",
    ] + [(f"| {d['decision']} | {fr(d['mediane'] / 1000, 2)} | {fr(d['p95'] / 1000, 2)} | {fr(d['moyenne'] / 1000, 2)} | {d['atteints']} sur {d['essais']} |" if d["atteints"]
          else f"| {d['decision']} | n/a | n/a | n/a | 0 sur {d['essais']} |") for d in decision] + [
        "",
        "Le temps d'un inconnu comprend la fenêtre d'analyse du réglage (`FACE_ANALYSIS_TIME_LIMIT`, 1 s par défaut) : c'est un délai voulu, pas un coût de calcul.",
        "",
        "## 4. Endurance",
        "",
        f"- Débit maximal pendant {params['endurance']} s : **{fr(premier, 2)} images par seconde** au début (premier cinquième) et **{fr(dernier, 2)}** à la fin (dernier cinquième) ; "
        f"par fenêtres de 5 s, de {fr(min(s['images_par_seconde'] for s in serie), 1)} à {fr(max(s['images_par_seconde'] for s in serie), 1)} images par seconde (les revérifications toutes les 0,8 s font varier la fenêtre).",
        f"- Processeur : {fr(cpu_c, 0)} % d'un cœur en moyenne pour le processus, soit **{fr(cpu, 0)} % de la machine** ({coeurs} cœurs logiques).",
        f"- Mémoire du processus : {fr(rss0, 0)} Mo au départ, {fr(mem_fin, 0)} Mo à la fin, maximum {fr(mem_max, 0)} Mo (**variation de {fr(mem_fin - rss0, 0)} Mo**).",
        "",
        "![Performance](performance.png)",
        "",
        "## Limites",
        "",
        "- La scène est une photo fixe sur fond noir : elle isole le coût du pipeline, pas celui d'une scène réelle (plusieurs personnes, mouvement, arrière-plan chargé). "
        "Le débit réel du flux de la caméra BW21 (17 à 30 images par seconde en 640 × 480) a été relevé à part et ne dépend pas de ce pipeline.",
        "- Le débit d'analyse du serveur est volontairement inférieur à celui de la caméra : les images en trop sont abandonnées (file de quatre places) et l'affichage est dessiné à la cadence de la caméra.",
        "- Une seule machine (voir ci-dessous), un seul processeur, CPU seul : aucun résultat sur Raspberry Pi, qui reste une perspective.",
        "- Les mesures dépendent de la charge de la machine au moment de l'essai ; le protocole (échauffement, alternance, médiane et 95e centile) limite ce biais sans le supprimer.",
        "",
        "## Matériel et versions",
        "",
    ] + [f"- {k} : {v}" for k, v in materiel().items()] + [f"- Durée totale de la mesure : {duree:.0f} s"]
    return "\n".join(T) + "\n"


def main(sortie, rapide=False):
    os.makedirs(sortie, exist_ok=True)
    t0 = time.time()
    preparer()
    params = {"n": 12 if rapide else 100, "stable": 10 if rapide else 40, "maxi": 10 if rapide else 60, "endurance": 20 if rapide else 300}
    # la photo de 2019 est enrôlée ; celle de 2024 est reconnue, celle de 2014 ne l'est pas
    enroler("apres1_2019_Chris_Evans_barbe.jpg")
    frame_vip = scene("apres2_2024_Chris_Evans_barbe.jpg")
    frame_inconnu = scene("avant_2014_Chris_Evans_rase.jpg")
    assert api.yolo.detect_humans(frame_vip) and api.yolo.detect_humans(frame_inconnu), "YOLO ne détecte pas la personne de la scène"

    print("1/4 étapes isolées…", flush=True)
    etapes = mesurer_etapes(frame_vip, params["n"])
    print("2-3/4 régimes et temps de décision…", flush=True)
    regimes, decision = mesurer_regimes(frame_vip, frame_inconnu, max(10, params["n"] // 5), params["stable"], params["maxi"])
    print(f"4/4 endurance ({params['endurance']} s)…", flush=True)
    serie, rss0, coeurs = endurance(frame_vip, params["endurance"])
    duree = time.time() - t0

    ecrire_csv(os.path.join(sortie, "performance_etapes.csv"), etapes)
    ecrire_csv(os.path.join(sortie, "performance_regimes.csv"), regimes + [{"regime": d["decision"], **{k: v for k, v in d.items() if k != "decision"}} for d in decision])
    ecrire_csv(os.path.join(sortie, "performance_endurance.csv"), serie)
    figure(etapes, serie, os.path.join(sortie, "performance.png"))
    with open(os.path.join(sortie, "rapport_performance.md"), "w", encoding="utf-8") as f:
        f.write(rapport(etapes, regimes, decision, serie, rss0, coeurs, params, duree))
    print(f"Rapport écrit dans {sortie} ({duree:.0f} s)", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1], rapide="--rapide" in sys.argv)
