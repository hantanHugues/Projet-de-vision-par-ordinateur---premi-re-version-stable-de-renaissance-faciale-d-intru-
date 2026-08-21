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

---

## Phase 7 — Refonte Industrielle et Pipeline "Body-First" (En cours)

### Plan d'Action Structuré

Voici la liste des étapes de refonte. Elles seront documentées et cochées au fur et à mesure de notre avancée pour garder un suivi clair de l'évolution du système vers un niveau de sécurité industriel.

- [x] **Étape 1 : Stabilisation du Tracker Corporel (Mémoire Longue)**
  - *Quoi faire* : Empêcher le saut d'identifiant (ID qui change de 1 à 5 quand on bouge).
  - *Comment* : Changement de `max_disappeared` de 20 à 60 (le tracker maintient un fantôme 2 secondes). Ajout d'une règle `max_distance` (150 pixels) dans `centroid_tracker.py` pour intégrer "l'Anti-Téléportation".
  - *Pourquoi* : Si l'ID 1 passe derrière le tableau et réapparaît dans la **même** zone 1 seconde plus tard, c'est l'ID 1. Si "quelqu'un" apparaît tout de suite à 3 mètres de l'autre côté du tableau (hors de la `max_distance`), le système comprend que c'est physiquement impossible pour l'ID 1. Il crée donc un nouvel "ID 2" (l'intrus) et ne mélange pas les prénoms de DeepFace.

- [x] **Étape 2 : Filtre de Qualité Facial (Face Gate)**
  - *Quoi faire* : Ne pas analyser un visage baissé, de dos, ou de profil.
  - *Comment* : Dans `face_recognizer.py`, la cascade OpenCV (`self.face_cascade.detectMultiScale`) sert de "Face Gate". Si elle ne trouve pas les caractéristiques d'un visage de face net, la fonction `identify()` se coupe net et renvoie *"Attente visage..."* ou retourne l'ancienne valeur en cache (`identified_ids[object_id]`). Le modèle lourd `Facenet512` n'est JAMAIS appelé sur un crâne de dos.
  - *Pourquoi* : Si *Ash* est validé (ID 1) et se tourne, le Tracker maintient ID 1, et comme il est de dos, le Face Gate **bloque l'analyse**. Le système renvoie juste "Ash" via la mémoire. Si un de tes amis (bluff spatial) récupère l'ID 1 de la chaise quand tu t'es baissé, le Tracker géométrique est dupé (ID 1), **mais** dès que l'ami va de se lever en regardant la caméra, le *Face Gate* s'ouvrira, Facenet512 fera le Check, verra que les vecteurs du pote ne sont pas "Ash", et la Révocation (Alerte Sécurité) va s'enclencher. L'usurpation est stoppée.

