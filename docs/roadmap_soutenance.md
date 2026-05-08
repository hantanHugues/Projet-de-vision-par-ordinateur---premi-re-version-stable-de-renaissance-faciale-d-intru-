# Roadmap et Architecture - Projet de Reconnaissance Faciale

Ce document trace la transition entre la phase de Preuve de Concept (POC) et la phase d'Industrialisation du projet, avec les justifications techniques pour la soutenance du mémoire.

## 1. Bilan du POC : Les fondations validées (À conserver)
Le cœur de l'Intelligence Artificielle est opérationnel et repose sur des standards industriels :
* **Détection spatiale :** Utilisation de **YOLOv8**, l'état de l'art pour capturer précisément la position des individus en temps réel.
* **Extraction Biométrique :** Utilisation de **DeepFace (modèle VGG-Face / Facenet512)** pour générer des *embeddings* (vecteurs à 512 dimensions) invariants aux changements mineurs.
* **Optimisation CPU :** Implémentation d'un **Centroid Tracker** mathématique qui attribue des IDs temporaires spatiaux, évitant de faire tourner le lourd réseau de neurones à chaque frame.

## 2. Résolution des Instabilités (Fix "Intrus A" -> "Intrus F")
### [MISE À JOUR EXPÉRIMENTALE] : L'Étalonnage du "Threshold" (Soutenance)
Lors de nos essais empiriques de robustesse avec la webcam, nous avons été confrontés à un **Dilemême de Trade-off (Faux Positifs vs Faux Négatifs)**, essentiel à documenter dans le mémoire :
1. **Test à 0.35 (Très strict) :** Génère trop de Faux Négatifs. L'IA perd l'identité à la moindre inclinaison de la tête.
2. **Test à 0.60 (Trop laxiste) :** Génère un Faux Positif grave. Il ne parvient plus à différencier deux visages aux traits similaires.
3. **Calibrage industriel retenu (0.23 sur Facenet512) :** Ce seuil métrique hyper-strict a été imposé pour répondre aux exigences d'une "Serrure Électronique". Il garantit la non-usurpation d'identité avec la méthode multi-embeddings (jusqu'à 30 vues stockées par personne).

### [NOTE D'INGÉNIERIE] : Le Protocole d'Accès Temporisé avec Apprentissage Continu
Le défi des caméras périmétriques (portail extérieur) réside dans la furtivité des intrus par rapport à un usager légitime.
L'opérateur a défini une logique d'Access Control industrielle imparable :
1.  **Le VIP coopère :** Les usagers légitimes s'exposent à la caméra pendant environ 1 seconde pour déverrouiller le portail. Durant cetête seconde, l'IA capture plusieurs clichés pour s'assurer du Match VIP.
2.  **Apprentissage Continu (Continuous Learning) :** Pour empêcher un intrus de tromper le système en changeant de masque très vite (sans perdre sa bounding box spatiale), le système re-vérifie l'identité toutes les 0.8 secondes. Si le visage a drastiquement muté, l'IA révoque l'accès et le reclasse en Intrus. Si c'est le même, l'IA enrichit la base SQLite de ce nouvel angle de visage.
3.  **L'Intrus furtif (Fuite) :** Si à un humain disparaît du champ AVANT la fin de la 1ère seconde d'analyse, l'IA déclenche une **ALERTE DE FUITE**.

## 3. Architecture Phase 6 : Industrialisation Client-Serveur (API FastAPI)
Pour passer d'un simple script local à une véritable application de vidéosurveillance d'entreprise (Smart Home) :

### A. Serveur Web : FastAPI (Séparation Cerveau / Caméra)
* **Problème Initial :** La boucle infinie `cv2.imshow()` sur `main.py` obligeait l'ordinateur captant l'image à calculer le lourd réseau de neurones en cascade (YOLO + MediaPipe + Facenet512). Cela entraînait d'énormes chutes de FPS pour la restitution vidéo en temps réel sur la machine de bord (ex: un Raspberry Pi modeste).
* **Solution d'Ingénierie :** L'intelligence a été isolée dans un serveur central **FastAPI** asynchrone (`api.py`). La caméra lointaine (`client_camera.py`) se contente d'allumer son objectif, de compresser la photo en JPG très léger, et de l'envoyer au serveur géant. L'API reçoit, calcule et répond instantanément en format texte JSON avec les coordonnées (x,y,w,h) et le nom reconnu.
* **Bénéfice Soutenance :** C'est le design exact d'une architecture Cloud/Edge Computing. La machine "Caméra" regagne instantanément une fluidité réseau parfaite, tandis que le "Cerveau" central absorbe la puissance mathématique brute en isolation.

### B. Base de Données SQL Locale : SQLite (Persistance)
L'historique des alertes Intrusion, des VIP entrants, et de la géométrie de leurs visages est persisté rigoureusement dans une base de données relationnelle légère (SQLite) qui évite les fuites de corromption liées aux simples fichiers textes/JSON.

### C. Fiabilisation du Réseau Inférentiel (Correction des doubles détections)
L'expérimentation a rapidement mis en lumière deux problèmes critiques d'intégration :
1. **L'Asynchronicité du flux Vidéo :** L'ancien client caméra attendait passivement le retour JSON avant de changer son image, figeant la vidéo locale au même rythme que l'IA centrale. La solution industrielle apportée fut de développer un script Client avec **Multithreading** embarqué : Un thread s'occupe  à l'infini de capturer et d'afficher le flux vidéo  30 FPS (cv2.imshow()), pendant qu'un second thread gère les requêtes HTTP POST en arrière-plan sans pénaliser la mécanique locale.
2. **Intersection over Union (IoU) & Bounding Boxes :** YOLOv8, dans sa structure brute, a tendance  envoyer plusieurs rectangles distincts pour une seule personne (ex: corps entier vs tête seule). Cela polluait l'analyse DeepFace. Cetête redondance a été supprimée en configurant un paramètre iou=0.35 (Forçant YOLO  fusionner les objets qui se superposent spatialement).
3. **Le Paradoxe d'Anomalie Spatiale :** Une règle originelle interdisait  à un humain (ex: "Ash") d'exister dans la base s'il était déjà présent sur l'écran dans une autre Bounding Box (Anti-Clonage). Cetête logique de "Patch Anti-Spatial" a t un échec car les algorithmes se lissaient : YOLO créait un carré rouge sur le même visage de "Ash", et l'IA croyait à  un "Intrus" qu'elle archivait en mémoire forte (SQLite). Cetête règle a été radiée, et la base de données SQLite a dû être purgée pour repartir sur un cerveau neuronal propre. 


## 4. [ARCHIVE & ÉVOLUTION - 10 Avril] : De la Rigidité à la Fiabilité Industrielle
Une grande partie du projet a consisté à analyser et surmonter nos propres impasses architecturales survenues lors du développement. Nous avons explicitement conservé une trace de ces erreurs pour prouver notre capacité d'adaptation et les exigences réelles du terrain :

### A. Le Piège de la Tolérance Mathématique (Threshold)
* **L'Erreur Initiale (Archive) :** Lors des premières phases, par peur de l'usurpation (Spoofing) et voulant un système "parfait", la tolérance cosinus de *Facenet512* avait été fixée à un seuil expérimental extrêmement strict (`0.20 - 0.23`). 
* **La Conséquence :** L'IA exigeait les conditions exactes de la photo d'origine (même lumière crue, même angle au pixel près), obligeant l'utilisateur à rester parfaitement immobile face à la caméra. Une simple rotation de tête de 5 degrés transformait la personne légitime en Intrus inconnu.
* **La Solution Définitive :** L'ingénierie moderne demande de la souplesse. Le seuil a été remonté à une norme industrielle plus équilibrée (`0.35`). Le système tolère donc parfaitement les changements de luminosité, la distance et les inclinaisons naturelles du visage tout en repoussant les anomalies réelles. Le verrouillage sécuritaire est désormais assuré par un Endpoint `/enroll` dédié, remplaçant un auto-apprentissage hasardeux.

### B. Le "Color Re-ID" (Tracking Continu malgré les occlusions)
* **L'Erreur Initiale (Archive) :** Notre module de Tracking de base (`CentroidTracker`) utilisait uniquement une règle de distance (`150 pixels`). Si une personne s'absentait de la caméra 1 seconde et réapparaissait de l'autre côté de la pièce, elle était considérée comme un clone intrus, obligeant le système à relancer tout le coûteux réseau DeepFace pour la ré-identifier.
* **La Solution Apportée :** Plutôt que de lancer un second modèle Deep Learning, une méthode colorimétrique extrêmement légère a été codée : l'Histogramme de Couleurs HSV (`cv2.calcHist`). La signature vestimentaire de chaque personne est encodée. Même si la personne disparaît derrière un mur, le Tracker utilise son vêtement (match > 85%) pour lui redonner immédiatement sa bonne identité sans réveiller l'IA faciale.
