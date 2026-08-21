# BioGate — Notes de Projet (Journal de Décisions)

Fichier vivant. Chaque décision, idée, contrainte ou choix d'implémentation est noté ici
pour traçabilité et pour alimenter le mémoire.

---

## Architecture générale retenue

- **Mode de déploiement** : Edge Computing local (pas de Cloud)
- **Séparation Cerveau / Caméra** : FastAPI (`api.py`) + Client OpenCV (`client_camera.py`)
- **Base de données** : SQLite locale (3 tables : profiles, embeddings, event_logs)
- **Environnement Python** : `.venv-deepface` (Python 3.11.15) — incompatibilité numpy/cv2 sur Python 3.13

---

## Pipeline IA — Chaîne validée

```
Frame reçue
  → YOLO (conf=0.5, class=0, imgsz=320, iou=0.35) + NMS manuel (IoU > 0.30)
  → CentroidTracker (distance euclidienne + Color Re-ID HSV 16-bins, bypass si sim > 0.85)
  → Forensic Snapshot (corps complet, 1 fois par object_id, dossier database/snapshots/)
  → FaceGate (HaarCascade + grayscale + equalizeHist)
  → CLAHE LAB (correction contre-jours sur ROI visage uniquement)
  → FaceNet512 (DeepFace, align=True, enforce_detection=False, detector_backend=opencv)
  → Comparaison cosinus vs cache RAM (threshold = 0.35)
  → Machine à états (ANALYZING → FINISHED, RECHECK toutes les 0.8s)
  → log_event SQLite
```

---

## Seuils calibrés

| Paramètre | Valeur | Justification |
|---|---|---|
| YOLO confidence | 0.5 | Rejette les détections floues |
| YOLO iou (NMS interne) | 0.35 | Fusionne les boîtes qui se chevauchent beaucoup |
| NMS post-YOLO (maison) | 0.30 | Cas "tête + corps" adjacents non couverts par YOLO |
| FaceNet512 threshold | 0.35 | Équilibre Faux Positifs / Faux Négatifs (0.20 = trop strict, 0.60 = trop laxiste) |
| Color Re-ID similarity | 0.85 | Vêtement quasi-identique = même personne post-occlusion |
| ANALYSIS_TIME_LIMIT | 1.0s | Fenêtre d'identification (VIP doit se montrer dans cette fenêtre) |
| RECHECK_INTERVAL | 0.8s | Fréquence de re-vérification après identification (anti-masque) |
| max_disappeared | 60 frames | ~2s à 30fps avant d'oublier définitivement un ID |
| max_distance | 150px | Anti-téléportation (trop loin = nouvelle personne) |

---

## Décisions architecturales majeures

### Cache RAM (2026-06)
SQLite était interrogé à chaque frame (SELECT * + json.loads à 0.8s minimum).
**Décision** : charger tous les embeddings en RAM au démarrage (`_embeddings_cache`).
`reload_cache()` appelé uniquement après un `/enroll` réussi.

### FaceGate bloquait le timeout (bug corrigé 2026-06)
Si le FaceGate ne détectait pas de visage frontal, `"Attente visage..."` durait à l'infini
car le couperet de 1 seconde était après le `return`. 
**Fix** : vérification du timeout DANS la branche `len(faces) == 0`.

### NMS post-YOLO (2026-06)
Le filtre de containment original ne gérait que "boîte A dans boîte B".
Cas non couvert : deux boîtes adjacentes (haut du corps + bas du corps).
**Fix** : NMS standard par IoU (tri par confiance, suppression si IoU > 0.30).

### PoseAnalyzer entièrement retiré (2026-08)
Chargé au démarrage mais jamais appelé. Gaspillage RAM + temps startup.
**Fix** : retiré de api.py (2026-06) puis de main.py et config.py (2026-08).
`POSE_MIN_DETECTION_CONFIDENCE` / `POSE_MIN_TRACKING_CONFIDENCE` supprimés de config.py.

---

