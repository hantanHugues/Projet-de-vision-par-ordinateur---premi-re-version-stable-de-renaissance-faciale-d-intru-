"""
Apprentissage continu face au VIEILLISSEMENT : le protocole de l'essai Chris Evans, répété sur de nombreuses personnes
de sexes et de continents différents, avec des photos libres de droits et DATÉES de Wikimedia Commons.

Pour chaque personne : photo la plus ancienne = enrôlement ; photo intermédiaire = apprentissage validé (comme une confirmation
par empreinte) ; photo la plus récente = test. On mesure la distance (chaîne de BioGate : Haar, CLAHE, FaceNet512, distance cosinus)
au profil d'origine puis au profil enrichi, et on compte les personnes reconnues (distance sous 0,35) avant et après.

RÈGLE DE SÉLECTION, FIXÉE AVANT TOUT RÉSULTAT (aucun choix à la main) :
  - la liste des candidats (candidats_vieillissement.csv) est ordonnée par case (région × sexe), puis par prénom ;
    on garde, dans chaque case, les PAR_CELLULE premiers candidats qui satisfont tous les critères ci-dessous ;
  - photos : licence libre (CC BY, CC BY-SA, CC0, domaine public) ; date de prise de vue présente dans les métadonnées ;
    largeur d'au moins 400 px ; le nom de la personne figure dans le nom du fichier (garantit que c'est le sujet de la photo) ;
    un SEUL visage de face (Haar, comme BioGate), d'au moins 70 px, confirmé par le second avis de MediaPipe ;
  - trois photos : la plus ancienne (E), la plus récente (T) avec au moins ECART_MIN ans d'écart, et une photo (L) strictement
    entre les deux, la plus proche du milieu ; à année égale, le visage le plus grand ;
  - vérification d'identité sans a priori : si une des trois distances entre ces photos dépasse DISTANCE_IDENTITE_MAX (0,90, valeur
    typique de deux personnes différentes), la photo est probablement mal étiquetée et le candidat est écarté.
Le sexe et la région sont ceux des biographies publiques (continent de nationalité) : ils servent uniquement à répartir l'évaluation
(voir les effets démographiques mesurés par le NIST), pas à décrire des individus. Les images ne sont PAS recopiées dans le dépôt :
un fichier liste leurs pages Commons, auteurs et licences, pour pouvoir tout re-télécharger.

Usage :
    .venv-deepface\\Scripts\\python.exe tests\\mesures\\mesure_vieillissement_commons.py <dossier_sortie> [--essai]

Sorties : manifeste_photos.csv, candidats_journal.csv, sujets_vieillissement.csv, rapport_vieillissement.md, vieillissement.png.
"""

import csv
import math
import os
import re
import sys
import tempfile
import time
import unicodedata

import cv2
import numpy as np
import requests

RACINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from mesure_far_frr import distance_cosinus, materiel, signature  # noqa: E402

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "BioGateMemoireResearch/1.0 (https://github.com/hantanHugues; memoire de licence IFRI/UAC, mesure academique)"}
SEUIL = 0.35
PAR_CELLULE = 4
ECART_MIN = 8
LARGEUR = 800
VISAGE_MIN = 70
DISTANCE_IDENTITE_MAX = 0.90
LICENCE = re.compile(r"^(CC[ -]BY|CC0|Public domain|PD)", re.I)
REGIONS = ["Afrique", "Asie", "Europe", "Amérique du Nord", "Amérique du Sud", "Océanie"]


# ----------------------------------------------------------------------------- Commons

def normaliser(texte):
    t = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def nom_dans_fichier(nom, titre):
    n, t = normaliser(nom).split(), normaliser(titre)
    return " ".join(n) in t or (len(n[-1]) >= 4 and n[-1] in t.split())


def annee(valeur):
    m = re.search(r"\b(19[5-9]\d|20[0-2]\d)\b", re.sub(r"<[^>]+>", "", valeur or ""))
    return int(m.group(1)) if m else None


