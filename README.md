# BioGate — Infrastructure de contrôle d'accès biométrique

Système de contrôle d'accès intelligent : détection humaine, reconnaissance faciale,
authentification multi-facteurs (visage + liveness + empreinte), pilotage d'actionneurs
IoT et supervision via un dashboard desktop.

Architecture Edge Computing : tout le calcul IA (YOLO, FaceNet512, MediaPipe) tourne en
local, aucune dépendance Cloud.

## Architecture

Le projet est composé de deux applications séparées :

```
Projet-de-vision-par-ordinateur.../   ← Backend Python (ce dépôt)
├── api.py                  # Serveur FastAPI central — pipeline IA + toutes les routes
├── main.py                 # Pipeline standalone local (legacy pré-v7, sans réseau/MFA/IoT)
├── client_camera.py        # Client caméra multithreadé (capture → API → affichage)
├── config.py                # Configuration centralisée (seuils, MFA, IoT, RGPD...)
├── core/
│   ├── yolo_detector.py     # Détection humaine (YOLOv8n)
│   ├── centroid_tracker.py  # Suivi par centroïde + Color Re-ID (HSV vestimentaire)
│   ├── face_recognizer.py   # Reconnaissance faciale FaceNet512 + cache RAM
│   ├── liveness_detector.py # Anti-spoofing actif (clignement/sourire, MediaPipe)
│   ├── trust_score.py       # Machine à états MFA (Trust Score 0→100%)
│   ├── iot_controller.py    # Pilotage porte / empreinte / éclairage (ESP32, mode mock inclus)
│   ├── camera_manager.py    # Gestion multi-caméras (USB/MJPEG/RTSP), un thread par caméra
│   └── logger.py            # Visual Logger (console + overlay vidéo)
├── database/
│   └── db_manager.py        # SQLite : profils, embeddings, event_logs, caméras
├── sources/                 # Abstraction des sources vidéo (Strategy pattern)
├── docs/                    # Cahier des charges, journal de labo, notes de décisions
└── Mémoire en latex/         # Mémoire de soutenance (non versionné, voir .gitignore)

biogate-dashboard/            # Frontend Electron (dépôt séparé, même racine de travail)
└── src/renderer/             # Dashboard React : logs, caméras, config, contrôle IoT
```

## Installation

```bash
# Installer 'uv' (gestionnaire de paquets Python ultra-rapide)
# PowerShell (Windows) :
Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -UseBasicParsing | Invoke-Expression

# 1. Créer l'environnement virtuel Python 3.11 (requis pour DeepFace)
uv venv --python 3.11 .venv-deepface

# 2. Activer l'environnement
.venv-deepface\Scripts\activate        # Windows

# 3. Installer les dépendances
uv pip install -r requirements.txt
```

## Utilisation

### 1. Démarrer le serveur central (FastAPI)

```bash
python -m uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

Expose ~30 routes : pipeline IA (`/analyze_frame`, `/enroll`), configuration
(`/config`, `/config/templates`), logs d'audit (`/logs`), gestion multi-caméras
(`/cameras`), IoT (`/iot/door`, `/iot/fingerprint`, `/iot/light`), liveness/MFA
(`/request_liveness`, `/liveness_result`, `/fingerprint_result`) et appairage du
dashboard (`/pair/request`, `/auth/token`).

Toutes les routes qui lisent ou modifient un état sensible (config, IoT, caméras,
profils, logs) exigent un token `Authorization: Bearer <token>`, obtenu via le flux
d'appairage PIN (`POST /pair/request` affiche un PIN dans le terminal serveur, le
dashboard l'échange contre un token via `POST /auth/token`).

### 2. Démarrer un client caméra (mode réseau)

```bash
python client_camera.py
```

Capture localement, envoie chaque frame à l'API, affiche le retour (boîtes, identités,
Trust Score) en overlay. Multithreadé pour ne pas figer l'affichage pendant l'appel réseau.

### 3. Démarrer le pipeline standalone (mode debug local, sans réseau)

```bash
python main.py
```

Pipeline complet en local (YOLO + Tracker + FaceNet512) sans passer par `api.py` ni
uvicorn — utile pour déboguer le pipeline IA seul. **Ne bénéficie pas** du MFA, du
liveness, de l'IoT ni du multi-caméras (ajoutés depuis dans `api.py`).

### 4. Démarrer le dashboard (Electron)

```bash
cd ../biogate-dashboard
npm install
npm run dev
```

Se connecte à l'API via l'appairage PIN, affiche le flux vidéo (MJPEG), les logs,
la gestion des caméras et le contrôle manuel des actionneurs IoT.

## Sécurité

- CORS restreint aux origines du dashboard (`localhost:5173/5174` + Electron `file://`).
- Toutes les routes de configuration/IoT/caméras/logs protégées par token Bearer.
- Base biométrique (`database/visages.db`) exclue du dépôt git (données personnelles,
  chaque installation génère la sienne en local).
- Purge RGPD des snapshots via `DELETE /logs/purge` (seuil par défaut
  `RGPD_SNAPSHOT_RETENTION_HOURS`, 72h) — déclenchée à la demande, **pas encore
  automatisée par un scheduler**.

## Phases de développement

| Phase | Description | Statut |
|-------|-------------|--------|
| 0 | Setup + capture vidéo | ✅ |
| 1 | Multi-source vidéo (abstraction Strategy) | ✅ |
| 2 | Détection humaine (YOLOv8n) | ✅ |
| 2.5 | Visual Logger (terminal incrusté vidéo) | ✅ |
| 3 | Analyse posturale 3D (MediaPipe Pose) | ❌ Abandonnée (cf. `docs/lab_journal.md`) |
| 4 | Suivi d'objets (Centroid Tracker + Color Re-ID) | ✅ |
| 5 | Reconnaissance faciale (FaceNet512/DeepFace) | ✅ |
| 6 | Architecture Client/Serveur (FastAPI + SQLite) | ✅ |
| 7 | MFA adaptatif (Trust Score, Liveness, empreinte) | ✅ |
| 8 | Contrôle IoT (porte, empreinte, éclairage) | ✅ (mode mock — `IOT_ENABLED=False` par défaut) |
| 9 | Multi-caméras + dashboard Electron | ✅ |
| 10 | Auth dashboard (appairage PIN + token Bearer) | ✅ |
| — | Alertes WhatsApp à distance | ⏳ Prévu, non implémenté |
| — | Table `audit_logs` dédiée (au-delà de `event_logs`) | ⏳ Prévu, non implémenté |

## Historique d'Implémentation

Voir `docs/lab_journal.md` pour le détail narratif des Phases 0 à 12, et
`erreur.md` pour le registre des bugs corrigés au fil du projet.

**Résumé Phase 7-10 (non détaillé dans le journal original)** : l'architecture a
évolué de l'API monolithique v6 vers un serveur v7 complet : `core/trust_score.py`
introduit la machine à états MFA (Présence 20% → Match facial 60% → Liveness 85% →
Empreinte 100%), `core/liveness_detector.py` implémente le challenge actif
sourire/clignement (MediaPipe), `core/iot_controller.py` pilote les actionneurs
(mode mock tant qu'`IOT_ENABLED=False`), et `core/camera_manager.py` généralise le
pipeline à plusieurs caméras simultanées avec CRUD complet (`/cameras`). Un système
d'appairage PIN + token Bearer a remplacé l'accès API ouvert, et le CORS a été
restreint aux origines légitimes du dashboard.
