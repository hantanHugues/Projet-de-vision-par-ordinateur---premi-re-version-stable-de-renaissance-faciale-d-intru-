# SurveilleIA — Backend (Hub de Décision)

Système de surveillance intelligente basé sur l'IA distribuée.  
Ce backend est le "cerveau" du système — il reçoit les flux vidéo, les analyse et prend des décisions.

## Architecture

```
backend/
├── config.py          # Configuration centralisée
├── main.py            # Point d'entrée principal
├── sources/           # Abstraction des sources vidéo
│   ├── base.py        #   → Interface abstraite VideoSource
│   └── webcam.py      #   → Implémentation webcam locale
├── core/              # Modules d'IA
│   ├── __init__.py    
│   ├── yolo_detector.py # → Moteur YOLOv8 (Phase 2)
│   ├── pose_analyzer.py # → Analyse posturale MediaPipe (Phase 3)
│   └── logger.py        # → Visual Logger console + vidéo (Phase 2.5)
├── tests/             # Tests unitaires et d'intégration
└── docs/
    └── lab_journal.md # Journal de laboratoire scientifique
```

## Installation

```bash
# Installer 'uv' (Gestionnaire de paquets et Python isolé ultra-rapide)
# PowerShell (Windows) :
Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -UseBasicParsing | Invoke-Expression

# 1. Créer l'environnement virtuel avec un Python 3.11 isolé et propre (Pour DeepFace)
uv venv --python 3.11 .venv-deepface

# 2. Activer l'environnement
.venv-deepface\Scripts\activate        # Windows

# 3. Installer les dépendances très rapidement
uv pip install -r requirements.txt
```

## Utilisation

Assurez-vous d'être dans `.venv-deepface` puis tapez :
```bash
python main.py
```

**Contrôles :**
- `q` → Quitter

## Phases de développement

| Phase | Description | Statut |
|-------|-------------|--------|
| 0 | Setup + capture vidéo | ✅ Complété |
| 1 | Multi-source vidéo | ⏳ |
| 2 | Détection humaine (YOLOv8n) | ✅ Complété |
| 2.5 | Visual Logger (terminal incrusté vidéo) | ✅ Complété |
| 3 | Analyse posturale (MediaPipe) | ❌ Inadapté (cf. Journal) |
| 4 | Suivi d'objets (Centroid Tracker) | ✅ Complété |
| 5 | Reconnaissance faciale (DeepFace/VGG) | ✅ Complété |
| 6 | Architecture Serveur (FastAPI + SQLite) | ✅ Complété |
| 7 | Source ESP32-CAM | ⏳ |

## Historique d'Implémentation (Trace)

- **Phase 0 (2026-04-05)** : Création de la structure abstraite `VideoSource`. Intégration de `cv2.VideoCapture` pour la `WebcamSource`. Boucle de capture dans `main.py` avec affichage des FPS. Refonte sécurisée du `.venv` suite à panne de courant. Validé par l'opérateur.
- **Phase 2 (2026-04-05)** : Avancement anticipé sur la Phase 2 pour l'optimisation Hub de Décision (Raspberry Pi). Ajout du package `ultralytics` et PyTorch. Création de `YoloDetector`. Configuration du filtrage `classes=[0]` (Humains uniquement) avec seuil à `0.5`. Câblage temps réel dans `main.py` avec `cv2.rectangle` pour l'inférence visuelle.
- **Phase 2.5 & Tests (2026-04-05)** : L'opérateur a testé la Phase 2 : succès de la détection humaine, mais identification d'une faille logique classique (YOLO a été trompé par la photo 2D d'un humain sur un téléphone). Création immédiate de `core/logger.py` (VisualLogger) pour intercepter et afficher les logs système dans un terminal incrusté en bas de la vidéo OpenCV. Validation de l'outil de log par l'opérateur.
- **Phase 3 — Code (2026-04-05)** :
  - `requirements.txt` : ajout de `mediapipe>=0.10.8` (ligne 15).
  - `config.py` : ajout de la section `IA - POSTURE (Phase 3)` avec `POSE_MIN_DETECTION_CONFIDENCE = 0.5` et `POSE_MIN_TRACKING_CONFIDENCE = 0.5` (lignes 58-65).
  - `core/pose_analyzer.py` : [NEW] Classe `PoseAnalyzer`. Méthode `analyze_and_draw(frame)` retourne `(annotated_frame, has_skeleton)`. Convertit BGR→RGB avant l'analyse. Désactive `.flags.writeable` sur le buffer RGB (optimisation mémoire). Dessine les landmarks avec `mp.solutions.drawing_utils`.
  - `main.py` : ajout de `from core.pose_analyzer import PoseAnalyzer` (ligne 23). Instanciation de `PoseAnalyzer(logger)` après `YoloDetector` (ligne 72). Logique conditionnelle : MediaPipe n'est appelé QUE si `len(detections) > 0` (lignes 130-140). Affichage détaillé des temps : `YOLO: Xms | Pose: Xms | Total: Xms` (ligne 144). Mise à jour du docstring de `main.py` : "Phase 3" (ligne 8).
  - `README.md` : arbre architecture mis à jour avec `pose_analyzer.py` et `logger.py`. Tableau des phases mis à jour.
- **Phase 3 — Bilan et Conclusion (2026-04-05)** : Tests en conditions réelles avec l'opérateur. L'analyse anti-spoofing par profondeur Z de l'IA (MediaPipe Pose) est trop capricieuse face à la résolution/qualité d'une webcam classique (fluctuations causant de fausses alertes). Conclusion architecturale cruciale : la validation 3D est inadaptée aux ressources et caméras du setup final (ESP32-CAM + Raspberry Pi). Le module de pose est conservé mais désengagé de la boucle d'alerte principale. Basculement stratégique vers la Phase 4 (Suivi Tracking).
- **Phase 4 & Préparation Phase 5 (2026-04-05)** : Centroid Tracker validé — les ID sont assignés avec la distance Euclidienne sans planter. Le tracker permet de simuler un humain "continu", ce qui donne un socle parfait pour l'économie CPU avant la Phase 5 (création du _FaceRecognizer_ avec cache : si YOLO détecte "ID 1", on ne fait le calcul IA qu'une fois, et on retourne le prénom stocké pour 0% de charge sur les frames suivantes).
- **Phase 5 — Reconnaissance DeepFace (2026-04-06)** : Extraction de vecteurs biométriques (512D) avec VGG-Face isolée dans `.venv-deepface` (Python 3.11) via `uv`. Phase d'étalonnage stricte effectuée pour balancer les *Faux Positifs* et *Faux Négatifs* en production. Le `threshold` Cosinus a été solidement fixé à 0.40 pour différencier deux visages familiaux, associé à un `max_disappeared` du Tracker à 60 frames pour absorber les micro-pertes de détection.
- **Phase 6 — (En cours)** : Refonte de la boucle locale vers une infrastructure Serveur (FastAPI) et Base de données (SQLite) pour héberger ce moteur d'IA.
