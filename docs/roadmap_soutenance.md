# Roadmap et Architecture - Projet de Reconnaissance Faciale

Ce document trace la transition entre la phase de Preuve de Concept (POC) et la phase d'Industrialisation du projet, avec les justifications techniques pour la soutenance du mémoire.

## 1. Bilan du POC : Les fondations validées (À conserver)
Le cœur de l'Intelligence Artificielle est opérationnel et repose sur des standards industriels :
* **Détection spatiale :** Utilisation de **YOLOv8**, l'état de l'art pour capturer précisément la position des individus en temps réel.
* **Extraction Biométrique :** Utilisation de **DeepFace (modèle VGG-Face / Facenet512)** pour générer des *embeddings* (vecteurs à 512 dimensions) invariants aux changements mineurs.
* **Optimisation CPU :** Implémentation d'un **Centroid Tracker** mathématique qui attribue des IDs temporaires spatiaux, évitant de faire tourner le lourd réseau de neurones à chaque frame.

## 2. Résolution des Instabilités (Fix "Intrus A" -> "Intrus F")
### [MISE À JOUR EXPÉRIMENTALE] : L'Étalonnage du "Threshold" (Soutenance)
Lors de nos essais empiriques de robustesse avec la webcam, nous avons été confrontés à un **Dilemme de Trade-off (Faux Positifs vs Faux Négatifs)**, essentiel à documenter dans le mémoire :
1. **Test à 0.35 (Très strict) :** Génère trop de Faux Négatifs. L'IA perd l'identité à la moindre inclinaison de la tête.
2. **Test à 0.60 (Trop laxiste) :** Génère un Faux Positif grave. Il ne parvient plus à différencier deux visages aux traits similaires.
3. **Calibrage industriel retenu (0.23 sur Facenet512) :** Ce seuil métrique hyper-strict a été imposé pour répondre aux exigences d'une "Serrure Électronique". Il garantit la non-usurpation d'identité avec la méthode multi-embeddings (jusqu'à 30 vues stockées par personne).

### [NOTE D'INGÉNIERIE] : Le Protocole d'Accès Temporisé avec Apprentissage Continu
Le défi des caméras périmétriques (portail extérieur) réside dans la furtivité des intrus par rapport à un usager légitime.
L'opérateur a défini une logique d'Access Control industrielle imparable :
1.  **Le VIP coopère :** Les usagers légitimes s'exposent à la caméra pendant environ 1 seconde pour déverrouiller le portail. Durant cette seconde, l'IA capture plusieurs clichés pour s'assurer du Match VIP.
2.  **Apprentissage Continu (Continuous Learning) :** Pour empêcher un intrus de tromper le système en changeant de masque très vite (sans perdre sa bounding box spatiale), le système re-vérifie l'identité toutes les 0.8 secondes. Si le visage a drastiquement muté, l'IA révoque l'accès et le reclasse en Intrus. Si c'est le même, l'IA enrichit la base SQLite de ce nouvel angle de visage.
3.  **L'Intrus furtif (Fuite) :** Si un humain disparaît du champ AVANT la fin de la 1ère seconde d'analyse, l'IA déclenche une **ALERTE DE FUITE**.

## 3. Architecture Phase 6 : Industrialisation Client-Serveur (API FastAPI)
Pour passer d'un simple script local à une véritable application de vidéosurveillance d'entreprise (Smart Home) :

### A. Serveur Web : FastAPI (Séparation Cerveau / Caméra)
* **Problème Initial :** La boucle infinie `cv2.imshow()` sur `main.py` obligeait l'ordinateur captant l'image à calculer le lourd réseau de neurones en cascade (YOLO + MediaPipe + Facenet512). Cela entraînait d'énormes chutes de FPS pour la restitution vidéo en temps réel sur la machine de bord (ex: un Raspberry Pi modeste).
* **Solution d'Ingénierie :** L'intelligence a été isolée dans un serveur central **FastAPI** asynchrone (`api.py`). La caméra lointaine (`client_camera.py`) se contente d'allumer son objectif, de compresser la photo en JPG très léger, et de l'envoyer au serveur géant. L'API reçoit, calcule et répond instantanément en format texte JSON avec les coordonnées (x,y,w,h) et le nom reconnu.
* **Bénéfice Soutenance :** C'est le design exact d'une architecture Cloud/Edge Computing. La machine "Caméra" regagne instantanément une fluidité réseau parfaite, tandis que le "Cerveau" central absorbe la puissance mathématique brute en isolation.

### B. Base de Données SQL Locale : SQLite (Persistance)
L'historique des alertes Intrusion, des VIP entrants, et de la géométrie de leurs visages est persisté rigoureusement dans une base de données relationnelle légère (SQLite) qui évite les fuites de corromption liées aux simples fichiers textes/JSON.

### C. Fiabilisation du R�seau Inf�rentiel (Correction des doubles d�tections)
L'exp�rimentation a rapidement mis en lumi�re deux probl�mes critiques d'int�gration :
1. **L'Asynchronicit� du flux Vid�o :** L'ancien client cam�ra attendait passivement le retour JSON avant de changer son image, figeant la vid�o locale au m�me rythme que l'IA centrale. La solution industrielle apport�e fut de d�velopper un script Client avec **Multithreading** embarqu� : Un thread s'occupe � l'infini de capturer et d'afficher le flux vid�o � 30 FPS (cv2.imshow()), pendant qu'un second thread g�re les requ�tes HTTP POST en arri�re-plan sans p�naliser la m�canique locale.
2. **Intersection over Union (IoU) & Bounding Boxes :** YOLOv8, dans sa structure brute, a tendance � envoyer plusieurs rectangles distincts pour une seule personne (ex: corps entier vs t�te seule). Cela polluait l'analyse DeepFace. Cette redondance a �t� supprim�e en configurant un param�tre iou=0.35 (For�ant YOLO � fusionner les objets qui se superposent spatialement).
3. **Le Paradoxe d'Anomalie Spatiale :** Une r�gle originelle interdisait � un humain (ex: "Ash") d'exister dans la base s'il �tait d�j� pr�sent sur l'�cran dans une autre Bounding Box (Anti-Clonage). Cette logique de "Patch Anti-Spatial" a �t� un �chec car les algorithmes se lissaient : YOLO cr�ait un carr� rouge sur le m�me visage de "Ash", et l'IA croyait � un "Intrus" qu'elle archivait en m�moire forte (SQLite). Cette r�gle a �t� radi�e, et la base de donn�es SQLite a d� �tre purg�e pour repartir sur un cerveau neuronal propre. 
