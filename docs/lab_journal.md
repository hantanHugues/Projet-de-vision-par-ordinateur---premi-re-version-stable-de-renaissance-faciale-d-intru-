# Journal de Laboratoire — SurveilleIA

> Ce document consigne chaque étape du développement du système de surveillance IA distribué.
> Chaque entrée suit le format : **Date → Hypothèse → Implémentation → Résultat → Conclusion**.

---

## Phase 0 — Fondations du Projet

### Entrée 001 — Initialisation de l'environnement
- **Date** : 2026-04-05
- **Objectif** : Mettre en place l'environnement Python, la structure du projet, et valider la capture vidéo depuis la webcam locale.
- **Hypothèse** : OpenCV peut capturer le flux de la webcam et l'afficher dans une fenêtre avec un compteur de FPS en temps réel.
#### Implémentation
- Création de la structure modulaire du projet (`core/`, `sources/`, `tests/`, `docs/`).
- Classe abstraite `VideoSource` (dans `sources/base.py`) définissant le contrat pour toutes les sources vidéo.
- Première implémentation concrète : `WebcamSource` (dans `sources/webcam.py`).
- Point d'entrée `main.py` avec factory pattern et boucle de capture.
- Configuration centralisée dans `config.py`.

#### Environnement
- **OS** : Windows
- **Python** : 3.14.0
- **Dépendances** : opencv-python 4.11.0.86, numpy >= 1.26.0

#### Résultat
- [x] L'environnement s'installe sans erreur
- [x] La boucle vidéo capture le flux avec de bonnes performances (FPS fluides)
- [x] L'architecture modulaire est validée pour accueillir l'IA.

#### Conclusion
- La fondation est saine. Le `VideoSource` abstrait parfaitement la webcam. Prêt à intégrer un modèle lourd.

---

## Phase 2 — Moteur IA de Détection (YOLOv8n)

### Entrée 002 — Intégration de Ultralytics YOLO
- **Date** : 2026-04-05
- **Objectif** : Transformer le flux vidéo brut en un flux analysé (Bounding boxes sur les humains).
- **Hypothèse** : YOLOv8 "Nano" peut traiter le flux vidéo sur le CPU de Windows en temps réel (pour la simulation du Hub).
- **Implémentation** :
    - `core/yolo_detector.py` enveloppe le modèle.
    - Seuil de confiance configuré à `0.5`, filtre restreint à la classe `0` (Personnes).
    - `main.py` mesure le temps d'inférence en `ms`.

#### Résultat
- [x] Installation de PyTorch et Ultralytics réussie.
- [x] Détection d'humain fonctionnelle (Bounding Boxes vertes, label "Humain: 0.XX").
- [x] FPS moyen mesuré : ~15.2 FPS sur CPU Windows (1800 frames en 118s).
- [x] Faille identifiée : YOLO trompé par photo 2D sur téléphone (comportement normal pour un réseau 2D).

#### Conclusion
- YOLOv8n fonctionne parfaitement comme première couche du pipeline. La faille photo 2D justifie l'ajout de MediaPipe (Phase 3) pour contrer les faux positifs.

---

## Phase 2.5 — Visual Logger

### Entrée 003 — Terminal incrusté dans la vidéo
- **Date** : 2026-04-05
- **Objectif** : Centraliser les logs système dans un terminal visible à la fois dans la console et directement incrusté en bas du flux vidéo.
- **Implémentation** : `core/logger.py` avec `VisualLogger`, mémoire tampon circulaire de 8 lignes, `numpy.vstack` pour empiler la vidéo et le panneau noir.

#### Résultat
- [x] Le logger s'affiche correctement dans la console ET dans la vidéo.
- [x] La logique anti-spam de `yolo_detector.py` ne logge que lors des changements d'état (entrée/sortie du champ).

#### Conclusion
- Outil de débogage indispensable pour la suite, particulièrement pour le déploiement headless sur Raspberry Pi.

---

## Phase 3 — Analyse Posturale (MediaPipe)

