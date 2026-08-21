# Registre des Erreurs d'Implémentation et Optimisations (Hallucinations de Code)

Ce document recense les problèmes de performance causés par des erreurs d'implémentation dans le code généré (hallucinations ou maladresses), ainsi que les approches d'optimisation prévues pour les corriger.

## 1. Redondance des calculs du "Face Gate" (HaarCascade)

**Fichiers concernés :** `api.py` et `core/face_recognizer.py`

**Le problème :**
Le concept théorique du "Face Gate" (filtrer les visages non-frontaux pour éviter les calculs inutiles) est excellent. Cependant, l'implémentation actuelle exécute l'algorithme `detectMultiScale` (HaarCascade) deux fois de suite sur la même image pour chaque personne détectée :
1. Une première fois dans `api.py` (ligne 89) uniquement pour isoler la tête et dessiner la boîte cyan (UI) sur le flux client.
2. Une seconde fois dans `face_recognizer.py` (ligne 215) à l'intérieur de la méthode `identify()` pour valider que Facenet512 peut s'exécuter sur un visage correct.

Sur un matériel Edge limitant comme un Raspberry Pi, exécuter la cascade Haar en double divise inutilement les performances par deux.

**Approche d'optimisation :**
- Exécuter le `Face Gate` **une seule fois** (le plus logique étant à l'intérieur de `face_recognizer.py`).
- Modifier la signature de `identify()` pour qu'elle renvoie un tuple contenant à la fois l'identité et les coordonnées du visage (s'il est détecté).
- Dans `api.py`, récupérer ces coordonnées directement depuis la réponse de l'IA et les utiliser pour l'UI, supprimant ainsi la détection HaarCascade redondante.

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