## Bloc 3 — MFA (conception finalisée)

### Décision clé — Liveness ET Empreinte sont des ALTERNATIVES, pas des additions
Le VIP a son visage reconnu (Trust Score 60%). Il doit ensuite prouver sa présence physique.
Il a DEUX options interchangeables — il choisit selon la situation :
- Option A (défaut) : poser le doigt sur le lecteur d'empreinte → Trust Score 100%
- Option B (mains occupées) : sourire OU cligner deux fois → Trust Score 85%
Une seule des deux est nécessaire. Pas les deux.

---

### Questions de design résolues

**Q1 : Niveau de confiance actuel pour la reconnaissance**
- FaceNet512 génère un vecteur 512D
- Distance cosinus = 1 - (a·b)/(|a||b|)
- Seuil : 0.35 → confiance minimum pour être reconnu = **65%**
- En conditions normales (bonne lumière, enrôlement propre) : **75-90%**
- Le score affiché = (1 - distance) × 100

**Q2 : Faux intrus sur changement d'expression — DÉCIDÉ**
Problème : RECHECK toutes les 0.8s peut reclasser un VIP comme intrus si l'expression change.
Solution retenue : **hysterèse** — N échecs consécutifs requis avant de changer d'identité.
Un seul RECHECK raté = ignoré silencieusement. Seulement après N ratés de suite = "Re-Analyse...".
Valeur de N à calibrer (proposition : 3).

**Q3 : Logique d'alerte différée — DÉCIDÉE**
Principe retenu : l'alerte WhatsApp n'est JAMAIS envoyée en temps réel.
Le système retient l'alerte et attend une "condition d'annulation" :

```
Personne inconnue détectée → classée "intrus provisoire"
        ↓
    FENÊTRE DE GRÂCE (~60 secondes)
        ↓
CAS 1 : VIP reconnu OU phase empreinte activée dans la fenêtre
    → l'événement "intrus" était le VIP avant identification
    → reclassé silencieusement, log discret, AUCUNE alerte

CAS 2 : Aucun VIP dans la fenêtre
    → Intrus confirmé
    → WhatsApp avec photo forensic
    → Alerte locale (lumière)
    → Log audit_trail
    → ZÉRO biométrie stockée (RGPD)
```

Contrainte légale : les embeddings d'intrus ne sont JAMAIS conservés en base.
Seule la photo forensic est gardée, purgée après 72h (RGPD).
Le comportement s'applique aussi aux intrus de quelques secondes / millisecondes.

**Q4 : Simulation IoT dans l'interface de test — DÉCIDÉE**
Pour développer et démontrer sans hardware branché :
- Terminal client enrichi avec commandes de simulation :
  - `fp ok`   → simule empreinte validée → route /fingerprint_result (match=true)
  - `fp fail`  → simule empreinte refusée → route /fingerprint_result (match=false)
  - `door`    → bascule état porte manuellement