### Entrée 004 — Intégration du squelette conditionnel
- **Date** : 2026-04-05
- **Objectif** : Ajouter une couche de confirmation par analyse du squelette : si YOLO détecte un humain, MediaPipe vérifie qu'il a une vraie posture corporelle (contrer les photos 2D).
- **Hypothèse** : MediaPipe Pose peut ajouter ~20-40 ms sur le CPU pour détecter les 33 points d'articulation, et ce temps n'est dépensé QUE lorsque YOLO a trouvé >= 1 humain.
- **Implémentation** :
    - `core/pose_analyzer.py` enveloppe `mediapipe.solutions.pose.Pose`.
    - Conversion BGR -> RGB avant analyse (exigence de MediaPipe).
    - Optimisation : `flags.writeable = False` sur le buffer RGB (réduit allocations mémoire).
    - `main.py` : logique conditionnelle `if len(detections) > 0` avant d'appeler MediaPipe.
    - Affichage détaillé des temps : `YOLO: Xms | Pose: Xms | Total: Xms`.

#### Résultat
- [x] Test de détection squelettique (MediaPipe) réussi : le maillage s'affiche correctement lorsque YOLO identifie un humain.
- [x] Contre-mesure anti-2D prouvée : ignore presque systématiquement la géométrie plate d'une photo sur un téléphone.
- [x] Temps de calcul mesurés : La cascade IA pèse lourd localement (les ms s'additionnent), ce qui a justifié le besoin de l'architecture Client-Serveur séparée par la suite.

---

## Phase 4 — Suivi Visuel et Vectorisation (Tracking)

### Entrée 005 — Tracking via Centroid (ID Temporel)
- **Date** : 2026-04-05
- **Objectif** : Le système doit pouvoir suivre "Humain 1" frame après frame. Sans tracker, YOLO oublie et redécouvre la personne 30 fois par seconde, rendant toute logique d'alerte ou de reconnaissance faciale impossible (surcharge CPU garantie).
- **Implémentation** :
    - Fichier `core/centroid_tracker.py` construit (méthode de suivi ultra légère par distance Euclidienne sur les centres de gravité).
    - `max_disappeared=20` implémenté : l'IA gardera en mémoire un marcheur qui passe derrière un pilier (ou que YOLO perd) pendant 20 frames avant de libérer son ID.
- **Résultat** : Un ID unique est attribué à chaque humain. Base fonctionnelle cruciale pour la Phase 5.

---

## Phase 5 — Reconnaissance Biométrique et Access Control (DeepFace)

### Entrée 006 — Le Moteur Facenet512 et SQLite
- **Date** : 2026-04-05
- **Objectif** : Identifier formellement un humain (Ash = VIP, Inconnu = Intrus) en exploitant l'ADN facial via l'IA de DeepFace.
- **Hypothèse** : Facenet512 est beaucoup plus robuste face aux conditions lumineuses de webcams que le modèle de base VGG-Face.
- **Implémentation** :
    - Base de données `database/db_manager.py` avec `sqlite3` pour ancrer l'historique et les empreintes (Multi-Empreintes possibles par individu).
    - Fichier `core/face_recognizer.py` utilisant `DeepFace.represent()` sur les boîtes découpées.
    - Installation d'un environnement `.venv-deepface` isolé (Python 3.11) suite à des conflits de compatibilité initiaux avec les packages Tensorflow/Keras 3.

### Entrée 007 — Apprentissage Continu et Temporisation à 1-Seconde
- **Date** : 2026-04-05/06
- **Objectif** : Ne pas bloquer l'engin avec une reconnaissance à chaque frame. Sécuriser le processus pour éviter qu'un VIP qui met vite un masque ne reste validé pour toujours (Continuous Learning).
- **Implémentation** :
    - Une Machine à États a été créée pour chaque ID (`ANALYZING`, `FINISHED`).
    - L'IA donne strictement **1.0 Seconde** (`ANALYSIS_TIME_LIMIT`) à l'humain pour se scanner.
    - S'il fuit avant 1.0s, déclenchement d'alerte "Fuite" via le VisualLogger.
    - Une fois validé, le système relance un scannage d'identité (Re-Vérification) toutes les **0.8 Secondes**. Si l'identité mute, alerte déclenchée et changement en Intrus. Si elle correspond toujours, elle stocke le profil (Apprentissage Continu de la pose).

---

## Phase 6 — Industrialisation (Client-Serveur FastAPI)

### Entrée 008 — Séparation de l'Intelligence et de la Caméra
- **Date** : 2026-04-06
- **Objectif** : Résoudre la chute drastique de FPS sur les machines modestes due à l'exécution synchronisée de la cascade YOLO + DeepFace Facenet512.
- **Implémentation** :
    - Création d'un serveur `api.py` avec FastAPI pour l'inférence lourde.
    - Création d'un client distant `client_camera.py` pour envoyer des images compressées et décoder l'analyse.
    - Correction des bugs (Erreur 500) causés par la modification de la signature de `tracker.update()` en Tuple `(objects, bboxes)`. 
- **Résultat** : L'IA et la caméra sont indépendantes. Un serveur surpuissant peut encaisser les modèles mathématiques lourds, et libérer l'ordinateur/caméra local.

### Entrée 009 — Asynchronisme Client et Fiabilisation de l'IA (Dédoublonnage)
- **Date** : 2026-04-06
- **Problème** : 
    - 1) La vidéo client restait liée au lag du réseau.
    - 2) Le système croyait être encerclé ("Intrus A, B, F") quand il n'y avait qu'une personne, à cause de boîtes YOLO redondantes superposées qui se heurtaient à la sécurité "Anti-Spatial".