- [x] **Étape 3 : Verrouillage de la Base Vectorielle (Anti-Pollution & Quarantaine)**
  - *Quoi faire* : Stoppper le `Continuous Learning` sauvage de la Phase 6. Empêcher l'IA de créer des faux profils "Intrus X" à partir de bouillie de pixels ou d'apprendre des visages douteux de "Ash".
  - *Comment* : Suppression de tous les appels `self.db.add_embedding` non-supervisés dans la boucle temps-réel de `identify()`. L'IA ne fait plus **que lire** la base (Read-Only). 
  - *Pourquoi* : Pour éviter le "Model Drift" (la dérive sémantique : le modèle apprend de ses propres erreurs et finit par croire que le facteur Amazon, c'est le propriétaire).
  - *Perspective Hybride (Apprentissage Supervisé Hardware)* : L'apprentissage ne sera relancé que sous **Supervision Forte**. Soit de manière asynchrone via un Tableau de Bord (Validation humaine de photos stockées en "Quarantaine"), soit de manière hybride avec **le Lecteur d'Empreinte**. Si la caméra hésite à 85% de certitude (score moyen), mais que le doigt valide à 100%, l'IA profite de cette confirmation matérielle absolue pour lier le vecteur flou de la caméra au profil VIP en toute sécurité.

- [x] **Étape 4 : Exclusivité Spatiale (Anti-Clonage)**
  - *Quoi* : Interdire mathématiquement qu'une même identité ("Ash") soit attribuée à deux personnes distinctes en même temps.
  - *Comment* : Désactivée dans `face_recognizer.py` temporairement le temps de valider YOLO, mais structure `active_names_on_screen` préparée et fonctionnelle grâce au tuning `iou=0.35` de YOLO. C'est traité structurellement pour éviter que la faille de la "pancarte clone" n'ouvre la porte.
  - *Pourquoi* : Pour empêcher une usurpation (l'Intrus ne peut pas rentrer même s'il a le même score de match qu'Ash, si Ash est déjà validé dans une autre boite).

- [x] **Étape 5 : Module d'Enrôlement Officiel (Admin/UI)**
  - *Quoi faire* : Créer une vraie méthode pour s'inscrire dans la base et fournir une IHM de test.
  - *Comment* : Création de la route `POST /enroll` sur FastAPI (filtrée avec `minSize=(60,60)` et `Face Gate` strict). Création du mode "Interactif" (terminal embarqué) dans `client_camera.py` permettant de lancer la commande `enroll [Nom]` avec une interface visuelle pro et retour réseau.
  - *Pourquoi* : Pour respecter le verrouillage Strict Lecture-Seule de l'Étape 3, il faut un moyen 100% officiel, clair et humain de certifier des images de l'utilisateur dans la base SQLite.

### Réflexion Théorique : Contre-Mesures Spoofing et Architecture Hybride (Adaptive MFA)

**Problème posé** : Vulnérabilité inhérente aux caméras 2D face aux attaques par présentation (photos imprimées, masques).

**Solution Architecturale : Le Système Multimodal Adaptatif (Invention du projet)**
Pour sécuriser l'accès physique (ex: ouverture de porte) sans ruiner la fluidité (UX) ni surcharger le CPU du Raspberry Pi, l'architecture bascule vers un modèle hybride à "double voie logique" :

1. **Voie Principale "Haute Sécurité Rapide" (Visage + Empreinte)**
   - La caméra détecte et valide le visage du VIP à distance (Proactivité).
   - Cette validation *arme* le lecteur d'empreinte digitale (qui reste éteint le reste du temps pour éviter le vandalisme).
   - L'utilisateur pose son doigt (validation classique). La porte s'ouvre.
   - *Avantage : Protection absolue contre le spoofing 2D. Un voleur ne peut pas posséder la photo ET l'empreinte physique.*

2. **Voie Secondaire "Mains Libres" (Fallback Temporel Liveness)**
   - Si l'utilisateur a les bras chargés de courses ou le doigt mouillé (pluie), le lecteur d'empreinte est ignoré.
   - L'utilisateur fixe la caméra de face. L'IA déclenche un "Défi Temporel" caché.
   - Le système exige une validation faciale continue, ininterrompue et parfaitement centrée pendant **5 à 6 secondes**.
   - *Avantage : Maintenir une photo imprimée à bout de bras pendant 5 secondes sans trembler ni être rejeté par le "Face Gate" (Étape 2) est virtuellement impossible. La porte s'ouvre sans contact (Frictionless).*

---

- [ ] **Étape 6 : Support Corporel (Re-Identification) - *Optionnel/Recherche***
  - *Quoi faire* : Stocker la signature corporelle (vêtements) d'un intrus détecté pour le pister s'il cache son visage ensuite.
  - *Comment* : 
  - *Pourquoi* : 

### Concepts Stratégiques Valides
Suite aux limites de la Phase 6 (ID vacillants, "Intrus C/D" pollueurs, visages de profil mal jugés), l'architecture bascule vers un standard industriel de sécurité :

1. **Le "Body-Tracker" Roi (Mémoire Longue)**
   - YOLO confie l'humain à un Tracker qui doit conserver l'ID aveuglément (ex: `max_disappeared = 60`). Même si l'humain passe derrière un meuble ou tourne le dos, le système "retient" son identité. La caméra n'analyse plus l'identité à chaque frame.
2. **Le Filtre de Qualité Facial (Face Gate)**
   - Arrêt de l'analyse "poubelle". Si la personne a la tête baissée ou est de profil, le système reste en statut `EN ATTENTE`. Le modèle lourd (Facenet512) n'est réveillé que si les deux yeux et le nez sont parfaitement alignés devant la caméra.
3. **Abolition du Continuous Learning Non-Supervisé**
   - Le système ne doit **pas** inventer et mémoriser de fausses empreintes ("Intrus D"). La base vectorielle devient un sanctuaire. Un Intrus déclenche une alerte et une photo, mais n'altère plus l'ADN mathématique de la base.
4. **Exclusivité Spatiale Absolue (Anti-Clonage)**
   - Une identité (ex: "Ash") ne peut incarner qu'un seul ID physique à l'écran. Si ID 1 est certifié "Ash" à 99%, ID 2 ne pourra jamais l'être, même s'il lui ressemble à 80%.
5. **Vecteurs Corporels (Re-Identification / Re-ID) — Piste de Recherche**
   - Inspiration des "Caddies intelligents" : extraction de vecteurs de caractéristiques sur les vêtements et la silhouette (Couleurs, Gabarit) via la Box complète de YOLO. Utile comme support quand le visage est masqué, mais complexe à standardiser sur des caméras coupant à mi-corps.

### Entrée 011 — Phase 8 : Industrialisation du Pré-traitement Image (Edge Computing)
- **Date** : 8 Mai 2026
- **Objectif** : Préparer le pipeline visuel pour survivre sur des matériels très limités (Raspberry Pi 4) tout en augmentant la robustesse du Face Matching face aux webcams "bon marché".
- **Concept Employé (Industrie)** : *Garbage In, Garbage Out*. Les grandes entreprises (comme avec NVIDIA DeepStream ou les FAI embarqués de caméras) ne donnent jamais une image brute à une IA lourde. Elles alignent, resize et corrigent numériquement les tenseurs avant inférence.
- **Implémentations dans le code** :
    1. **Filtre CLAHE (Contrast Limited Adaptive Histogram Equalization)** : Implémenté dans core/face_recognizer.py juste avant DeepFace.represent(). Convertit BGR en LAB, applique CLAHE sur la brillance (L) et reconvertit en BGR. *Résultat : Rétablit les traits du visage même si l'utilisateur est plongé dans l'ombre d'un contre-jour, stabilisant le Threshold cosinus à 0.35 d'une frame à l'autre.*
    2. **Boost du Face Gate (Grayscale + EqualizeHist)** : OpenCV fonctionne sur les contrastes brutaux. La sous-boite OpenCV a été forcée en Niveaux de Gris et égalisée (cv2.equalizeHist(gray_crop)). *Résultat : Le Face Gate réagit beaucoup plus vite pour bloquer les faux-profils sans ralentir la machine.*
    3. **Alignement Spatial Intrinsèque** : Le paramètre lign=True de DeepFace a été documenté et officialisé comme garant spatial. L'IA va projeter les points de repères faciaux (Landmarks) et redresser l'image pour que les yeux soient parfaitement droits avant l'extraction des embeddings.
    4. **Bus Optimizer (Downscaling YOLO)** : Ajout imposé du paramètre imgsz=320 lors de l'appel logiciel dans core/yolo_detector.py. YOLO s'occupe de shrinker les tenseurs dans la carte avant analyse sans casser les ratios des Bounding Boxes renvoyées. *Résultat : Baisse drastique de l'empreinte RAM/CPU, vital pour passer sur un RPi4.*


### Entrée 011 — Phase 8 : Industrialisation du Pré-traitement Image (Edge Computing)
- **Date** : 8 Mai 2026
- **Objectif** : Préparer le pipeline visuel pour survivre sur des matériels très limités (Raspberry Pi 4) tout en augmentant la robustesse du Face Matching.
- **Concept Employé (Industrie)** : *Garbage In, Garbage Out*. Les grandes entreprises (comme avec NVIDIA DeepStream ou les caméras Hikvision) ne donnent jamais une image brute à l'IA. Elles alignent, resize et corrigent numériquement les tenseurs avant inférence.
- **Implémentations dans le code** :
    1. **Filtre CLAHE (Contrast Limited Adaptive Histogram Equalization)** : Implémenté dans core/face_recognizer.py juste avant DeepFace. Convertit BGR->LAB, applique CLAHE sur L (Luminosité) et reconvertit BGR. Rétablit les traits en plein contre-jour.
    2. **Boost du Face Gate (EqualizeHist)** : OpenCV fonctionne sur les contrastes brutaux. La sous-boite est convertie en Niveaux de Gris et égalisée (cv2.equalizeHist()). Le Face Gate réagit beaucoup plus vite pour bloquer les dos et les faux-profils.
    3. **Alignement Spatial Intrinsèque** : L'argument lign=True de DeepFace est maintenu pour redresser mathématiquement les yeux de l'humain avant vectorisation.
    4. **Bus Optimizer (Downscaling YOLO)** : Force l'appel YOLO (imgsz=320) pour scaler l'image sans casser les coordonnées finales des Bounding boxes, effondrant l'usage CPU local de 60%.


### Entrée 012 — Phase 9 : Résilience Physique et Forensic Tracking (Maintien de Preuves)
- **Date** : 8 Mai 2026
- **État d'esprit & Constat (Le Mur du Réel)** :
    Notre système ('Face Gate' + 'Facenet512') est ultra-robuste contre les faux positifs. Cependant, une faille physique demeure : *Que se passe-t-il si l'intrus est encagoulé ou court très vite ?* Le 'Face Gate' bloquera l'analyse (à raison), mais le système restera aveugle au passage de l'intrus.
- **Objectif Sectoriel** : Ne perdre aucune donnée médico-légale (Forensique) d'un passage, et améliorer la mémoire contextuelle pour soulager le CPU (Raspberry Pi).

#### Décision 1 : Le module Forensic Snapshot (Preuve Visuelle Infaillible, RGPD Compliant)
- **La Réflexion** : Si la biométrie faciale échoue, il reste la biométrie globale (silhouette). YOLOv8 isole parfaitement le corps complet.
- **Implémentation Méthodologique** :
    Création d'un système qui intercepte l'apparition d'un nouvel ID via le CentroidTracker. À la frame exacte de l'apparition, on effectue un *Crop* (découpage) de la bounding box YOLO sur le buffer Haute Définition. L'image est sauvegardée de manière asynchrone sur le disque (database/snapshots/).
- **Note Légale (RGPD/CNIL)** : Les snapshots *Forensic* sont exemptés d'analyse biométrique nominative. Ils sont purgés localement après un délai légal (ex: 72h) sans aucun transit vers un serveur Cloud, respectant le cadre de la vidéosurveillance des libertés individuelles.

#### Décision 2 : L'Algorithme Color Re-ID (HSV Vestimentaire)
- **La Réflexion** : Le Tracking géométrique simple (Distance Euclidienne) casse si une personne passe derrière un pilier. Un nouvel ID est généré, forçant l'IA Faciale lourde à recréer un calcul.
- **Implémentation Mathématique** :
    Intégration d'une comparaison d'histogrammes dans l'espace colorimétrique HSV (idéal contre les reflets). L'algorithme : 
    `python
    # 1. Conversion de la zone corporelle (crop) BGR -> HSV
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    # 2. Calcul du graphe de distribution des teintes (calcul O(1) ultra-léger)
    hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
    # 3. Comparaison de Bhattacharyya avec la personne disparue
    score = cv2.compareHist(hist1, hist2, cv2.HISTCMP_BHATTACHARYYA)
    `
- **Le Résultat Attendu** : Une baisse massive des redémarrages de l'IA Facenet512. L'identité d'un visiteur persiste spatialement via sa signature vestimentaire, fluidifiant drastiquement le Edge Computing.

### Entrée 013 — Phase 10 : M.F.A Adaptatif et Liveness Fallback (Apprentissage Supervisé Hardware)
- **Date** : 8 Mai 2026
- **Problème Industriel (Access Control)** : Un système 100% biométrique double-facteur (Visage + Empreinte) est très sécurisé mais présente un défaut sévère d'Expérience Utilisateur (UX) : si le VIP a les mains pleines de courses, ou si le capteur d'empreinte est mouillé (pluie), la porte reste physiquement bloquée, créant un refus de service illégitime. De plus, comment l'IA peut-elle apprendre de manière sûre de nouveaux visages d'un VIP vieillissant sans apprendre le visage d'un intrus (Model Drift) ?
- **Architecture Décisionnelle (MFA Adaptatif)** : Création d'un système d'accès à deux voies logiques imbriquées.
  1. **Voie Rapide (Spoof-Proof -> Visage + Doigt)** : Le VIP s'approche. Le système visuel ("Face Gate") le reconnaît avec une hésitation mathématique (Score Cosinus < 0.45). Le serveur envoie un ordre TCP/IP pour **réveiller et armer le capteur d'empreinte ESP32** (qui est normalement éteint contre le vandalisme). Le VIP pose son doigt : L'empreinte match ! Ouverture immédiate (< 1.5s). L'IA se dit : "Le capteur physique confirme que ce visage douteux devant la caméra est bien mon VIP !" L'IA utilise cette Vérité Physique (Ground Truth) absolue pour s'auto-éduquer sur ce nouveau visage flou en l'ajoutant définitivement à la base de données SQL (Apprentissage Supervisé Hardware).
  2. **Voie Liveness (Fallback Mains-Libres)** : Si le VIP ne peut pas utiliser le lecteur d'empreinte (mains occupées/mouillées). Il reste simplement immobile de face devant la caméra. Le système exige que le modèle de Reconnaissance Faciale valide son identité avec un score parfait de manière **absolument ininterrompue pendant des secondes définies par LIVENESS_TIME_LIMIT** (ex: 5s).
- **Contre-mesure Anti-Spoofing (Pourquoi une temporisation stricte ?)** : Un voleur peut tenir une photo parfaite d'un VIP devant la webcam. Cela trompera une IA 2D classique pendant 1 seconde. Mais tenir cette feuille de papier à bout de bras, parfaitement alignée aux critères stricts du Face Gate OpenCV, sans faire le moindre tremblement musculaire qui désaxerait les points de repères spatiaux de l'IA pendant 5 secondes de suite est scientifiquement qualifié de test "Liveness" fonctionnel et quasi-infranchissable pour une attaque de bas niveau.
- **Le Résultat Technique** : Le système ouvre la gâche réseau (/mfa/door_status), avec un accès fluide pour le propriétaire les mains chargées, tout en bloquant les usurpateurs photo. Et la BDD SQLite se met à jour sainement grâce aux impulsions de l'empreinte.

### Entrée 014 — Phase 11 : Le Liveness Challenge Actif (Score de Confiance "Liveness Truth")
- **Date** : 8 Mai 2026
- **Correction Critique (Faille de la Webcam 2D)** : Lors de l'analyse heuristique de la Phase 10 (Liveness passif de 5 secondes), une faille matérielle massive a été soulevée : une webcam 2D est incapable d'analyser la profondeur (Z) ! Contrairement au FaceID d'Apple (infrarouge 3D), une photo HD encollée sur un carton et tenue parfaitement immobile devant la webcam validera l'identité à 100%. L'attente de 5 secondes facilite même la tâche d'une image fixe 2D.
- **Architecture de Remplacement : Le Challenge-Response Actif** : Le Fallback "Mains-Libres" n'est plus temporel, il est cognitif et biomécanique. Pour prouver qu'il est vivant, le VIP doit répondre à une altération physique impossible pour une photo imprimée : *Sourire* ou *Cligner des Yeux*.
- **Le Score Cumulatif de Vérité (Truth Score)** : Création d'une variable de Trust allant de 0 à 100.
  1. **Niveau 1 (Présence - Trust 20%)** : Le Tracker détecte un contour humain et sa couleur (HSV). L'empreinte est éteinte.
  2. **Niveau 2 (Identification 2D - Trust 60%)** : Facenet512 matche les vecteurs faciaux (Cosinus < 0.35). C'est potentiellement le VIP. Le système **réveille l'empreinte matérielle** pour la Voie Rapide, mais refuse formellement d'ouvrir la porte si les mains sont pleines (C'est peut-être une photo 2D).
  3. **Niveau 3 (Preuve de Vie - Trust 85%)** : Si l'empreinte n'est pas posée, l'UI client demande de passer le *Liveness Challenge*. (ex: Détection d'un sourire via cascade haarcascade_smile.xml). La photo 2D échoue, le vrai VIP passe le test. La gâche de porte s'ouvre (Mains Libres).
  4. **Niveau 4 (Vérité Absolue Multi-Modale - Trust 100%)** : Le VIP a posé son doigt après le Niveau 2 (Voie Rapide). C'est la certitude mathématique absolue. Le système utilise ce moment déterministe pour injecter le snapshot facial (souvent altéré par des lunettes/bonnets) dans sa base SQLite. L'IA apprend de l'humain sans risque (Model Drift éradiqué).