- Panneau visuel dans la vidéo (coins de l'image) :
  - Coin haut-droit : état porte (vert = ouverte / rouge = verrouillée)
  - État lecteur empreinte : En veille / En attente / OK / ÉCHEC
  - Barre Trust Score sous la boîte de la personne
  - Couleur boîte : blanc=analyse, jaune=face matchée, vert=accès autorisé, rouge=intrus

---

---

## Liveness Detection — Décision architecture (2026-06-30)

### Contexte

Pour la phase MFA (état LIVENESS_PENDING), le système doit détecter que la personne
en face de la caméra est bien vivante et non une photo/masque. Le défi est anti-spoofing actif :
demander à la personne d'effectuer une action (cligner, sourire) que l'on peut mesurer.

### Options évaluées

**Option A — Code manuel (EAR/MAR sur landmarks)**
- Calculer Eye Aspect Ratio (6 points de l'œil) et Mouth Aspect Ratio (points de la bouche)
- Via MediaPipe FaceMesh legacy API (468 landmarks)
- Implémenté en v1 de liveness_detector.py
- Problème : EAR/MAR sont sensibles à l'orientation, à la luminosité, aux lunettes
- Sensibilité à calibrer manuellement par seuillage empirique

**Option B — MediaPipe FaceLandmarker + Blendshapes natifs**
- Le modèle `face_landmarker.task` génère 52 blendshapes (valeurs 0→1)
- Les blendshapes `eyeBlinkLeft`, `eyeBlinkRight`, `mouthSmileLeft`, `mouthSmileRight`
  sont calculés directement par le réseau de neurones Google (XNNPACK optimisé)
- Pas de formule EAR/MAR à écrire — les valeurs sont déjà calibrées
- Plus robuste aux variations de pose et luminosité

**Option C — DeepFace analyse d'émotion**
- DeepFace.analyze(actions=['emotion']) → détecte 'happy', 'neutral', 'surprise'…
- Latence : 500ms à 2s par frame (modèle Keras entier, pas optimisé)
- Résultat : inutilisable en temps réel (vidéo fluide = 30fps = 33ms/frame max)
- Détecte la même chose que B mais 50× plus lentement

### Décision retenue : Option B uniquement

**Raison 1 — Performance** : blendshapes XNNPACK ~5ms/frame sur CPU. DeepFace >500ms.
**Raison 2 — Redondance** : combiner B et C détecte deux fois la même chose (sourire = emotion happy).
**Raison 3 — Complexité inutile** : ajouter C n'augmente pas la sécurité, augmente la latence.

### Implémentation retenue (seuils calibrés 2026-08)

```
Modèle : models/face_landmarker.task (float16, 3.6 MB, Tasks API mediapipe 0.10.x)

Exécution : côté CLIENT (client_camera.py) à 30fps via MediaPipe local (_live system).
Scores envoyés au serveur via POST multipart (liveness_blink, liveness_smile).
Fallback serveur (5fps) si le client n'envoie pas de scores.

Challenge 1 — Clignement :
  score_blink = (eyeBlinkLeft + eyeBlinkRight) / 2
  BLINK_THRESHOLD = 0.35
  si score > 0.35 pendant ≥ 1 frame consécutive → 1 clignement comptabilisé
  BLINKS_REQUIRED = 2 clignements = SUCCESS

Challenge 2 — Sourire (avec hystérésis) :
  score_smile = (mouthSmileLeft + mouthSmileRight) / 2
  SMILE_THRESHOLD      = 0.40  (abaissé de 0.45 — pics réels ≈ 0.60-0.75)
  SMILE_EXIT_THRESHOLD = 0.25  (le timer ne se réinitialise que si on descend vraiment bas)
  SMILE_HOLD_SEC       = 1.2s  (réduit de 1.5s — compense les micro-dips à faible fps)
  si score > 0.40 pendant ≥ 1.2s en continu → SUCCESS

Les deux challenges sont évalués en parallèle à chaque frame.
Le premier à réussir détermine SUCCESS.
Timeout global = config.LIVENESS_CHALLENGE_TIMEOUT (défaut 10s).
```

### Flux complet MFA avec liveness (MFA_REQUIRED=True, LIVENESS_ENABLED=True)

```
1. VIP reconnu par FaceNet512 → state=FACE_MATCHED → score FaceNet (ex: 78%)
2. MFA requis → state=FINGERPRINT_PENDING (lecteur réveillé via IoT)
3. VIP a les mains occupées → appuie 'l' → POST /request_liveness
4. state=LIVENESS_PENDING → LivenessDetector instancié pour cet object_id
   + _live_start() côté client → MediaPipe activé localement
5. Chaque frame client :
   - client_camera.py : _live_analyze(frame) → scores mis à jour en RAM
   - POST /analyze_frame : envoie liveness_blink + liveness_smile dans le form
   - api.py : det.check_values(blink, smile) → blendshapes évalués
   - Fallback : det.check(crop) si scores absents (0.0)
6. SUCCESS → ts.liveness_success() → state=GRANTED → score=85%
   TIMEOUT  → ts.liveness_failed() → state=DENIED → score=0%
7. GRANTED → porte ouverte (IoT), lumière verte, log EVENT_LIVENESS_SUCCESS
```

---

## Configuration & Dashboard — Architecture retenue

### Principe : configuration fine depuis le dashboard, templates comme point de départ

Pas de profils rigides. L'utilisateur configure chaque paramètre individuellement.
Des templates prêts à l'emploi (Portail, Domicile, Bureau, Haute Sécurité) servent
de point de départ que l'utilisateur peut ensuite personnaliser librement.

### Routes de configuration à préparer dans api.py

```
GET  /config                    → retourne tous les paramètres actuels
PUT  /config                    → modifie un ou plusieurs paramètres
GET  /config/templates          → liste les templates disponibles
POST /config/apply_template     → charge un template (base de personnalisation)
```

### Paramètres configurables depuis le dashboard

| Paramètre | Template Portail | Template Domicile | Template Bureau | Template Haute Sécurité |
|---|---|---|---|---|
| Fenêtre de grâce alerte | 120s | 60s | 30s | 5s |
| MFA obligatoire | Non | Optionnel | Oui | Oui (toujours) |
| Alerte si intrus | Locale seulement | WhatsApp + locale | Log silencieux | WhatsApp + locale + verrouillage |
| ANALYSIS_TIME_LIMIT | 1.5s | 1.0s | 1.0s | 0.8s |
| Hysterèse RECHECK | 5 ratés | 3 ratés | 3 ratés | 1 raté |
| Purge RGPD snapshots | 72h | 72h | 24h | 12h |

---

## État d'implémentation (mis à jour 2026-06-30)

### Bloc 3 — MFA & IoT — TERMINÉ ✅
- [x] `config.py` — constantes MFA, IoT, alertes, RGPD (RECHECK_FAILURE_TOLERANCE, ALERT_GRACE_PERIOD, …)
- [x] `core/trust_score.py` — machine à états (IDLE→ANALYZING→FACE_MATCHED→FINGERPRINT_PENDING|LIVENESS_PENDING→GRANTED|DENIED) + TrustScoreManager avec callback `on_intruder_confirmed`
- [x] `core/iot_controller.py` — HTTP vers ESP32 (porte, lecteur, lumière) + mode mock (IOT_ENABLED=False)
- [x] `core/liveness_detector.py` — **v2 MediaPipe Blendshapes** (2 clignements OU sourire 1.5s via valeurs pré-calculées eyeBlinkLeft/Right et mouthSmileLeft/Right)
- [x] `models/face_landmarker.task` — modèle Google téléchargé (3.6 MB, float16, XNNPACK)
- [x] Liveness branché dans `api.py` — `_liveness_sessions` dict, analyse frame par frame en LIVENESS_PENDING, `liveness_progress` injecté dans la réponse `/analyze_frame`
- [x] Hysterèse RECHECK dans `face_recognizer.py` — `recheck_fail_count` accumulé, re-analyse seulement après N=RECHECK_FAILURE_TOLERANCE ratés consécutifs
- [x] Alerte différée dans `face_recognizer.py` — `ts.intruder_detected()` → `TrustScore._grace_expired()` → callback → WhatsApp + light alert
- [x] VIP reconnu → `trust_mgr.cancel_intruder_if_vip_nearby()` annule toutes les alertes provisoires
- [x] Routes : `/fingerprint_result`, `/liveness_result`, `/request_liveness`, `/access_status`, `/iot/door`, `/iot/fingerprint`, `/iot/light`
- [x] Réponse `/analyze_frame` enrichie : champ `trust` par objet (+ `liveness_progress`) + champ `iot` global
- [x] UI `client_camera.py` — barre IoT (porte/empreinte/lumière), Trust Score par boîte, challenge liveness guidé visuellement (instructions + compteur), 9 raccourcis clavier

### Bloc 4 — Configuration — TERMINÉ ✅
- [x] Table `system_config` SQLite — persistée entre redémarrages, upsert `ON CONFLICT DO UPDATE`
- [x] `get_effective_config()` — merge DB sur config.py, order of precedence clair
- [x] 4 templates prédéfinis : PORTAIL, DOMICILE, BUREAU, HAUTE_SECURITE
- [x] Routes : `GET /config`, `PUT /config`, `GET /config/templates`, `POST /config/apply_template`

### Bloc 5 — Logs & RGPD — TERMINÉ ✅
- [x] Table `event_logs` enrichie : `event_type` + `snapshot_path` (migration automatique via PRAGMA)
- [x] 9 types d'événements constants : VIP_ENTRY, INTRUDER_PENDING, INTRUDER_CONFIRMED, FINGERPRINT_OK, FINGERPRINT_FAIL, LIVENESS_SUCCESS, ACCESS_DENIED, FLIGHT_ALERT, DETECTION
- [x] Routes : `GET /logs`, `GET /logs/stats`, `DELETE /logs/{id}`, `DELETE /logs/purge`
- [x] `purge_old_snapshots()` supprime fichiers disque + entrées DB

### À faire — Blocs suivants
- [ ] **WhatsApp** (Twilio / GreenAPI) — appel dans `_on_intruder_confirmed` de api.py
- [ ] **Script RGPD autonome** — purge auto au démarrage du serveur + scheduler
- [ ] **Dashboard Web** (Bloc 4 frontend) :
  - Vue flux live (MJPEG ou polling /analyze_frame)
  - Tableau event_logs (utilise GET /logs)
  - Formulaire enrôlement VIP (utilise POST /enroll)
  - Panneau configuration / templates (utilise GET+PUT /config)
  - Statut IoT en temps réel (utilise GET /access_status)
- [ ] **Source MJPEG/RTSP** pour caméra BW21-CBV (Bloc 6)
- [ ] **ONNX/TFLite export** YOLOv8n pour Raspberry Pi (Bloc 7, post-soutenance)

---

## Architecture embarquée — BW21-CBV + Raspberry Pi (2026-07-13)

### Matériel envisagé

- **Ai Thinker BW21-CBV** : caméra WiFi embarquée, chip Realtek RTL8735B
  - NPU intégré 0.4 TOPS, ARM v8-M @ 500 MHz, 128 MB DDR2
  - WiFi dual-band 2.4+5 GHz, BLE 5.1
  - Encodage H.264/H.265 jusqu'à 1080p @ 45fps
  - Exemples pré-compilés Ai Thinker : YOLOv7, détection visage, reconnaissance gestes
  - SDK Arduino + SDK Realtek (modèles custom = outils propriétaires Realtek requis)

- **Raspberry Pi 4** (si disponible) : serveur IA embarqué

### Analyse des goulots d'étranglement actuels (PC seul)

```
Frame 640×480 reçue du client (~5fps réseau)
  → YOLO détection personne   : ~30-50ms   ← lourd, candidat déport BW21
  → FaceNet512 embedding      : ~100-300ms ← GOULOT PRINCIPAL
  → MediaPipe liveness        : ~5ms       ← léger, limité à 5fps réseau
```

Le vrai problème de latence = FaceNet512, pas YOLO.

### Architecture optimale identifiée (PC + BW21-CBV)

```
BW21-CBV (exemples pré-compilés, aucun outil proprio requis)
  → YOLOv7 on-device : détecte personne
  → Détection visage + crop 100×100px
  → Liveness blink/smile on-device à 30fps (si exemple Ai Thinker disponible)
  → Envoie crop via WiFi au serveur

PC serveur
  → FaceNet512 sur crop 100×100 uniquement
  → Trust Score + IoT control
  → MediaPipe liveness (fallback si non géré par BW21)
```

**Gains estimés :**
- YOLO retiré du serveur → -40ms par frame
- Image 30× plus petite envoyée → FPS réseau ×2 à ×3 (5fps → 10-15fps)
- Crop visage net et centré → FaceNet512 plus précis, score moins fluctuant
- Liveness à 30fps local → blink/smile fiables (vs 5fps actuel = clignements ratés)

### Pourquoi PAS Raspberry Pi comme serveur IA principal

FaceNet512 est trop lourd pour le RPi 4 :

| Machine | FaceNet512 par inférence |
|---------|--------------------------|
| PC (CPU) | ~100-300ms |
| Raspberry Pi 4 | ~500ms - 2s |

Mettre FaceNet512 sur RPi = **plus lent** qu'aujourd'hui.

### Scénarios classés par faisabilité

| Scénario | Faisable | Impressionnant | Notes |
|----------|----------|----------------|-------|
| PC + BW21 (crop WiFi) | ✅ Facile | ✅ | Recommandé pour soutenance |
| RPi + BW21 + MobileFaceNet | ⚠️ Travail supp. | ✅✅ | Remplacer FaceNet512 par MobileFaceNet TFLite (~100ms sur RPi) |
| RPi + BW21 + FaceNet512 | ❌ | — | Plus lent qu'aujourd'hui |

### Décision pour la soutenance

**Priorité 1** : PC + BW21-CBV en stream RTSP/MJPEG → déjà supporté par `client_camera.py` option 2.
**Priorité 2** : Si temps disponible, activer les exemples YOLO pré-compilés sur BW21 pour envoyer uniquement les crops visage.
**Post-soutenance** : Migration RPi avec MobileFaceNet (Bloc 7).

---

## Dashboard Electron — Architecture décidée (2026-07-30)

### Contexte

Le dashboard BioGate est une application **desktop Electron indépendante** dans son propre dossier
(`biogate-dashboard/`). Elle tourne sur n'importe quel PC (Windows/Mac/Linux), se connecte au
serveur BioGate via WiFi LAN, et nécessite un appairage unique pour accéder au système.

**Objectif de sécurité clé** : une tierce personne ayant installé la même application ne peut
pas voir ni contrôler un système BioGate qui n't lui appartient pas.

---

### Choix technologique : React + Vite + electron-vite

**Pourquoi PAS Next.js dans Electron :**
- Next.js est conçu pour le SSR web (rendu serveur + SEO) — inutile dans une app desktop
- Nécessite un process Node.js SSR séparé, complexifie Electron sans apport réel
- `next export` (mode statique) perd tous les avantages de Next.js
- Incompatibilités récurrentes avec le système de fichiers Electron

**Choix retenu : `electron-vite` + React 18**
- `electron-vite` est le standard moderne pour Electron (remplace `electron-webpack`)
- Vite : HMR ultra-rapide en dev, build optimisé en prod
- React Router v6 pour la navigation entre pages
- Packaging final : `electron-builder` → `.exe` Windows, `.dmg` Mac, `.AppImage` Linux
- Une seule commande : `npm run build` → installeur prêt à distribuer

---

### Structure du dossier

```
biogate-dashboard/                   ← dossier indépendant dans le projet
├── package.json
├── electron.vite.config.js
├── electron/
│   ├── main.js                      ← process principal Electron (fenêtre, menu, sécurité)
│   └── preload.js                   ← pont contextIsolation : expose API sécurisée au renderer
├── src/
│   ├── main.jsx                     ← entrée React
│   ├── App.jsx                      ← router principal
│   ├── api/
│   │   ├── client.js                ← axios configuré avec baseURL + JWT header + HTTPS
│   │   └── auth.js                  ← stockage token (electron.safeStorage), pairing flow
│   ├── pages/
│   │   ├── Setup.jsx                ← écran de premier lancement (IP + code pairing)
│   │   ├── Dashboard.jsx            ← flux live + TrustScore en temps réel
│   │   ├── Logs.jsx                 ← tableau event_logs avec filtres (GET /logs)
│   │   ├── Enroll.jsx               ← formulaire inscription VIP (POST /enroll)
│   │   └── Config.jsx               ← paramètres + templates (GET/PUT /config)
│   └── components/
│       ├── LiveFeed.jsx             ← polling /access_status toutes les 500ms
│       ├── TrustBadge.jsx           ← badge état (GRANTED/DENIED/ANALYZING...)
│       └── IotPanel.jsx             ← contrôles porte / lumière / empreinte
└── assets/
    └── biogate-logo.svg
```

---

### Mécanisme de pairing (sécurité anti-tiers)

Inspiré du modèle Philips Hue / Chromecast : le code est physiquement présent sur le serveur,
donc impossible à obtenir à distance sans accès au local.

```
PREMIER LANCEMENT de l'app
────────────────────────────
1. Écran Setup : l'utilisateur entre l'IP du serveur BioGate (ex: 192.168.1.10)
2. L'app contacte GET /pair/request
3. Le serveur génère un code PIN à 6 chiffres → affiché dans le terminal serveur
4. L'utilisateur entre ce code dans l'app
5. L'app POST /auth/token {pin: "123456", device_id: "<UUID local>"}
6. Serveur valide le PIN (valable 5 min, max 5 tentatives)
7. Serveur génère un JWT signé (HS256, expiry 30 jours) + retourne au client
8. L'app stocke {server_ip, jwt_token} via electron.safeStorage (chiffré par l'OS)

LANCEMENTS SUIVANTS
────────────────────
→ L'app lit le token stocké et se reconnecte automatiquement
→ Si token expiré → re-pairing avec nouveau code PIN
→ Si serveur change d'IP → l'utilisateur entre la nouvelle IP

SÉCURITÉ TIERS
───────────────
→ Sans le code PIN affiché sur le serveur physique = aucun accès
→ Le JWT est unique par appareil (device_id = UUID généré une fois à l'installation)
→ Le serveur peut révoquer un device_id (liste noire en mémoire)
→ Max 5 appareils appairés simultanément
```

---

### Communication sécurisée

| Couche | Solution | Détail |
|---|---|---|
| Chiffrement transport | **HTTPS** (TLS 1.3) | Certificat auto-signé OpenSSL, généré au démarrage serveur |
| Authentification | **JWT HS256** | Secret aléatoire 256 bits généré à l'installation, stocké dans `.env` |
| Stockage token client | **electron.safeStorage** | Chiffré par l'OS (DPAPI Windows, Keychain macOS) |
| Protection PIN | Rate limiting | 5 tentatives max, blacklist IP 15 min après échec |
| Expiry token | 30 jours | Re-pairing silencieux si refresh token valide |

---

### Niveau de sécurité par route FastAPI (à implémenter)

```
PUBLIC — pas de JWT requis
  GET  /health              → "serveur vivant ?" — utilisé par l'app pour tester la connexion
  POST /pair/request        → déclenche génération du code PIN côté serveur (rate-limitée)
  POST /auth/token          → valide le PIN et retourne le JWT

PROTÉGÉ JWT — header Authorization: Bearer <token> obligatoire
  POST /analyze_frame       🔴 CRITIQUE  — flux IA temps réel
  POST /enroll              🔴 CRITIQUE  — ajout de profils VIP
  GET  /logs                🔴 CRITIQUE  — données personnelles (RGPD)
  DELETE /logs/*            🔴 CRITIQUE  — suppression données
  GET  /logs/stats          🟠 ÉLEVÉ     — statistiques de sécurité
  PUT  /config              🔴 CRITIQUE  — modification des paramètres système
  GET  /config              🟠 ÉLEVÉ     — lecture configuration
  GET  /config/templates    🟡 MODÉRÉ    — lecture des templates
  POST /config/apply_template 🔴 CRITIQUE — reset de la configuration
  GET  /access_status       🟠 ÉLEVÉ     — état temps réel (IoT + Trust Scores)
  POST /fingerprint_result  🔴 CRITIQUE  — validation accès MFA
  POST /request_liveness    🔴 CRITIQUE  — déclenchement challenge
  POST /iot/*               🔴 CRITIQUE  — contrôle physique porte / lumière
```

---

### Ce qui change dans FastAPI (api.py) pour supporter le dashboard

1. **HTTPS** : lancer uvicorn avec `--ssl-keyfile` et `--ssl-certfile` (certificat auto-signé généré à l'init)
2. **Middleware JWT** : décorateur FastAPI `Security(verify_token)` sur toutes les routes protégées
3. **Nouvelles routes** :
   - `GET  /health` — retourne `{"status": "ok", "version": "7.0"}`
   - `POST /pair/request` — génère et affiche le PIN côté serveur, stocke en mémoire avec TTL 5min
   - `POST /auth/token` — valide PIN + device_id, retourne JWT signé
4. **CORS configuré** pour accepter les requêtes depuis `electron://` et `http://localhost` (dev)

---

### Flux vidéo en temps réel dans le dashboard

FastAPI expose `GET /stream` — une `StreamingResponse` MJPEG qui pousse les frames
**déjà annotées** (boîtes YOLO, identités, TrustScore) en continu.

Dans l'app Electron, une simple balise `<img>` suffit — les navigateurs/Electron gèrent
nativement le MJPEG :

```html
<img src="https://192.168.1.10/stream?token=JWT_TOKEN" />
```

Le JWT passe en query param (obligatoire pour `<img src>` qui ne peut pas envoyer de headers).
Acceptable sur LAN : le token n'est pas dans l'URL publique, uniquement sur le réseau local fermé.

FastAPI construit la frame annotée dans la route `/stream` en puisant dans la dernière frame
analysée par `/analyze_frame` (variable partagée en mémoire).

### Autres flux de données

```
Dashboard.jsx / IotPanel
  → toutes les 500ms : GET /access_status
      → met à jour état porte, lumière, empreinte, TrustScores par ID

Logs.jsx
  → toutes les 5s ou sur action : GET /logs?limit=50
      → rafraîchit le tableau des derniers événements

Alertes desktop
  → quand /access_status retourne un nouvel INTRUDER_CONFIRMED
      → electron Notification API → notification Windows/Mac native
```

### Pages et fonctionnalités complètes

| Page | Fonctionnalités |
|---|---|
| **Live** | Flux MJPEG annoté temps réel + panneau IoT (boutons porte/lumière) + TrustBadge par personne |
| **Accès** | Tableau event_logs filtrable (type, nom, date) + miniature forensic cliquable + export CSV |
| **VIP** | Upload photo ou capture webcam → POST /enroll + liste des VIP enregistrés |
| **Config** | Sélecteur de template + sliders/toggles pour chaque paramètre → PUT /config |
| **Stats** | Compteurs du jour : entrées VIP / tentatives intrus / succès liveness / taux de refus |
| **Alertes** | Notification desktop native (Electron Notification) à chaque INTRUDER_CONFIRMED |

---

### État d'implémentation Dashboard Electron

- [ ] Créer `biogate-dashboard/` avec `electron-vite` + React 18
- [ ] `electron/main.js` — fenêtre principale, contextIsolation=true, nodeIntegration=false
- [ ] `electron/preload.js` — expose uniquement `{ipc, safeStorage}` au renderer
- [ ] `src/api/auth.js` — pairing flow, stockage JWT safeStorage
- [ ] `src/api/client.js` — axios instance avec intercepteur JWT + gestion 401
- [ ] Côté FastAPI : `/health`, `/pair/request`, `/auth/token` + middleware JWT
- [ ] Côté FastAPI : HTTPS (certificat auto-signé, généré au 1er démarrage)
- [ ] `Setup.jsx` — écran de connexion / pairing
- [ ] `Dashboard.jsx` — polling /access_status, TrustBadge, IotPanel
- [ ] `Logs.jsx` — tableau paginé avec filtres
- [ ] `Enroll.jsx` — formulaire VIP avec aperçu webcam
- [ ] `Config.jsx` — paramètres + templates
