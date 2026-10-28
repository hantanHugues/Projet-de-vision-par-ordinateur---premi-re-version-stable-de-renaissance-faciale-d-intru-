"""
Test scientifique — Apprentissage continu (Ground Truth Learning) face au
vieillissement / changement d'apparence (barbe, lunettes, etc.)

CONTEXTE
--------
Le système apprend de nouveaux échantillons du visage d'un VIP quand une
empreinte digitale confirme son identité malgré un échec de reconnaissance
faciale (voir core/face_recognizer.py:learn_from_confirmation, appelé
depuis POST /fingerprint_result quand success=True). Ce script reproduit
ce mécanisme hors ligne pour prouver, avec des chiffres reproductibles,
que l'apprentissage résout bien le problème plutôt que de l'affirmer.

PROTOCOLE (à citer tel quel dans le mémoire)
---------------------------------------------
1. ENRÔLEMENT — le profil VIP est créé avec UNE photo de référence ("avant").
2. BASELINE — une photo "après" (changement d'apparence) est présentée au
   moteur de reconnaissance AVANT tout apprentissage. Le système doit
   échouer (distance > seuil) : ceci établit que le problème existe
   réellement, et n'est pas juste supposé.
3. APPRENTISSAGE — la photo "après" #1 est ajoutée comme gabarit
   supplémentaire du même profil, exactement comme le ferait une
   confirmation par empreinte en conditions réelles.
4. VALIDATION — une AUTRE photo "après" (--after2, différente de celle
   utilisée pour l'apprentissage) est présentée. Le système doit maintenant
   reconnaître le sujet : preuve que l'apprentissage généralise à une
   nouvelle photo, pas seulement qu'il "se souvient" du fichier exact
   qu'on vient de lui donner (ce qui serait un test trivial et sans valeur
   scientifique — la distance serait quasi nulle par construction).
   Sans --after2, le script réutilise --after1 pour l'étape 4 et le signale
   clairement dans le rapport comme un test moins rigoureux.

Utilise directement core.face_recognizer.FaceRecognizer — même modèle
(FaceNet512), même seuil (config.FACE_RECOGNITION_THRESHOLD), même formule
de distance cosinus que le système réel — sur une base de données SQLite
TEMPORAIRE. database/visages.db (les vrais profils) n'est jamais touché.

USAGE (depuis la racine du projet, avec l'interpréteur .venv-deepface) :
    .venv-deepface\\Scripts\\python.exe tests\\test_continuous_learning.py ^
        --clean photos\\avant.jpg ^
        --after1 photos\\apres_apprentissage.jpg ^
        --after2 photos\\apres_validation.jpg ^
        --name "Sujet Test" ^
        --report rapport_apprentissage_continu.md
"""

import argparse
import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2  # noqa: E402
import config  # noqa: E402