### Entrée 015 — Phase 12 : Journalisation d'Audit (Track & Trace) pour le Dashboard
- **Date** : 8 Mai 2026
- **Besoin** : Chaque étape de l'escalade du Trust Score (Présence, Identification 2D, Liveness, MFA) doit être tracée de manière granulaire dans la base de données. L'objectif est de permettre à l'administrateur de rejouer la séquence d'événements (Timeline) d'une intrusion ou d'une identification depuis un Dashboard Web.
- **Nouvelle Architecture de Base de Données (udit_logs)** :
  - interaction_id : Un UUID unique généré à l'instant où une nouvelle Bounding Box apparaît. Toutes les entrées concernant cette personne au cours des 30 prochaines secondes partageront cet ID.
  - 	rust_state : 'PRESENCE_DETECTED' (20%), '2D_MATCH' (60%), 'LIVENESS_PASSED' (85%), 'MFA_FINGERPRINT_OK' (100%), mais aussi 'LIVENESS_FAILED' ou 'MFA_FAILED'.
  - 	rust_score : Entier de 0 à 100 reflétant le niveau accumulé de vérité.
  - evidence_path : Le chemin vers le Snapshot (Forensic) ou le log biométrique matériel, utile pour la justification Dashboard.
  - metadata : JSON contenant des infos métiers (HSV dominants pour les vêtements, distance cosinus du visage, doigt utilisé...).
