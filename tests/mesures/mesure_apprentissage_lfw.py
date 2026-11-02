"""
Mesure de l'apprentissage continu sur de nombreux sujets (base LFW), avec la chaîne de BioGate.

Pour chaque sujet (une personne de LFW ayant au moins `min_images` photos), on simule BioGate :
  - enrôlement : une photo ;
  - apprentissage validé : deux autres photos sont ajoutées au profil, comme le ferait une confirmation par empreinte ;
  - test : toutes les autres photos du sujet, jamais vues du profil.
Pour ne dépendre d'aucun ordre particulier, la répartition (enrôlement, apprentissage, test) est tirée au hasard
`REPETITIONS` fois par sujet ; chaque sujet est résumé par la moyenne de ses répétitions.

Trois expériences :
  1. sujet légitime : part des photos de test reconnues (distance au plus proche vecteur du profil sous le seuil), avant puis après apprentissage ;
  2. inconnus : part des photos de TOUTES les autres personnes du jeu acceptées à tort, avant puis après apprentissage ;
  3. apprentissage erroné, exhaustif : pour chaque couple (sujet, inconnu), une photo de l'inconnu est ajoutée au profil comme si
     l'empreinte l'avait confirmée à tort ; on mesure la part des autres photos de cet inconnu acceptées. C'est le risque que la
     confirmation par un facteur fort (l'empreinte) évite.

Choix de méthode, pour qu'ils tiennent devant un jury :
  - l'unité statistique est le SUJET (les photos d'un même sujet ne sont pas indépendantes) : intervalles de confiance à 95 % par
    rééchantillonnage des sujets (bootstrap), test appairé de Wilcoxon sur les sujets ;
  - les quasi-doublons (photos presque identiques prises à la même occasion) peuvent gonfler l'effet de l'apprentissage : les résultats sont
    redonnés en écartant toute photo de test à moins de QUASI_DOUBLON d'un vecteur du profil ;
  - le seuil de 0,35 n'a pas été réglé sur ce jeu (il vient de la webcam) ; les résultats sont aussi donnés à 0,30 et 0,40, et sans seuil
    (aire sous la courbe ROC, point d'égal taux d'erreur) ;
  - la chaîne de mesure est comparée à FaceRecognizer._extract_face_signature (code de production) sur des images réelles ;
  - graine fixée, sujets tirés au hasard, noms jamais publiés (sujets numérotés).
Deux variantes de la chaîne cherchent l'origine du FRR élevé de mesure_far_frr.py :
  biogate        Haar sur l'image, CLAHE, FaceNet512 (alignement, détecteur opencv) : la chaîne de BioGate ;
  image_entiere  FaceNet512 sur l'image entière, sans Haar ni CLAHE ;
  sans_clahe     comme biogate, sans la correction de contraste.

LFW sert à la recherche : les images ne sont pas recopiées dans le dépôt.

Usage :
    .venv-deepface\\Scripts\\python.exe tests\\mesures\\mesure_apprentissage_lfw.py <lfw-funneled.tgz> <dossier_sortie> [max_sujets] [max_images] [min_images] [graine]

Sorties : sujets.csv, rapport_apprentissage_lfw.md, apprentissage_lfw.png (et un cache d'embeddings par variante).
"""

import csv
import os
import random
import sys
import tarfile
import tempfile
import time

import cv2
import numpy as np

RACINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from mesure_far_frr import distance_cosinus, materiel, signature  # noqa: E402

SEUIL = 0.35
SEUILS = (0.30, 0.35, 0.40)
QUASI_DOUBLON = 0.10
REPETITIONS = 20
BOOTSTRAP = 5000
VARIANTES = [
    ("biogate", "Chaîne de BioGate (Haar, CLAHE, FaceNet512)"),
    ("image_entiere", "Image entière, sans Haar ni CLAHE (FaceNet512 seul)"),
    ("sans_clahe", "Haar sans CLAHE (FaceNet512)"),
]


# ----------------------------------------------------------------------------- données