def detect_and_crop_face(fr, image_path):
    """Même Face Gate que /enroll côté API : un visage net, un seul."""
    frame = cv2.imread(image_path)
    if frame is None:
        raise ValueError(f"Impossible de lire l'image : {image_path}")
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = fr.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    if len(faces) == 0:
        raise ValueError(f"Aucun visage net détecté dans : {image_path}")
    if len(faces) > 1:
        raise ValueError(f"Plusieurs visages détectés dans : {image_path} — utilisez une photo avec une seule personne.")
    x, y, w, h = faces[0]
    return frame[y:y + h, x:x + w]


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--clean",  required=True, help="Photo de référence (avant changement d'apparence)")
    parser.add_argument("--after1", required=True, help="Photo 'après' utilisée pour déclencher l'apprentissage")
    parser.add_argument("--after2", help="Photo 'après' DIFFÉRENTE utilisée pour valider — fortement recommandé")
    parser.add_argument("--name",   default="Sujet_Test", help="Nom du profil VIP de test")
    parser.add_argument("--report", help="Chemin du rapport Markdown à générer (optionnel)")
    args = parser.parse_args()

    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    config.DB_PATH = tmp_db  # DB isolée — doit être fixé AVANT d'importer FaceRecognizer

    from core.logger import VisualLogger
    from core.face_recognizer import FaceRecognizer

    logger = VisualLogger()
    fr = FaceRecognizer(logger=logger, trust_mgr=None)

    results = {"name": args.name, "threshold": config.FACE_RECOGNITION_THRESHOLD, "steps": []}

    def log_step(title, **kw):
        print(f"\n=== {title} ===")
        for k, v in kw.items():
            print(f"  {k}: {v}")
        results["steps"].append({"title": title, **kw})

    try:
        # 1 — Enrôlement de référence
        clean_sig = fr._extract_face_signature(detect_and_crop_face(fr, args.clean))
        if clean_sig is None:
            print("ÉCHEC : extraction du gabarit de référence impossible (éclairage ? photo ?).")
            sys.exit(1)
        fr.db.add_embedding(args.name, clean_sig, role="VIP")
        fr.reload_cache()
        log_step("1. Enrôlement de référence (avant)",
                  photo=args.clean, gabarits=len(fr._embeddings_cache[args.name]))

        # 2 — BASELINE : reconnaissance AVANT apprentissage
        after1_sig = fr._extract_face_signature(detect_and_crop_face(fr, args.after1))
        if after1_sig is None:
            print("ÉCHEC : extraction du gabarit 'après' #1 impossible.")
            sys.exit(1)
        match1, dist1 = fr._find_in_memory(after1_sig, current_object_id=-1)
        baseline_recognized = match1 is not None
        log_step("2. BASELINE — reconnaissance avant apprentissage",
                  photo=args.after1, distance=round(float(dist1), 4),
                  seuil=config.FACE_RECOGNITION_THRESHOLD,
                  resultat="RECONNU" if baseline_recognized else "NON RECONNU (attendu à ce stade)")

        # 3 — Apprentissage (Ground Truth Learning simulé)
        fr.db.add_embedding(args.name, after1_sig, role="VIP")
        fr.reload_cache()
        log_step("3. Apprentissage continu (Ground Truth Learning simulé)",
                  gabarits_total=len(fr._embeddings_cache[args.name]))

        # 4 — VALIDATION : reconnaissance APRÈS apprentissage
        val_path = args.after2 or args.after1
        val_sig = fr._extract_face_signature(detect_and_crop_face(fr, val_path))
        if val_sig is None:
            print("ÉCHEC : extraction du gabarit de validation impossible.")
            sys.exit(1)
        match2, dist2 = fr._find_in_memory(val_sig, current_object_id=-1)
        validation_recognized = match2 is not None
        log_step("4. VALIDATION — reconnaissance après apprentissage",
                  photo=val_path, distance=round(float(dist2), 4),
                  seuil=config.FACE_RECOGNITION_THRESHOLD,
                  resultat="RECONNU" if validation_recognized else "NON RECONNU",
                  rigueur=("photo différente de l'apprentissage — test rigoureux" if args.after2 else
                           "ATTENTION : identique à la photo d'apprentissage — distance quasi nulle "
                           "par construction, préférez --after2 pour une vraie preuve de généralisation"))

        verdict = (not baseline_recognized) and validation_recognized
        results["verdict"]                = verdict
        results["baseline_recognized"]    = baseline_recognized
        results["validation_recognized"]  = validation_recognized
        results["rigorous"]               = bool(args.after2)

        print("\n" + "=" * 64)
        print(f"VERDICT : {'HYPOTHÈSE CONFIRMÉE' if verdict else 'HYPOTHÈSE NON CONFIRMÉE'}")
        print(f"  Avant apprentissage : {'reconnu' if baseline_recognized else 'NON reconnu'} (distance {dist1:.4f})")
        print(f"  Après apprentissage  : {'reconnu' if validation_recognized else 'NON reconnu'} (distance {dist2:.4f})")
        if not args.after2:
            print("  (rappel : --after2 absent, la validation a réutilisé la photo d'apprentissage)")
        print("=" * 64)

        if args.report:
            write_report(args.report, results)
            print(f"\nRapport généré : {args.report}")

    finally:
        try:
            os.remove(tmp_db)
        except OSError:
            pass


def write_report(path, r):
    rows = "\n".join(
        f"| {s['title']} | {s['distance']} | {s.get('resultat', '—')} |"
        for s in r["steps"] if "distance" in s
    )
    rigor_note = (
        "Photo de validation différente de celle d'apprentissage — résultat scientifiquement probant."
        if r["rigorous"] else
        "⚠️ Photo de validation identique à celle d'apprentissage — la reconnaissance après apprentissage "
        "est donc partiellement triviale (distance quasi nulle par construction). Refaire le test avec "
        "--after2 pour une preuve de généralisation solide."
    )
    conclusion = (
        "✅ **Hypothèse confirmée** : le système échoue à reconnaître le sujet après changement "
        "d'apparence tant qu'aucun apprentissage n'a eu lieu, et réussit après une seule confirmation "
        "d'identité — ce qui valide la légitimité du mécanisme d'apprentissage continu face au "
        "vieillissement et aux changements naturels d'apparence."
        if r["verdict"] else
        "⚠️ **Hypothèse non confirmée en l'état** — voir le détail des distances ci-dessus (qualité des "
        "photos, seuil de reconnaissance, ou choix des images) avant de conclure."
    )
    content = f"""# Rapport de test — Apprentissage continu face au changement d'apparence

*Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}*

## Méthodologie

Protocole en 4 étapes utilisant directement le moteur de reconnaissance du système
(FaceNet512, distance cosinus, seuil configuré), sur une base de données isolée
pour ne pas affecter les profils réels :

1. Enrôlement d'un profil de référence avec une photo "avant".
2. Tentative de reconnaissance d'une photo "après" (changement d'apparence) **avant**
   tout apprentissage — établit que le problème existe réellement.
3. Simulation du mécanisme d'apprentissage continu (Ground Truth Learning) : le
   visage "après" est ajouté comme gabarit supplémentaire du même profil, exactement
   comme le ferait une confirmation par empreinte digitale en conditions réelles.
4. Nouvelle tentative de reconnaissance sur une photo "après" — différente de celle
   utilisée pour l'apprentissage si possible — pour prouver la généralisation et pas
   seulement un rappel exact.

## Résultats

- **Sujet de test** : {r['name']}
- **Seuil de reconnaissance** (`FACE_RECOGNITION_THRESHOLD`) : {r['threshold']}
- **Rigueur du protocole** : {rigor_note}

| Étape | Distance cosinus | Résultat |
|---|---|---|
{rows}

## Conclusion

{conclusion}

## Reproductibilité

```
python tests/test_continuous_learning.py --clean <avant.jpg> --after1 <apres_1.jpg> \\
    --after2 <apres_2.jpg> --name "{r['name']}"
```

Base de données temporaire, isolée de `database/visages.db` — aucun profil réel n'est modifié.
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    main()