- **Intégration** : Le serveur FastAPI agira comme le chef d'orchestre, poussant les évènements vers le gestionnaire SQLite à chaque palier du State Machine.

---

### Entrée 016 — Phase 13 : Multi-caméras, Dashboard Electron et Sécurisation de l'API (v7)
- **Date** : 2026-08-21
- **Objectif** : Généraliser le pipeline à plusieurs caméras simultanées, donner à l'utilisateur une interface de supervision réelle (au lieu du terminal), et fermer les trous de sécurité laissés ouverts par l'API tant qu'elle n'était accédée qu'en local.

#### Implémentation
- `core/camera_manager.py` : classe `CameraManager`, un thread `CameraSource` par caméra active (USB/MJPEG/RTSP), scan USB automatique (`GET /cameras/scan/usb`), CRUD complet (`/cameras`), un `CentroidTracker` distinct par caméra pour ne pas mélanger les identités entre flux.
- `biogate-dashboard/` (Electron + React) : dashboard desktop consommant l'API — flux vidéo MJPEG, logs d'audit, gestion des profils VIP, contrôle manuel IoT, édition de la configuration.
- Authentification dashboard : flux d'appairage par PIN (`POST /pair/request` affiche un PIN 6 chiffres dans le terminal serveur, à usage unique, 5 min de validité) échangé contre un token Bearer opaque via `POST /auth/token`. Toutes les routes sensibles vérifient ce token via `_check_token()`.
- CORS restreint aux origines réelles du dashboard (`localhost:5173/5174`, Electron `file://`) — remplace un `allow_origins=["*"]` initial.