def choisir(archive, min_images, max_images, max_sujets, graine):
    """Retourne ({sujet: [noms de fichiers de l'archive]}, nombre de personnes éligibles) : sujets tirés au hasard, graine fixe."""
    par_personne = {}
    with tarfile.open(archive, "r:gz") as tar:
        for m in tar:
            if m.isfile() and m.name.endswith(".jpg"):
                par_personne.setdefault(m.name.split("/")[1], []).append(m.name)
    eligibles = sorted(p for p, noms in par_personne.items() if len(noms) >= min_images)
    rng = random.Random(graine)
    choisis = rng.sample(eligibles, min(max_sujets, len(eligibles)))
    return {f"S{i + 1:03d}": sorted(par_personne[p])[:max_images] for i, p in enumerate(sorted(choisis))}, len(eligibles)


def extraire(archive, noms, dossier):
    """Extrait seulement les images voulues. Les chemins viennent de NOTRE liste, jamais de l'archive."""
    os.makedirs(dossier, exist_ok=True)
    voulus = set(noms)
    chemins = {}
    with tarfile.open(archive, "r:gz") as tar:
        for m in tar:
            if m.isfile() and m.name in voulus:
                cible = os.path.join(dossier, m.name.replace("/", "__"))
                if not os.path.exists(cible):
                    with open(cible, "wb") as f:
                        f.write(tar.extractfile(m).read())
                chemins[m.name] = cible
    return chemins


def _represent(deepface, image):
    res = deepface.represent(img_path=image, model_name="Facenet512", enforce_detection=False,
                             align=True, detector_backend="opencv")
    return np.array(res[0]["embedding"], dtype=np.float32)