def get(params, essais=8):
    for i in range(essais):
        try:
            r = requests.get(API, params=params, headers=UA, timeout=60)
        except requests.exceptions.ConnectionError:
            time.sleep(5 * (i + 1))  # coupure réseau côté Commons : on réessaie
            continue
        if r.status_code == 429:
            time.sleep(5 * (i + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("Commons : trop de requêtes")


def _sous_categories(titre):
    d = get({"action": "query", "format": "json", "list": "categorymembers", "cmtitle": titre, "cmtype": "subcat", "cmlimit": 60})
    return [m["title"] for m in d.get("query", {}).get("categorymembers", [])]


def lister(nom, profondeur=2, categories_max=30):
    """Fichiers de la catégorie Commons de la personne ET de ses sous-catégories (profondeur 2, 30 catégories au plus)."""
    a_visiter, vues, fichiers = [(f"Category:{nom}", 0)], set(), []
    while a_visiter and len(vues) < categories_max:
        titre, niveau = a_visiter.pop(0)
        if titre in vues:
            continue
        vues.add(titre)
        fichiers += _fichiers_categorie(titre)
        if niveau < profondeur:
            a_visiter += [(t, niveau + 1) for t in _sous_categories(titre)]
            time.sleep(0.2)
    uniques = {f["titre"]: f for f in fichiers}
    return list(uniques.values())


def _fichiers_categorie(titre, pages_max=6):
    """Fichiers d'une catégorie Commons, avec date, licence, auteur et miniature de 800 px."""
    params = {"action": "query", "format": "json", "generator": "categorymembers", "gcmtitle": titre, "gcmtype": "file",
              "gcmlimit": 50, "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": LARGEUR,
              "iiextmetadatafilter": "DateTimeOriginal|LicenseShortName|Artist"}
    fichiers = []
    for _ in range(pages_max):
        d = get(params)
        for pg in d.get("query", {}).get("pages", {}).values():
            ii = (pg.get("imageinfo") or [{}])[0]
            em = ii.get("extmetadata", {})
            val = lambda k: re.sub(r"<[^>]+>", "", em.get(k, {}).get("value", "")).strip()
            fichiers.append({"titre": pg["title"], "largeur": ii.get("width", 0), "mime": ii.get("mime", ""), "miniature": ii.get("thumburl", ""),
                             "page": ii.get("descriptionurl", ""), "licence": val("LicenseShortName"), "auteur": val("Artist")[:80],
                             "annee": annee(em.get("DateTimeOriginal", {}).get("value", ""))})
        if "continue" not in d:
            break
        params.update(d["continue"])
        time.sleep(0.2)
    return fichiers


def echantillon(fichiers, nom, par_annee=3, maxi=36):
    """Photos admissibles (licence, date, taille, nom dans le fichier), au plus `par_annee` par année, étalées dans le temps."""
    ok = [f for f in fichiers if f["annee"] and f["mime"] == "image/jpeg" and f["largeur"] >= 400 and f["miniature"]
          and LICENCE.match(f["licence"]) and nom_dans_fichier(nom, f["titre"])]
    ok.sort(key=lambda f: (f["annee"], f["titre"]))
    garde, compte = [], {}
    for f in ok:
        if compte.get(f["annee"], 0) < par_annee:
            garde.append(f)
            compte[f["annee"]] = compte.get(f["annee"], 0) + 1
    if len(garde) > maxi:
        pas = len(garde) / maxi
        garde = [garde[int(i * pas)] for i in range(maxi)]
    return garde, len(ok)


def telecharger(f, dossier):
    chemin = os.path.join(dossier, re.sub(r"[^A-Za-z0-9]+", "_", f["titre"])[:90] + ".jpg")
    if not os.path.exists(chemin):
        for i in range(4):
            r = requests.get(f["miniature"], headers=UA, timeout=60)
            if r.status_code == 429:
                time.sleep(5 * (i + 1))
                continue
            r.raise_for_status()
            with open(chemin, "wb") as fh:
                fh.write(r.content)
            break
        else:
            return None
        time.sleep(0.2)
    return chemin


# ----------------------------------------------------------------------------- visages

def visage_unique(fr, image):
    """(rectangle, motif) : rectangle du seul visage de face (Haar de BioGate, au moins VISAGE_MIN px, confirmé par MediaPipe),
    sinon None avec le motif du rejet : « aucun », « plusieurs » ou « non_confirme »."""
    gris = cv2.equalizeHist(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
    visages = fr.face_cascade.detectMultiScale(gris, scaleFactor=1.1, minNeighbors=5, minSize=(VISAGE_MIN, VISAGE_MIN))
    if len(visages) == 0:
        return None, "aucun"
    if len(visages) > 1:
        return None, "plusieurs"
    if not fr._confirm_face(image, visages[0]):
        return None, "non_confirme"
    return tuple(int(v) for v in visages[0]), "ok"


def choisir_trois(valides):
    """valides : [(fichier, taille_du_visage, chemin)] -> (E, L, T) ou une raison d'exclusion."""
    tri = sorted(valides, key=lambda v: (v[0]["annee"], -v[1]))
    a_min, a_max = tri[0][0]["annee"], tri[-1][0]["annee"]
    if a_max - a_min < ECART_MIN:
        return None, f"écart de {a_max - a_min} ans entre les photos valides (minimum {ECART_MIN})"
    e = next(v for v in tri if v[0]["annee"] == a_min)
    t = next(v for v in sorted(tri, key=lambda v: (-v[0]["annee"], -v[1])) if v[0]["annee"] == a_max)
    milieu = (a_min + a_max) / 2
    inter = [v for v in tri if a_min < v[0]["annee"] < a_max]
    if not inter:
        return None, "aucune photo valide strictement entre la plus ancienne et la plus récente"
    l = min(inter, key=lambda v: (abs(v[0]["annee"] - milieu), -v[1]))
    return (e, l, t), ""


# ----------------------------------------------------------------------------- analyse

def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n)


def ic_moyenne(valeurs, graine=1, rep=5000):
    v = np.asarray(valeurs, float)
    rng = np.random.default_rng(graine)
    m = v[rng.integers(0, len(v), (rep, len(v)))].mean(axis=1)
    return float(v.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def analyser(S):
    for s in S:
        e, l, t = s["emb"]
        s["d_EL"], s["d_ET"], s["d_LT"] = distance_cosinus(e, l), distance_cosinus(e, t), distance_cosinus(l, t)
        s["avant"], s["apres"] = s["d_ET"], min(s["d_ET"], s["d_LT"])
        s["ecart"] = s["annees"][2] - s["annees"][0]
    n = len(S)
    imp_a = imp_b = imp_n = 0
    for i, si in enumerate(S):
        ei, li = si["emb"][0], si["emb"][1]
        for j, sj in enumerate(S):
            if i != j:
                d_av = distance_cosinus(sj["emb"][2], ei)
                d_ap = min(d_av, distance_cosinus(sj["emb"][2], li))
                imp_a += d_av < SEUIL
                imp_b += d_ap < SEUIL
                imp_n += 1
    return {"n": n, "imp_avant": imp_a, "imp_apres": imp_b, "imp_total": imp_n}


def groupe(S, cle, valeurs):
    lignes = []
    for v in valeurs:
        G = [s for s in S if s[cle] == v]
        if not G:
            continue
        ka, kb = sum(s["avant"] < SEUIL for s in G), sum(s["apres"] < SEUIL for s in G)
        lignes.append({"groupe": v, "n": len(G), "avant": ka, "apres": kb, "ic_avant": wilson(ka, len(G)), "ic_apres": wilson(kb, len(G)),
                       "d_avant": float(np.mean([s["avant"] for s in G])), "d_apres": float(np.mean([s["apres"] for s in G])),
                       "ecart": float(np.mean([s["ecart"] for s in G]))})
    return lignes


def fr(x, d=1):
    return f"{x:.{d}f}".replace(".", ",")


def detection(journal, cle, valeurs):
    """Tableau : motifs de rejet et validation par le filtre de visage, par groupe, sur les photos testées des candidats examinés."""
    T = [f"| {'Région' if cle == 'region' else 'Sexe'} | Photos testées | Aucun visage de face | Plusieurs visages | Un visage non confirmé par MediaPipe | **Un visage de face validé** |", "|---|---|---|---|---|---|"]
    for v in valeurs:
        J = [j for j in journal if j[cle] == v]
        tot = {k: sum(j.get(k, 0) for j in J) for k in ("aucun", "plusieurs", "non_confirme", "ok")}
        n = sum(tot.values())
        if n == 0:
            continue
        lo, hi = wilson(tot["ok"], n)
        T.append(f"| {v} | {n} | {fr(100 * tot['aucun'] / n)} % | {fr(100 * tot['plusieurs'] / n)} % | {fr(100 * tot['non_confirme'] / n)} % | "
                 f"**{fr(100 * tot['ok'] / n)} %** [{fr(100 * lo)} ; {fr(100 * hi)}] |")
    return T


def pct(k, n):
    lo, hi = wilson(k, n)
    return f"{k} sur {n} ({fr(100 * k / n)} % [{fr(100 * lo)} ; {fr(100 * hi)}])"


# ----------------------------------------------------------------------------- sortie

def figure(S, chemin):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    couleurs = dict(zip(REGIONS, plt.cm.tab10.colors))
    fig, ax = plt.subplots(1, 2, figsize=(12.5, 4.6))
    for s in S:
        c, m = couleurs[s["region"]], ("o" if s["sexe"] == "F" else "s")
        ax[0].plot([s["ecart"], s["ecart"]], [s["avant"], s["apres"]], color=c, alpha=0.5, lw=1)
        ax[0].scatter(s["ecart"], s["avant"], facecolors="none", edgecolors=c, marker=m, s=34)
        ax[0].scatter(s["ecart"], s["apres"], color=c, marker=m, s=34)
    ax[0].axhline(SEUIL, color="k", ls="--", lw=1)
    ax[0].set_xlabel("années entre la photo d'enrôlement et la photo de test")
    ax[0].set_ylabel("distance au profil")
    ax[0].set_title("Chaque personne : avant (creux) puis après apprentissage (plein)", fontsize=9)
    for r in REGIONS:
        ax[0].scatter([], [], color=couleurs[r], label=r)
    ax[0].scatter([], [], facecolors="none", edgecolors="gray", marker="o", label="femme")
    ax[0].scatter([], [], facecolors="none", edgecolors="gray", marker="s", label="homme")
    ax[0].legend(fontsize=7, ncol=2)
    lignes = groupe(S, "region", REGIONS)
    x = np.arange(len(lignes))
    ax[1].bar(x - 0.2, [100 * l["avant"] / l["n"] for l in lignes], 0.4, label="profil d'origine")
    ax[1].bar(x + 0.2, [100 * l["apres"] / l["n"] for l in lignes], 0.4, label="après apprentissage")
    ax[1].set_xticks(x)
    ax[1].set_xticklabels([f"{l['groupe']}\n(n = {l['n']})" for l in lignes], fontsize=7)
    ax[1].set_ylabel("% de personnes reconnues (seuil 0,35)")
    ax[1].legend(fontsize=8)
    ax[1].set_title("Reconnaissance par région", fontsize=9)
    fig.tight_layout()
    fig.savefig(chemin, dpi=130)
    plt.close(fig)


def rapport(S, A, journal, duree, essai):
    n = A["n"]
    ka, kb = sum(s["avant"] < SEUIL for s in S), sum(s["apres"] < SEUIL for s in S)
    b = sum(1 for s in S if s["avant"] >= SEUIL and s["apres"] < SEUIL)
    gain = ic_moyenne([s["avant"] - s["apres"] for s in S])
    d_av, d_ap = ic_moyenne([s["avant"] for s in S]), ic_moyenne([s["apres"] for s in S])
    from scipy.stats import spearmanr
    rho, p_rho = spearmanr([s["ecart"] for s in S], [s["avant"] for s in S])
    pente = float(np.polyfit([s["ecart"] for s in S], [s["avant"] for s in S], 1)[0])
    raisons = {}
    for j in journal:
        if j["statut"] != "retenu":
            raisons[j["statut"]] = raisons.get(j["statut"], 0) + 1

    def tab(lignes, titre):
        T = [f"| {titre} | Personnes | Reconnues, profil d'origine | Reconnues, après apprentissage | Distance moyenne avant → après | Écart moyen (années) |", "|---|---|---|---|---|---|"]
        for l in lignes:
            T.append(f"| {l['groupe']} | {l['n']} | {pct(l['avant'], l['n'])} | {pct(l['apres'], l['n'])} | {fr(l['d_avant'], 3)} → {fr(l['d_apres'], 3)} | {fr(l['ecart'])} |")
        return T

    R = [
        "# Apprentissage continu face au vieillissement, sur des personnes de tous les continents",
        "",
        f"*Généré par `tests/mesures/mesure_vieillissement_commons.py` le {time.strftime('%d/%m/%Y à %H:%M')}.*" + (" **(essai réduit)**" if essai else ""),
        "",
        "## Protocole",
        "",
        "- Même protocole que l'essai Chris Evans, répété sur **" + str(n) + " personnes** : photo la plus **ancienne** = enrôlement ; photo **intermédiaire** = apprentissage validé (ce que ferait une confirmation par empreinte) ; "
        f"photo la plus **récente** = test, au moins {ECART_MIN} ans après l'enrôlement. Distance cosinus de la chaîne de BioGate (Haar, CLAHE, FaceNet512), reconnue sous **{fr(SEUIL, 2)}**.",
        f"- **Sélection fixée avant tout résultat** : liste de candidats (`candidats_vieillissement.csv`) ordonnée par case (6 régions × 2 sexes) puis par prénom ; les {PAR_CELLULE} premiers candidats de chaque case qui satisfont tous les critères sont retenus, sans aucun choix à la main.",
        "- **Photos** : Wikimedia Commons, licence libre (CC BY, CC BY-SA, CC0, domaine public), date de prise de vue dans les métadonnées, largeur d'au moins 400 px, **nom de la personne dans le nom du fichier** (c'est le sujet de la photo), "
        f"un seul visage de face d'au moins {VISAGE_MIN} px (Haar de BioGate confirmé par MediaPipe). Vérification d'identité : une distance supérieure à {fr(DISTANCE_IDENTITE_MAX, 2)} entre deux des trois photos (typique de deux personnes différentes) fait écarter le candidat.",
        "- Sexe et région (continent de nationalité) viennent des biographies publiques ; ils servent seulement à répartir l'évaluation. Les images ne sont pas copiées dans le dépôt : `manifeste_photos.csv` donne les pages Commons, auteurs, licences et années.",
        "",
        "## Résultats globaux",
        "",
        f"- Personnes reconnues avec le **profil d'origine** (une photo, souvent ancienne) : **{pct(ka, n)}**.",
        f"- Après **apprentissage** d'une photo intermédiaire : **{pct(kb, n)}**. {b} personnes passent de « non reconnue » à « reconnue » (test exact de McNemar : p = {fr(mcnemar_exact(b, 0), 4)}, aucune personne ne se dégrade : le minimum sur davantage de vecteurs ne peut qu'améliorer).",
        f"- Distance moyenne au profil : **{fr(d_av[0], 3)}** [{fr(d_av[1], 3)} ; {fr(d_av[2], 3)}] avant, **{fr(d_ap[0], 3)}** [{fr(d_ap[1], 3)} ; {fr(d_ap[2], 3)}] après ; baisse moyenne {fr(gain[0], 3)} [{fr(gain[1], 3)} ; {fr(gain[2], 3)}] (intervalles de confiance à 95 % par rééchantillonnage des personnes).",
        f"- **Effet des années** : la distance entre la photo d'enrôlement et la photo de test augmente avec l'écart d'années (Spearman ρ = {fr(rho, 2)}, p = {fr(p_rho, 3)} ; pente de {fr(10 * pente, 3)} par décennie).",
        f"- **Fausses acceptations** : photos de test d'autres personnes du jeu acceptées par un profil : {A['imp_avant']} sur {A['imp_total']} avant, {A['imp_apres']} sur {A['imp_total']} après apprentissage.",
        "",
        "![Vieillissement](vieillissement.png)",
        "",
        "## Par région et par sexe (descriptif)",
        "",
    ] + tab(groupe(S, "region", REGIONS), "Région") + [""] + tab(groupe(S, "sexe", ["F", "M"]), "Sexe") + [
        "",
        "Les effectifs par groupe sont petits : les intervalles (Wilson, 95 %) sont larges et **ces lignes décrivent l'échantillon, elles ne prouvent aucune différence entre groupes**. "
        "Pour une étude des écarts selon l'origine, le rapport 8280 du NIST (Grother et coll., 2019) porte sur des millions d'images ; il est cité au chapitre 1.",
        "",
        "## Le filtre de visage de BioGate (Haar + MediaPipe) selon la région et le sexe (descriptif)",
        "",
        "Pour chaque photo admissible testée (licence, date, taille, nom dans le fichier), motif du rejet ou validation par le filtre de visage de BioGate. "
        "« Plusieurs visages » et « aucun visage » dépendent aussi du type de photo (événement, groupe, pose) : **ce tableau décrit l'échantillon, il ne prouve pas un biais du détecteur**.",
        "",
    ] + detection(journal, "region", REGIONS) + [""] + detection(journal, "sexe", ["F", "M"]) + [
        "",
        "## Candidats examinés",
        "",
        f"- {len(journal)} candidats examinés, **{n} retenus**. Motifs d'écart : " + "; ".join(f"{v} × {k}" for k, v in sorted(raisons.items(), key=lambda x: -x[1])) + ".",
        "- Détail dans `candidats_journal.csv`.",
        "",
        "## Limites",
        "",
        "- Les personnes sont des **célébrités très photographiées** : photos de presse ou d'événements, plus soignées qu'une caméra de porte, et retouchées parfois ; les taux absolus ne se transposent pas tels quels à BioGate.",
        "- La sélection exige un seul visage de face détecté par Haar : elle favorise les portraits nets et exclut les poses difficiles (risque de **surestimer** la reconnaissance).",
        "- Le « continent » est celui de la nationalité, pas l'origine ethnique ni la couleur de peau ; le sexe est binaire (biographies publiques). Ce n'est pas une étude des biais démographiques.",
        "- Une seule photo d'apprentissage et une seule photo de test par personne ; la date vient des métadonnées de Commons (une erreur de date est possible). La vérification d'identité écarte les cas manifestes, pas tous.",
        "- Les photos ne couvrent pas toujours une vraie évolution (barbe, coiffure) : l'écart est mesuré en années, pas en changement d'apparence.",
        "",
        "## Matériel et versions",
        "",
    ] + [f"- {k} : {v}" for k, v in materiel().items()] + [f"- Durée : {duree:.0f} s"]
    return "\n".join(R) + "\n"


# ----------------------------------------------------------------------------- programme

def main(sortie, essai=False):
    os.makedirs(sortie, exist_ok=True)
    t0 = time.time()
    par_cellule = 1 if essai else PAR_CELLULE
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "candidats_vieillissement.csv"), encoding="utf-8") as f:
        candidats = list(csv.DictReader(f))
    if essai:
        candidats = candidats[:10] + [c for c in candidats if c["region"] == "Europe" and c["sexe"] == "M"][:6]

    import config
    config.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="biogate-vieill-"), "visages.db")
    from deepface import DeepFace
    from core.face_recognizer import FaceRecognizer
    from core.logger import VisualLogger
    fr_ = FaceRecognizer(logger=VisualLogger(), trust_mgr=None)
    fr_._get_landmarker()
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    dossier = os.path.join(sortie, "photos_temporaires")
    os.makedirs(dossier, exist_ok=True)

    retenus, journal, compte = [], [], {}
    for c in candidats:
        case = (c["region"], c["sexe"])
        if compte.get(case, 0) >= par_cellule:
            continue
        nom = c["nom"]
        ligne = {"nom": nom, "region": c["region"], "sexe": c["sexe"], "statut": "", "detail": "", "aucun": 0, "plusieurs": 0, "non_confirme": 0, "ok": 0}
        try:
            fichiers = lister(nom)
        except Exception as exc:
            ligne.update(statut="catégorie introuvable ou inaccessible", detail=str(exc)[:80])
            journal.append(ligne)
            print(f"  {nom:28s} : catégorie introuvable", flush=True)
            continue
        garde, nb_adm = echantillon(fichiers, nom)
        valides = []
        motifs = {"aucun": 0, "plusieurs": 0, "non_confirme": 0, "ok": 0}
        for f in garde:
            chemin = telecharger(f, dossier)
            image = cv2.imread(chemin) if chemin else None
            if image is None:
                continue
            rect, motif = visage_unique(fr_, image)
            motifs[motif] += 1
            if rect:
                valides.append((f, rect[2], chemin))
        ligne.update(motifs)
        if len(valides) < 3:
            ligne.update(statut="moins de 3 photos valides", detail=f"{len(fichiers)} fichiers, {nb_adm} admissibles, {len(valides)} avec un seul visage de face")
            journal.append(ligne)
            print(f"  {nom:28s} : {len(fichiers)} fichiers, {nb_adm} admissibles, {len(valides)} valides -> écarté", flush=True)
            continue
        trois, raison = choisir_trois(valides)
        if trois is None:
            ligne.update(statut="écart d'années ou photo intermédiaire insuffisant", detail=raison)
            journal.append(ligne)
            print(f"  {nom:28s} : {raison} -> écarté", flush=True)
            continue
        stats = {"haar": 0, "entiere": 0}
        emb = [signature(DeepFace, clahe, fr_.face_cascade, cv2.imread(v[2]), stats) for v in trois]
        d = [distance_cosinus(emb[0], emb[1]), distance_cosinus(emb[0], emb[2]), distance_cosinus(emb[1], emb[2])]
        if max(d) > DISTANCE_IDENTITE_MAX:
            ligne.update(statut="identité douteuse", detail="distances " + "/".join(f"{x:.2f}" for x in d))
            journal.append(ligne)
            print(f"  {nom:28s} : identité douteuse {['%.2f' % x for x in d]} -> écarté", flush=True)
            continue
        sid = f"V{len(retenus) + 1:02d}"
        retenus.append({"id": sid, "nom": nom, "region": c["region"], "sexe": c["sexe"], "emb": emb,
                        "annees": [v[0]["annee"] for v in trois], "fichiers": [v[0] for v in trois]})
        compte[case] = compte.get(case, 0) + 1
        ligne.update(statut="retenu", detail=f"{trois[0][0]['annee']} / {trois[1][0]['annee']} / {trois[2][0]['annee']}")
        journal.append(ligne)
        print(f"  {nom:28s} : RETENU ({ligne['detail']}) distances {['%.2f' % x for x in d]}", flush=True)

    if len(retenus) < 3:
        raise SystemExit("Moins de 3 personnes retenues : analyse impossible.")
    A = analyser(retenus)
    duree = time.time() - t0

    with open(os.path.join(sortie, "manifeste_photos.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sujet", "nom", "sexe", "region", "role", "annee", "titre_fichier_commons", "licence", "auteur", "page_commons"])
        for s in retenus:
            for role, fi in zip(("enrôlement", "apprentissage", "test"), s["fichiers"]):
                w.writerow([s["id"], s["nom"], s["sexe"], s["region"], role, fi["annee"], fi["titre"], fi["licence"], fi["auteur"], fi["page"]])
    with open(os.path.join(sortie, "candidats_journal.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["nom", "region", "sexe", "statut", "detail", "aucun", "plusieurs", "non_confirme", "ok"])
        w.writeheader()
        w.writerows(journal)
    with open(os.path.join(sortie, "sujets_vieillissement.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sujet", "sexe", "region", "annee_enrolement", "annee_apprentissage", "annee_test", "ecart_annees", "distance_E_L", "distance_E_T",
                    "distance_L_T", "distance_avant_apprentissage", "distance_apres_apprentissage", "reconnu_avant", "reconnu_apres"])
        for s in retenus:
            w.writerow([s["id"], s["sexe"], s["region"], *s["annees"], s["ecart"], f"{s['d_EL']:.4f}", f"{s['d_ET']:.4f}", f"{s['d_LT']:.4f}",
                        f"{s['avant']:.4f}", f"{s['apres']:.4f}", int(s["avant"] < SEUIL), int(s["apres"] < SEUIL)])
    figure(retenus, os.path.join(sortie, "vieillissement.png"))
    with open(os.path.join(sortie, "rapport_vieillissement.md"), "w", encoding="utf-8") as f:
        f.write(rapport(retenus, A, journal, duree, essai))
    ka = sum(s["avant"] < SEUIL for s in retenus)
    kb = sum(s["apres"] < SEUIL for s in retenus)
    print(f"{len(retenus)} personnes retenues : reconnues {ka} -> {kb} | rapport dans {sortie} ({duree:.0f} s)", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1], essai="--essai" in sys.argv)
