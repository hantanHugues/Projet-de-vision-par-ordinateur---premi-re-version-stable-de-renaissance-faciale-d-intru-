"""
Mesure du FAR et du FRR de FaceNet512 sur les paires de test de LFW (Labeled Faces in the Wild).

Même chaîne que BioGate : détection du visage par Haar sur la silhouette, correction de contraste
CLAHE (canal L de l'espace LAB), puis DeepFace.represent (Facenet512, align=True, détecteur opencv),
distance cosinus. Le visage entier de l'image est utilisé quand Haar n'en trouve pas (comptés dans
le rapport).

  FAR (taux de fausses acceptations) : part des paires de PERSONNES DIFFÉRENTES dont la distance est
                                       sous le seuil, donc prises pour la même personne.
  FRR (taux de faux rejets)          : part des paires de la MÊME personne dont la distance est au-dessus
                                       du seuil, donc refusées.

Usage :
    .venv-deepface\\Scripts\\python.exe tests\\mesures\\mesure_far_frr.py <lfw-funneled.tgz> <pairsDevTest.txt> <dossier_sortie>

Sorties : distances.csv, far_frr.csv, far_frr.png, rapport_far_frr.md (et un cache d'embeddings).
"""

import csv
import os
import platform
import subprocess
import sys
import tarfile
import time

import cv2
import numpy as np

SEUIL_BIOGATE = 0.35


def lire_paires(chemin):
    """Format LFW : 1re ligne = N ; N lignes « nom i j » (même personne) ; N lignes « nom1 i nom2 j »."""
    lignes = [l.split() for l in open(chemin, encoding="utf-8").read().splitlines() if l.strip()]
    n = int(lignes[0][0])
    memes = [((a, int(i)), (a, int(j))) for a, i, j in lignes[1:1 + n]]
    differentes = [((a, int(i)), (b, int(j))) for a, i, b, j in lignes[1 + n:1 + 2 * n]]
    return memes, differentes


def nom_fichier(nom, i):
    return f"lfw_funneled/{nom}/{nom}_{i:04d}.jpg"


def extraire_images(archive, necessaires, dossier):
    """Extrait seulement les images voulues. Les chemins viennent de NOTRE liste, jamais de l'archive."""
    os.makedirs(dossier, exist_ok=True)
    voulus = {nom_fichier(n, i) for n, i in necessaires}
    trouves = 0
    with tarfile.open(archive, "r:gz") as tar:
        for membre in tar:
            if membre.isfile() and membre.name in voulus:
                donnees = tar.extractfile(membre).read()
                cible = os.path.join(dossier, membre.name.replace("/", "__"))
                with open(cible, "wb") as f:
                    f.write(donnees)
                trouves += 1
    return trouves, len(voulus)