def _visage_haar(haar, image):
    gris = cv2.equalizeHist(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
    visages = haar.detectMultiScale(gris, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    if len(visages):
        x, y, w, h = visages[0]
        return image[y:y + h, x:x + w], True
    return image, False


def embeddings(variante, chemins, cache_chemin):
    """Calcule (ou relit) l'embedding de chaque image pour une variante de la chaîne."""
    cache = {}
    if os.path.exists(cache_chemin):
        with np.load(cache_chemin, allow_pickle=False) as z:
            cache = {k: z[k] for k in z.files}
    manquantes = [n for n in chemins if n.replace("/", "__") not in cache]
    stats = {"haar": 0, "entiere": 0}
    if manquantes:
        from deepface import DeepFace
        haar = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        t0 = time.time()
        for i, nom in enumerate(manquantes, 1):
            image = cv2.imread(chemins[nom])
            if image is None:
                continue
            if variante == "biogate":
                v = signature(DeepFace, clahe, haar, image, stats)
            elif variante == "sans_clahe":
                visage, trouve = _visage_haar(haar, image)
                stats["haar" if trouve else "entiere"] += 1
                v = _represent(DeepFace, visage)
            else:
                v = _represent(DeepFace, image)
            cache[nom.replace("/", "__")] = v
            if i % 100 == 0 or i == len(manquantes):
                print(f"  [{variante}] {i}/{len(manquantes)} images, {time.time() - t0:.0f} s", flush=True)
        np.savez(cache_chemin, **cache)
    return {n: cache[n.replace("/", "__")] for n in chemins if n.replace("/", "__") in cache}, stats


def verifier_equivalence(chemins, n=6):
    """Écart maximal (distance cosinus) entre la chaîne de mesure et le code de production sur n images : doit être quasi nul."""
    import config
    config.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="biogate-equiv-"), "visages.db")
    from deepface import DeepFace
    from core.face_recognizer import FaceRecognizer
    from core.logger import VisualLogger
    fr = FaceRecognizer(logger=VisualLogger(), trust_mgr=None)
    haar = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    ecarts = []
    for nom in sorted(chemins)[:: max(1, len(chemins) // n)][:n]:
        image = cv2.imread(chemins[nom])
        mesure = signature(DeepFace, clahe, haar, image, {"haar": 0, "entiere": 0})
        gris = cv2.equalizeHist(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
        visages = fr.face_cascade.detectMultiScale(gris, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        visage = image[visages[0][1]:visages[0][1] + visages[0][3], visages[0][0]:visages[0][0] + visages[0][2]] if len(visages) else image
        prod = fr._extract_face_signature(visage)
        ecarts.append(distance_cosinus(mesure, prod))
    return max(ecarts), len(ecarts)


# ----------------------------------------------------------------------------- statistiques

def matrice_distances(vecteurs):
    X = np.stack(vecteurs).astype(np.float64)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    return 1.0 - X @ X.T


def ic95(valeurs, graine):
    """Moyenne et intervalle de confiance à 95 % par rééchantillonnage des sujets (bootstrap)."""
    v = np.asarray([x for x in valeurs if not np.isnan(x)], dtype=float)
    rng = np.random.default_rng(graine)
    moyennes = v[rng.integers(0, len(v), (BOOTSTRAP, len(v)))].mean(axis=1)
    return float(v.mean()), float(np.percentile(moyennes, 2.5)), float(np.percentile(moyennes, 97.5))


def wilcoxon_p(apres, avant):
    from scipy.stats import wilcoxon
    d = np.asarray(apres) - np.asarray(avant)
    if not np.any(d != 0):
        return 1.0
    return float(wilcoxon(d).pvalue)


def experiences(D, idx_sujets, graine):
    rng = np.random.default_rng(graine + 1)
    sids = list(idx_sujets)
    tous = np.concatenate([idx_sujets[s] for s in sids])
    lignes, d0_tous, d2_tous = [], [], []
    for sid in sids:
        I = idx_sujets[sid]
        imposteurs = np.setdiff1d(tous, I)
        acc = {k: [] for k in ("dist0", "dist2", "doublons", "rec0_nd", "rec2_nd")}
        for s in SEUILS:
            for k in ("rec0", "rec2", "far0", "far2"):
                acc[f"{k}_{s}"] = []
        for _ in range(REPETITIONS):
            p = rng.permutation(I)
            e, apprentis, test = p[0], p[1:3], p[3:]
            profil2 = np.concatenate([[e], apprentis])
            d0 = D[e][test]
            d2 = D[np.ix_(profil2, test)].min(axis=0)
            i0 = D[e][imposteurs]
            i2 = D[np.ix_(profil2, imposteurs)].min(axis=0)
            d0_tous.append(d0)
            d2_tous.append(d2)
            for s in SEUILS:
                acc[f"rec0_{s}"].append(np.mean(d0 < s))
                acc[f"rec2_{s}"].append(np.mean(d2 < s))
                acc[f"far0_{s}"].append(np.mean(i0 < s))
                acc[f"far2_{s}"].append(np.mean(i2 < s))
            acc["dist0"].append(d0.mean())
            acc["dist2"].append(d2.mean())
            # photos de test presque identiques à une photo du profil (même occasion) : écartées pour les deux profils
            garde = d2 >= QUASI_DOUBLON
            acc["doublons"].append(1 - garde.mean())
            acc["rec0_nd"].append(np.mean(d0[garde] < SEUIL) if garde.any() else np.nan)
            acc["rec2_nd"].append(np.mean(d2[garde] < SEUIL) if garde.any() else np.nan)
        ligne = {"sujet": sid, "photos_test": len(I) - 3}
        ligne.update({k: float(np.nanmean(v)) for k, v in acc.items()})
        # apprentissage erroné, exhaustif : chaque inconnu T, une de ses photos ajoutée à tort au profil de ce sujet
        a0, ac = [], []
        for t in sids:
            if t == sid:
                continue
            e = rng.choice(I)
            It = idx_sujets[t]
            c = rng.choice(It)
            reste = It[It != c]
            d_e = D[e][reste]
            a0.append(np.mean(d_e < SEUIL))
            ac.append(np.mean(np.minimum(d_e, D[c][reste]) < SEUIL))
        ligne["erreur0"], ligne["erreurc"] = float(np.mean(a0)), float(np.mean(ac))
        ligne["erreur_ge50"] = float(np.mean(np.asarray(ac) >= 0.5))
        lignes.append(ligne)
    return {"lignes": lignes, "d0": np.concatenate(d0_tous), "d2": np.concatenate(d2_tous)}


def qualite_paires(D, labels):
    """Toutes les paires du jeu (aucun échantillonnage) : aire ROC, point d'égal taux d'erreur, FRR et FAR au seuil."""
    iu, ju = np.triu_indices(len(labels), k=1)
    d = D[iu, ju]
    meme = labels[iu] == labels[ju]
    memes, diff = d[meme], np.sort(d[~meme])
    auc = float(1 - np.mean(np.searchsorted(diff, memes, side="left") / len(diff)))
    ts = np.linspace(0, 1, 401)
    far = np.array([np.mean(diff < t) for t in ts])
    frr = np.array([np.mean(memes >= t) for t in ts])
    k = int(np.argmin(np.abs(far - frr)))
    return {"auc": auc, "eer": float((far[k] + frr[k]) / 2), "seuil_eer": float(ts[k]),
            "frr": float(np.mean(memes >= SEUIL)), "far": float(np.mean(diff < SEUIL)),
            "d_meme": float(memes.mean()), "d_diff": float(diff.mean()), "n_memes": int(len(memes)), "n_diff": int(len(diff))}


# ----------------------------------------------------------------------------- sortie

def fr(x):
    return str(x).replace(".", ",")


def nf(x, fmt):
    """Nombre formaté à la française : nf(0.5, '.3f') -> '0,500'."""
    return fr(format(x, fmt))


def pct_ic(m, lo, hi):
    return fr(f"{100 * m:.1f} % [{100 * lo:.1f} ; {100 * hi:.1f}]")


def resume(lignes, cle, graine):
    return ic95([l[cle] for l in lignes], graine)


def figure(res, chemin, graine):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    r = res["biogate"]
    L = r["lignes"]
    fig, ax = plt.subplots(1, 2, figsize=(11.5, 4.2))
    bins = np.linspace(0, 1, 41)
    ax[0].hist(r["d0"], bins=bins, alpha=0.6, label="profil d'origine (1 photo)")
    ax[0].hist(r["d2"], bins=bins, alpha=0.6, label="après 2 validations (3 photos)")
    ax[0].axvline(SEUIL, color="k", ls="--", lw=1)
    ax[0].set_xlabel("distance au plus proche vecteur du profil")
    ax[0].set_ylabel("photos de test")
    ax[0].legend(fontsize=8)
    ax[0].set_title("Sujet légitime (chaîne de BioGate)", fontsize=10)
    series = [("Légitimes\nreconnus", f"rec0_{SEUIL}", f"rec2_{SEUIL}"),
              ("Inconnus\nacceptés", f"far0_{SEUIL}", f"far2_{SEUIL}"),
              ("Inconnu accepté après\napprentissage erroné", "erreur0", "erreurc")]
    for i, (nom, a, b) in enumerate(series):
        for dec, cle, coul in ((-0.2, a, "tab:blue"), (0.2, b, "tab:orange")):
            m, lo, hi = resume(L, cle, graine)
            ax[1].bar(i + dec, 100 * m, 0.4, color=coul, label=("profil d'origine" if dec < 0 else "après apprentissage") if i == 0 else None,
                      yerr=[[100 * (m - lo)], [100 * (hi - m)]], capsize=3)
    ax[1].set_xticks(range(3))
    ax[1].set_xticklabels([s[0] for s in series], fontsize=8)
    ax[1].set_ylabel("% (moyenne des sujets, IC à 95 %)")
    ax[1].legend(fontsize=8)
    ax[1].set_title("Effet de l'apprentissage (seuil 0,35)", fontsize=10)
    fig.tight_layout()
    fig.savefig(chemin, dpi=130)
    plt.close(fig)


def rapport(res, qualite, stats, params, n_eligibles, n_images, equiv, duree, graine):
    L = res["biogate"]["lignes"]
    S = len(L)
    g = graine
    rec0, rec2 = resume(L, f"rec0_{SEUIL}", g), resume(L, f"rec2_{SEUIL}", g)
    dlt = ic95([l[f"rec2_{SEUIL}"] - l[f"rec0_{SEUIL}"] for l in L], g)
    far0, far2 = resume(L, f"far0_{SEUIL}", g), resume(L, f"far2_{SEUIL}", g)
    dfar = ic95([l[f"far2_{SEUIL}"] - l[f"far0_{SEUIL}"] for l in L], g)
    e0, ec = resume(L, "erreur0", g), resume(L, "erreurc", g)
    ge50 = resume(L, "erreur_ge50", g)
    dist0, dist2 = resume(L, "dist0", g), resume(L, "dist2", g)
    nd0, nd2 = resume(L, "rec0_nd", g), resume(L, "rec2_nd", g)
    doublons = resume(L, "doublons", g)
    p_rec = wilcoxon_p([l[f"rec2_{SEUIL}"] for l in L], [l[f"rec0_{SEUIL}"] for l in L])
    p_far = wilcoxon_p([l[f"far2_{SEUIL}"] for l in L], [l[f"far0_{SEUIL}"] for l in L])
    ameliores = sum(1 for l in L if l[f"rec2_{SEUIL}"] > l[f"rec0_{SEUIL}"] + 1e-9)
    inchanges = sum(1 for l in L if abs(l[f"rec2_{SEUIL}"] - l[f"rec0_{SEUIL}"]) <= 1e-9)
    q = qualite["biogate"]

    T = [
        "# Apprentissage continu sur de nombreux sujets (LFW)",
        "",
        f"*Généré par `tests/mesures/mesure_apprentissage_lfw.py` le {time.strftime('%d/%m/%Y à %H:%M')}.*",
        "",
        "## Protocole",
        "",
        f"- Base LFW (Labeled Faces in the Wild, version « funneled »). **{S} sujets** tirés au hasard (graine {params['graine']}) parmi les {n_eligibles} personnes "
        f"qui ont au moins {params['min_images']} photos ; au plus {params['max_images']} photos par sujet, soit **{n_images} images**. Les sujets sont numérotés : aucun nom n'est publié.",
        f"- Pour chaque sujet, comme BioGate : **enrôlement** avec une photo ; **apprentissage validé** : deux autres photos sont ajoutées au profil (ce que ferait une confirmation par empreinte) ; "
        f"**test** sur toutes les autres photos du sujet (jamais vues du profil). La répartition est **tirée au hasard {REPETITIONS} fois par sujet** : aucun résultat ne dépend d'un ordre de photos ; "
        "chaque sujet est résumé par la moyenne de ses répétitions.",
        f"- Une photo est reconnue si la distance cosinus au plus proche vecteur du profil est sous **{fr(SEUIL)}**. Les **fausses acceptations** se comptent sur les photos de **toutes** les autres personnes du jeu (aucun échantillonnage).",
        "- **Unité statistique : le sujet** (les photos d'un même sujet ne sont pas indépendantes). Moyennes sur les sujets, **intervalles de confiance à 95 %** par rééchantillonnage des sujets "
        f"({BOOTSTRAP} tirages), test appairé de **Wilcoxon** sur les sujets.",
        "- **Apprentissage erroné, exhaustif** : pour chaque couple (sujet, inconnu), une photo de l'inconnu est ajoutée au profil du sujet comme si l'empreinte l'avait confirmée à tort ; "
        "on mesure la part des autres photos de cet inconnu acceptées.",
        f"- Chaîne de BioGate appliquée telle quelle (Haar, CLAHE, FaceNet512 avec alignement). Écart maximal avec le code de production (`FaceRecognizer._extract_face_signature`) "
        f"sur {equiv[1]} images : **{equiv[0]:.1e}** en distance cosinus (nul à la précision numérique près).",
        "",
        "## Résultats pour la chaîne de BioGate (seuil 0,35)",
        "",
        "Moyenne des sujets, avec l'intervalle de confiance à 95 % entre crochets.",
        "",
        "| Indicateur | Profil d'origine (1 photo) | Après 2 validations (3 photos) | Différence |",
        "|---|---|---|---|",
        f"| Photos de test du sujet reconnues | {pct_ic(*rec0)} | {pct_ic(*rec2)} | +{fr(f'{100 * dlt[0]:.1f}')} points [{fr(f'{100 * dlt[1]:.1f}')} ; {fr(f'{100 * dlt[2]:.1f}')}], Wilcoxon p = {fr(f'{p_rec:.1e}')} |",
        f"| Distance moyenne des photos de test | {fr(f'{dist0[0]:.3f}')} | {fr(f'{dist2[0]:.3f}')} | {fr(f'{dist2[0] - dist0[0]:+.3f}')} |",
        f"| Photos d'inconnus acceptées à tort (fausses acceptations) | {pct_ic(*far0)} | {pct_ic(*far2)} | +{fr(f'{100 * dfar[0]:.2f}')} points [{fr(f'{100 * dfar[1]:.2f}')} ; {fr(f'{100 * dfar[2]:.2f}')}], Wilcoxon p = {fr(f'{p_far:.1e}')} |",
        f"| **Après un apprentissage erroné** : autres photos de l'inconnu acceptées | {pct_ic(*e0)} | {pct_ic(*ec)} | dans {pct_ic(*ge50)} des cas, plus de la moitié de ses photos sont acceptées |",
        "",
        f"- Effet sur la reconnaissance : **{ameliores} sujets améliorés, {inchanges} inchangés** sur {S} (le minimum sur davantage de vecteurs ne peut que baisser la distance : l'amélioration est attendue, "
        "ce qui est mesuré ici est son **ampleur** et son **coût en fausses acceptations**).",
        f"- Lecture (d'après les chiffres ci-dessus) : l'apprentissage validé relève la reconnaissance de {nf(100 * dlt[0], '.1f')} points ; les fausses acceptations passent de "
        f"{pct_ic(*far0)} à {pct_ic(*far2)} (variation {'significative' if p_far < 0.05 else 'non significative'} au seuil de 5 %). "
        f"Un seul apprentissage erroné fait passer, pour l'inconnu concerné, la part de ses photos acceptées de {pct_ic(*e0)} à {pct_ic(*ec)}, "
        f"contre {pct_ic(*far2)} pour un inconnu quelconque après un apprentissage valide : c'est ce que la confirmation par un facteur fort (l'empreinte) avant tout ajout au profil évite.",
        "",
        "![Effet de l'apprentissage](apprentissage_lfw.png)",
        "",
        "## Sensibilité des résultats",
        "",
        f"- **Quasi-doublons** : en moyenne {pct_ic(*doublons)} des photos de test sont à moins de {fr(QUASI_DOUBLON)} d'une photo du profil (prises à la même occasion). "
        f"En les écartant pour les deux profils, la reconnaissance passe de {pct_ic(*nd0)} à {pct_ic(*nd2)}.",
        "",
        "| Seuil | Reconnues, origine | Reconnues, après | Fausses acceptations, origine | Fausses acceptations, après |",
        "|---|---|---|---|---|",
    ]
    for s in SEUILS:
        T.append(f"| {fr(s)} | {pct_ic(*resume(L, f'rec0_{s}', g))} | {pct_ic(*resume(L, f'rec2_{s}', g))} | "
                 f"{pct_ic(*resume(L, f'far0_{s}', g))} | {pct_ic(*resume(L, f'far2_{s}', g))} |")
    T += [
        "",
        f"- **Sans seuil** (toutes les paires du jeu : {q['n_memes']} paires d'une même personne, {q['n_diff']} de personnes différentes) : "
        f"aire sous la courbe ROC **{nf(q['auc'], '.3f')}**, point d'égal taux d'erreur **{nf(100 * q['eer'], '.1f')} %** au seuil {nf(q['seuil_eer'], '.2f')}.",
        "",
        "## Les trois variantes de la chaîne (mêmes sujets, mêmes photos)",
        "",
        "| Variante | Aire ROC | Égal taux d'erreur (seuil) | FRR / FAR des paires à 0,35 | Distance moyenne : même personne / personnes différentes | Reconnues, origine → après |",
        "|---|---|---|---|---|---|",
    ]
    for cle, titre in VARIANTES:
        if cle not in res:
            continue
        qq = qualite[cle]
        r0, r2 = resume(res[cle]["lignes"], f"rec0_{SEUIL}", g), resume(res[cle]["lignes"], f"rec2_{SEUIL}", g)
        T.append(f"| {titre} | {nf(qq['auc'], '.3f')} | {nf(100 * qq['eer'], '.1f')} % ({nf(qq['seuil_eer'], '.2f')}) | "
                 f"{nf(100 * qq['frr'], '.1f')} % / {nf(100 * qq['far'], '.1f')} % | {nf(qq['d_meme'], '.3f')} / {nf(qq['d_diff'], '.3f')} | "
                 f"{nf(100 * r0[0], '.1f')} % → {nf(100 * r2[0], '.1f')} % |")
    T += [
        "",
        f"Haar a trouvé un visage dans {stats['biogate']['haar']} images sur {stats['biogate']['haar'] + stats['biogate']['entiere']} (chaîne de BioGate).",
        "",
        "## Menaces à la validité et réponses",
        "",
        "| Objection possible | Réponse |",
        "|---|---|",
        f"| « Un seul tirage de photos peut être favorable. » | La répartition enrôlement / apprentissage / test est tirée {REPETITIONS} fois par sujet ; les résultats sont des moyennes. |",
        "| « Les photos d'un même sujet ne sont pas indépendantes. » | L'unité statistique est le sujet : intervalles de confiance et test par rééchantillonnage ou appariement des sujets, jamais des photos. |",
        "| « Des photos presque identiques gonflent l'effet. » | Résultats redonnés en écartant toute photo de test proche d'une photo du profil. |",
        "| « Le seuil a été choisi pour que ça marche. » | Le seuil de 0,35 vient de la webcam, pas de ce jeu ; résultats donnés à 0,30, 0,35 et 0,40, et sans seuil (aire ROC, égal taux d'erreur). |",
        "| « Les sujets ont été choisis. » | Tirage au hasard avec graine fixée parmi toutes les personnes éligibles ; aucun nom publié ; le script reproduit tout. |",
        "| « Votre chaîne de mesure n'est pas celle du produit. » | Comparée au code de production sur des images réelles : écart nul à la précision numérique près. |",
        "| « L'amélioration est automatique : plus de vecteurs, plus de chances. » | Oui, et c'est le comportement de BioGate : la question mesurée est l'ampleur du gain et le coût en fausses acceptations, avec l'apprentissage erroné comme contre-exemple. |",
        "| « La confirmation par empreinte n'est pas parfaite. » | Elle est supposée fiable (empreinte simulée dans le prototype) : la mesure d'apprentissage erroné chiffre ce qui arrive si elle ne l'est pas. |",
        "",
        "## Limites",
        "",
        "- LFW ne date pas les photos : ce sont des photos de presse prises dans des conditions variées (pose, lumière, expression, quelques années d'écart au plus). Elles couvrent la variabilité naturelle d'un visage, "
        "**pas le vieillissement sur dix ans**, ni la pousse d'une barbe : pour cela, l'essai à trois photos datées (Chris Evans, 0,4722 → 0,224) reste la démonstration.",
        "- Les personnes de LFW sont des personnalités très photographiées : le jeu n'est pas représentatif de toute la population (âge, origine, genre), et les taux absolus ne se transposent pas tels quels à une caméra de porte.",
        "- BioGate compare à plusieurs photos enrôlées à la webcam, avec une caméra fixe : son FRR réel n'est pas celui de cette mesure.",
        "- Un seul jeu de sujets (graine fixée). Les répétitions couvrent la répartition des photos, pas le choix des sujets ; l'intervalle de confiance couvre ce dernier.",
        "- L'apprentissage erroné est simulé avec une photo d'inconnu tirée au hasard ; le risque est plus fort pour deux visages qui se ressemblent.",
        "",
        "## Matériel et versions",
        "",
    ] + [f"- {k} : {v}" for k, v in materiel().items()] + [f"- Durée du calcul des embeddings et des expériences : {duree:.0f} s"]
    return "\n".join(T) + "\n"


def main(archive, sortie, max_sujets=100, max_images=10, min_images=8, graine=1):
    os.makedirs(sortie, exist_ok=True)
    t0 = time.time()
    sujets, n_eligibles = choisir(archive, min_images, max_images, max_sujets, graine)
    noms = [n for liste in sujets.values() for n in liste]
    print(f"{len(sujets)} sujets, {len(noms)} images (sur {n_eligibles} personnes éligibles)", flush=True)
    chemins = extraire(archive, noms, os.path.join(sortie, "images_lfw"))

    res, qualite, stats = {}, {}, {}
    for cle, titre in VARIANTES:
        print(f"Variante {cle} : {titre}", flush=True)
        emb, st = embeddings(cle, chemins, os.path.join(sortie, f"embeddings_{cle}.npz"))
        stats[cle] = st
        ordre = [n for n in noms if n in emb]
        idx = {n: i for i, n in enumerate(ordre)}
        D = matrice_distances([emb[n] for n in ordre])
        idx_sujets = {s: np.array([idx[n] for n in liste if n in idx]) for s, liste in sujets.items()}
        idx_sujets = {s: v for s, v in idx_sujets.items() if len(v) >= max(min_images, 5)}
        labels = np.zeros(len(ordre), dtype=int)
        for k, (s, v) in enumerate(idx_sujets.items()):
            labels[v] = k
        res[cle] = experiences(D, idx_sujets, graine)
        qualite[cle] = qualite_paires(D, labels)
        if cle == "biogate":
            print("Vérification d'équivalence avec le code de production…", flush=True)
            equiv = verifier_equivalence(chemins)
            print(f"  écart maximal : {equiv[0]:.2e} sur {equiv[1]} images", flush=True)
    duree = time.time() - t0

    L = res["biogate"]["lignes"]
    with open(os.path.join(sortie, "sujets.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        cols = ["sujet", "photos_test", f"rec0_{SEUIL}", f"rec2_{SEUIL}", "dist0", "dist2",
                f"far0_{SEUIL}", f"far2_{SEUIL}", "erreur0", "erreurc", "erreur_ge50"]
        w.writerow(["sujet", "photos_test", "reconnues_origine", "reconnues_apres_apprentissage", "distance_moy_origine",
                    "distance_moy_apres", "fausses_acceptations_origine", "fausses_acceptations_apres",
                    "inconnu_accepte_origine", "inconnu_accepte_apres_apprentissage_errone", "part_cas_plus_de_50_pour_cent"])
        for l in L:
            w.writerow([l["sujet"]] + [l["photos_test"]] + [f"{l[c]:.4f}" for c in cols[2:]])
    figure(res, os.path.join(sortie, "apprentissage_lfw.png"), graine)
    params = {"graine": graine, "min_images": min_images, "max_images": max_images}
    with open(os.path.join(sortie, "rapport_apprentissage_lfw.md"), "w", encoding="utf-8") as f:
        f.write(rapport(res, qualite, stats, params, n_eligibles, len(noms), equiv, duree, graine))
    m0, m2 = resume(L, f"rec0_{SEUIL}", graine), resume(L, f"rec2_{SEUIL}", graine)
    print(f"Reconnues : {100 * m0[0]:.1f} % -> {100 * m2[0]:.1f} % | rapport écrit dans {sortie}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    a = sys.argv
    main(a[1], a[2], int(a[3]) if len(a) > 3 else 100, int(a[4]) if len(a) > 4 else 10,
         int(a[5]) if len(a) > 5 else 8, int(a[6]) if len(a) > 6 else 1)