- **Action** :
    - **Multithreading :** Injection du module `threading` dans `client_camera.py`. L'affichage caméra OpenCV tourne de façon fluide à son propre rythme pendant que la requête `POST` s'exécute en tâche de fond.
    - **IoU YOLO :** Ajout du paramètre `iou=0.35` (Non-Maximum Suppression) dans l'inférence pour raboter les multiples rectangles trouvés sur une personne.
    - **Ablation Anti-Spatial :** Désactivation de la règle bloquant deux personnes du même nom dans une seule image pour éviter l'effet "Faux Positifs Mémorisés".
    - **Mémoire Effacée (Tabula Rasa) :** Suppression de la base SQLite `visages.db` corrompue par les faux intrus.
- **Résultat** : Un seul visage analysé = une seule identité vérifiée. L'affichage est fluide (30 FPS local, peu importe la connexion). Cerveau IA propre et opérationnel.

---

## Bilan Final

### Entrée 010 — Bilan des Expérimentations et Recalibrages
- **Date** : 2026-04-06
- **Objectif** : Documenter les choix technologiques finaux suite aux diverses impasses rencontrées lors des phases de test intensives.
- **Réglage Qualité Vidéo** : 
    - L'image de base de la webcam était trop grande ou non adaptée en formatage initial pour le réseau neuronal, exigeant une normalisation stricte (BGR/RGB) pour alimenter Facenet512 et MediaPipe sans distortion d'échelle.
- **Dédoublonnage YOLO (Tuning IoU)** :
    - *Observation* : L'algorithme renvoyait souvent 2 bounding boxes sur une même personne (ex: Corps Entier + Tête), forçant la création de multiples "Intrus" fantômes.
    - *Décision* : Réglage du seuil d'Intersection over Union (`iou=0.35`) qui agglomère strictement les rectangles qui se superposent sur la scène, réglant instantanément la duplication.
- **Modèle de Reconnaissance (Le grand saut)** :
    - *Observation* : Les premiers tests avec VGG-Face / OpenCV HaarCascades basiques montraient trop d'imprécisions face à la lumière de la webcam.
    - *Décision* : Abandon définitif des visages 2D simples au profit de l'extracteur d'ADN facial robuste **Facenet512** de Google (implémenté via le framework DeepFace), combiné à une détection HaarCascade locale juste pour le recadrage (gain de performance net).
- **Logique Temporelle & Continuous Learning (La solution Ultime)** :
    - *Observation* : Sur-solliciter l'IA à chaque image à 30 FPS tuait la machine. Garder une seule validation à vie permettait à un intrus de mettre le masque d'un VIP après ouverture.
    - *Décision* : Déploiement d'un coupe-circuit à `1 Seconde` (Temps d'analyse) + Apprentissage continu toutes les `0.8 Secondes`. Résultat: Si tu mets le masque après validation, le système réagit et te déclasse en "Intrus".