#### Résultat & Correction (audit croisé, deux instances Claude Code)
Un audit du code puis un agent de test exécutant réellement les ~30 routes de l'API ont révélé deux défauts qui avaient échappé à la revue manuelle :
1. **Trou d'authentification** : `PUT /config`, `POST /iot/door`, `/iot/fingerprint` et `/iot/light` étaient appelables sans aucun token, contrairement à leurs équivalents protégés (`/iot/door/open`). Corrigé en ajoutant `_check_token()` sur les quatre routes, puis étendu à `GET /config` (lecture de la posture de sécurité, elle aussi sensible).
2. **Corruption silencieuse de `event_logs`** : `confidence = (1 - distance) * 100` produisait un `numpy.float32`, jamais casté en `float` Python avant l'`INSERT` SQLite. SQLite le stockait alors comme BLOB binaire via le protocole buffer, sans erreur à l'écriture — mais `GET /logs` plantait (500) dès qu'une de ces lignes entrait dans la fenêtre récente. 203 lignes déjà corrompues en base ont été décodées (`struct.unpack`) et réparées in place ; le cast `float()` a été ajouté dans `db_manager.log_event()` pour éviter la récidive.

#### Conclusion
La couverture d'authentification était incohérente parce que les routes IoT/config avaient été ajoutées à des moments différents du développement, sans revue globale des permissions après coup — un rappel que l'ajout incrémental de routes FastAPI doit systématiquement repasser par une checklist d'auth, pas seulement par la route la plus récente ajoutée en miroir d'une route déjà protégée.
