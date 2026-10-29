# Registre des Erreurs d'Implémentation et Optimisations (Hallucinations de Code)

Ce document recense les problèmes de performance causés par des erreurs d'implémentation dans le code généré (hallucinations ou maladresses), ainsi que les approches d'optimisation prévues pour les corriger.

## 1. ~~Redondance des calculs du "Face Gate" (HaarCascade)~~ — ✅ RÉSOLU

**Fichiers concernés :** `api.py` et `core/face_recognizer.py`

**Résolu le :** 2026-10-28

Le Face Gate ne tourne plus qu'une fois par personne et par image. `identify()` mémorise la position du visage (relative à la silhouette) et `api.py` la réutilise pour l'encadré affiché par le client, via `FaceRecognizer.get_face_box()` qui la replace sur la silhouette courante : l'encadré suit la personne entre deux passages du Face Gate, sans nouvelle détection.

Mesuré (`tests/bench_face_gate.py`, rapport `tests/rapport_face_gate.md`) : 2 → 1 détection par image pendant l'identification, 1,28 → 0,24 une fois la personne identifiée, soit de −48 % à −78 % de temps sur la route `/analyze_frame` (YOLO et FaceNet exclus de la mesure). Verrouillé par `tests/test_face_gate.py`. Le mode multi-caméras du dashboard n'était pas concerné : il n'affiche pas d'encadré de visage.

---

## 2. ~~Goulot d'étranglement I/O et CPU sur la Base de Données (SQLite)~~ — ✅ RÉSOLU

**Fichiers concernés :** `core/face_recognizer.py` et `database/db_manager.py`

**Résolu le :** 2026-07 (implémenté dans face_recognizer.py)

`_find_in_memory()` utilise désormais `self._embeddings_cache` (dict Python chargé en RAM au démarrage depuis SQLite). Aucune I/O disque lors des analyses. Le cache est mis à jour uniquement à `/enroll` et `learn_from_confirmation()`.

---

## 3. ~~Nettoyage du Code Obsolète (Vestiges du Liveness Temporel)~~ — ✅ RÉSOLU

**Fichiers concernés :** `core/face_recognizer.py`, `config.py`, `main.py`

**Résolu le :** 2026-08-10

Variables `LIVENESS_TIME_LIMIT`, `POSE_MIN_DETECTION_CONFIDENCE`, `POSE_MIN_TRACKING_CONFIDENCE` supprimées. Import `PoseAnalyzer` et instanciation retirés de `main.py`. Variable morte `active_names_on_screen` retirée de `face_recognizer.py`.

---

## 4. ~~Aucun cadre sur les personnes non reconnues (dashboard)~~ — ✅ RÉSOLU

**Fichiers concernés :** `api.py` (`_run_pipeline_and_annotate`)

**Résolu le :** 2026-10-29 (découvert en lisant le journal du serveur pendant un test à la webcam)

`identify()` renvoie un texte (le nom, `Intrus_001`, `Analyse… (0.4s)`), mais le pipeline multi-caméras appelait `identity.get("name", "?")` dessus. Pour toute personne sans nom de VIP (inconnu, intrus, analyse en cours), cela levait `AttributeError`, avalée par le `try` englobant : toutes les annotations de l'image étaient perdues. Résultat visible : l'utilisateur avait son cadre, l'intrus n'en avait aucun, et les personnes suivantes de l'image n'étaient même pas traitées. Le journal se remplissait de `[PIPELINE] … 'str' object has no attribute 'get'` (996 fois en deux minutes de test). La détection d'intrusion elle-même (Trust Score, photo, alerte) fonctionnait, car elle s'exécute avant la ligne fautive.

Corrigé en `or str(identity)`. Verrouillé par `tests/test_face_gate.py::PipelineAnnotationsTest`, qui obtient 0 annotation au lieu de 2 sur l'ancien code.