def signature(deepface, clahe, haar, image_bgr, stats):
    gris = cv2.equalizeHist(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY))
    visages = haar.detectMultiScale(gris, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    if len(visages):
        x, y, w, h = visages[0]
        visage = image_bgr[y:y + h, x:x + w]
        stats["haar"] += 1
    else:
        visage = image_bgr
        stats["entiere"] += 1
    lab = cv2.cvtColor(visage, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    visage = cv2.cvtColor(cv2.merge((clahe.apply(l), a, b)), cv2.COLOR_LAB2BGR)
    res = deepface.represent(img_path=visage, model_name="Facenet512", enforce_detection=False,
                             align=True, detector_backend="opencv")
    return np.array(res[0]["embedding"], dtype=np.float32)


def distance_cosinus(a, b):
    return float(1 - np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def commande(cmd):
    try:
        return subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        return "inconnu"


def materiel():
    import tensorflow as tf
    from deepface import DeepFace  # noqa: F401
    import deepface
    return {
        "Système": platform.platform(),
        "Processeur": commande("(Get-CimInstance Win32_Processor | Select-Object -First 1).Name"),
        "Cœurs logiques": str(os.cpu_count()),
        "Mémoire": commande("[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1).ToString() + ' Go'"),
        "Python": platform.python_version(),
        "TensorFlow": tf.__version__,
        "DeepFace": getattr(deepface, "__version__", "?"),
        "OpenCV": cv2.__version__,
    }


def courbes(d_memes, d_diff, seuils):
    far = np.array([(d_diff < t).mean() for t in seuils])
    frr = np.array([(d_memes >= t).mean() for t in seuils])
    return far, frr


def main(archive, paires_txt, sortie):
    os.makedirs(sortie, exist_ok=True)
    memes, differentes = lire_paires(paires_txt)
    necessaires = sorted({p for paire in memes + differentes for p in paire})
    print(f"{len(memes)} paires identiques, {len(differentes)} paires différentes, {len(necessaires)} images uniques")

    dossier_images = os.path.join(sortie, "images_lfw")
    trouves, voulus = extraire_images(archive, necessaires, dossier_images)
    print(f"images extraites : {trouves}/{voulus}")

    from deepface import DeepFace
    haar = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    cache = os.path.join(sortie, "embeddings.npz")
    embeddings = {}
    if os.path.exists(cache):
        z = np.load(cache, allow_pickle=True)
        embeddings = dict(zip(z["cles"].tolist(), z["valeurs"]))
        print(f"cache d'embeddings repris : {len(embeddings)}")
    stats = {"haar": 0, "entiere": 0, "illisible": 0}
    t0 = time.time()
    for k, (nom, i) in enumerate(necessaires):
        cle = nom_fichier(nom, i)
        if cle in embeddings:
            continue
        chemin = os.path.join(dossier_images, cle.replace("/", "__"))
        image = cv2.imread(chemin)
        if image is None:
            stats["illisible"] += 1
            continue
        embeddings[cle] = signature(DeepFace, clahe, haar, image, stats)
        if (k + 1) % 100 == 0:
            ecoule = time.time() - t0
            print(f"  {k + 1}/{len(necessaires)} images, {ecoule:.0f} s ({ecoule / max(1, stats['haar'] + stats['entiere']):.2f} s par image)", flush=True)
            np.savez(cache, cles=np.array(list(embeddings.keys())), valeurs=np.array(list(embeddings.values())))
    np.savez(cache, cles=np.array(list(embeddings.keys())), valeurs=np.array(list(embeddings.values())))
    duree = time.time() - t0
    n_calc = stats["haar"] + stats["entiere"]
    print(f"embeddings calculés : {n_calc} en {duree:.0f} s")

    lignes, d_memes, d_diff = [], [], []
    for type_paire, liste in (("meme", memes), ("differente", differentes)):
        for (a, b) in liste:
            ka, kb = nom_fichier(*a), nom_fichier(*b)
            if ka in embeddings and kb in embeddings:
                d = distance_cosinus(embeddings[ka], embeddings[kb])
                (d_memes if type_paire == "meme" else d_diff).append(d)
                lignes.append((type_paire, ka, kb, f"{d:.4f}"))
    d_memes, d_diff = np.array(d_memes), np.array(d_diff)
    with open(os.path.join(sortie, "distances.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["type", "image_a", "image_b", "distance"]); w.writerows(lignes)

    seuils = np.round(np.arange(0.10, 0.801, 0.01), 2)
    far, frr = courbes(d_memes, d_diff, seuils)
    with open(os.path.join(sortie, "far_frr.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["seuil", "FAR", "FRR"])
        for t, a, b in zip(seuils, far, frr):
            w.writerow([f"{t:.2f}", f"{a:.4f}", f"{b:.4f}"])

    i_eer = int(np.argmin(np.abs(far - frr)))
    seuil_eer, eer = float(seuils[i_eer]), float((far[i_eer] + frr[i_eer]) / 2)
    i_b = int(np.argmin(np.abs(seuils - SEUIL_BIOGATE)))
    # AUC par rangs : probabilité qu'une paire identique ait une distance plus petite qu'une paire différente
    rangs = (d_memes[:, None] < d_diff[None, :]).mean() + 0.5 * (d_memes[:, None] == d_diff[None, :]).mean()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
    ax[0].plot(seuils, 100 * far, label="FAR (inconnu accepté)", color="#c0392b", lw=2)
    ax[0].plot(seuils, 100 * frr, label="FRR (VIP refusé)", color="#2471a3", lw=2)
    ax[0].axvline(SEUIL_BIOGATE, color="#27ae60", ls="--", label=f"seuil BioGate {SEUIL_BIOGATE}")
    ax[0].scatter([seuil_eer], [100 * eer], color="black", zorder=5, label=f"EER {100 * eer:.1f} % (seuil {seuil_eer:.2f})")
    ax[0].set_xlabel("Seuil de distance cosinus"); ax[0].set_ylabel("Taux d'erreur (%)")
    ax[0].set_title("FAR et FRR selon le seuil (FaceNet512, paires LFW)"); ax[0].grid(alpha=.3); ax[0].legend()
    bacs = np.linspace(0, 1.2, 60)
    ax[1].hist(d_memes, bins=bacs, alpha=.65, color="#2471a3", label=f"même personne ({len(d_memes)} paires)")
    ax[1].hist(d_diff, bins=bacs, alpha=.65, color="#c0392b", label=f"personnes différentes ({len(d_diff)} paires)")
    ax[1].axvline(SEUIL_BIOGATE, color="#27ae60", ls="--", label=f"seuil {SEUIL_BIOGATE}")
    ax[1].set_xlabel("Distance cosinus"); ax[1].set_ylabel("Nombre de paires")
    ax[1].set_title("Distribution des distances"); ax[1].grid(alpha=.3); ax[1].legend()
    fig.tight_layout(); fig.savefig(os.path.join(sortie, "far_frr.png"), dpi=170); plt.close(fig)

    mat = materiel()
    choisis = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60]
    with open(os.path.join(sortie, "rapport_far_frr.md"), "w", encoding="utf-8") as f:
        f.write("# Mesure du FAR et du FRR de FaceNet512 sur LFW\n\n")
        f.write(f"*Généré par `tests/mesures/mesure_far_frr.py` le {time.strftime('%d/%m/%Y à %H:%M')}.*\n\n")
        f.write("## Protocole\n\n")
        f.write(f"- Base : LFW (Labeled Faces in the Wild), version « funneled », fichier de paires `pairsDevTest.txt` : "
                f"**{len(d_memes)} paires de la même personne** et **{len(d_diff)} paires de personnes différentes** "
                f"({len(embeddings)} images uniques).\n")
        f.write("- Chaîne identique à celle de BioGate : détection Haar du visage, CLAHE (canal L), `DeepFace.represent` "
                "(Facenet512, `align=True`, détecteur `opencv`), distance cosinus.\n")
        f.write(f"- Haar a trouvé un visage dans {stats['haar']} images ; sur {stats['entiere']} images il n'en a pas trouvé "
                f"et l'image entière a été utilisée ; {stats['illisible']} illisibles.\n")
        f.write("- FAR = part des paires de personnes différentes dont la distance est **sous** le seuil (un inconnu serait accepté). "
                "FRR = part des paires de la même personne dont la distance est **au-dessus** du seuil (un VIP serait refusé).\n\n")
        f.write("## Résultats\n\n")
        f.write(f"- Seuil de BioGate : **{SEUIL_BIOGATE}** → FAR **{100 * far[i_b]:.1f} %**, FRR **{100 * frr[i_b]:.1f} %**.\n")
        f.write(f"- Point d'égal taux d'erreur (EER) : **{100 * eer:.1f} %** au seuil **{seuil_eer:.2f}**.\n")
        f.write(f"- Aire sous la courbe ROC (probabilité qu'une paire identique soit plus proche qu'une paire différente) : **{rangs:.3f}**.\n")
        f.write(f"- Distance moyenne : même personne **{d_memes.mean():.3f}** (écart-type {d_memes.std():.3f}), "
                f"personnes différentes **{d_diff.mean():.3f}** (écart-type {d_diff.std():.3f}).\n\n")
        f.write("| Seuil | FAR (%) | FRR (%) |\n|---|---|---|\n")
        for t in choisis:
            j = int(np.argmin(np.abs(seuils - t)))
            marque = " ← BioGate" if abs(t - SEUIL_BIOGATE) < 1e-9 else ""
            f.write(f"| {t:.2f}{marque} | {100 * far[j]:.1f} | {100 * frr[j]:.1f} |\n")
        f.write("\n![FAR et FRR](far_frr.png)\n\n")
        f.write("## Matériel et versions\n\n")
        for k, v in mat.items():
            f.write(f"- {k} : {v}\n")
        f.write(f"\nTemps de calcul des embeddings : {duree:.0f} s pour {n_calc} images "
                f"({duree / max(1, n_calc):.2f} s par image, Haar + CLAHE + FaceNet512 sur processeur).\n")
        f.write("\n## Limites\n\n")
        f.write("- LFW contient des photos de personnalités prises dans des conditions variées, pas des visages devant "
                "une caméra de porte ; les chiffres donnent un ordre de grandeur et justifient le choix du seuil, pas une "
                "garantie en conditions réelles.\n")
        f.write("- Une seule série de 1 000 paires ; pas de validation croisée sur les 10 séries de LFW.\n")
        f.write("- BioGate compare à plusieurs échantillons par personne (le plus proche gagne) : son FRR réel est plus bas "
                "que celui de cette mesure à un seul échantillon, son FAR un peu plus haut.\n")
    print(f"FAR à {SEUIL_BIOGATE} : {100 * far[i_b]:.1f} % | FRR : {100 * frr[i_b]:.1f} % | EER : {100 * eer:.1f} % au seuil {seuil_eer:.2f} | AUC : {rangs:.3f}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
