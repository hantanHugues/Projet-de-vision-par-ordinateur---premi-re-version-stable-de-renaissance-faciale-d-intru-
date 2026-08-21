# Cahier des charges — Projet BioGate

**Thème :** Conception et implémentation d'une infrastructure de contrôle d'accès biométrique intelligente par vision artificielle et architecture Edge Computing (Le système BioGate).  
**Version :** 2.0 (Refonte Intégrale Industrielle)

---

## 1. Contexte et Problématique

La sécurité résidentielle et la gestion des accès physiques font face à des défis croissants. Les systèmes classiques (clés, alarmes simples) ne permettent pas une identification formelle et manquent souvent de preuves visuelles exploitables. De plus, les solutions commerciales actuelles (Ring, Nest) posent de sévères problèmes de **confidentialité** en envoyant des flux vidéo privés vers des serveurs Cloud (États-Unis), créant ainsi une dépendance à Internet et une latence inévitable.

Les solutions de reconnaissance faciale "locales" standard présentent quant à elles plusieurs failles majeures :
- **Risques de sécurité (Spoofing) :** Usurpation facile par la présentation d'une simple photo 2D imprimée ou sur un téléphone.
- **Contraintes matérielles :** Difficulté de faire cohabiter des modèles d'IA lourds (YOLOv8 + Réseaux de neurones profonds) sur des microcontrôleurs légers (CPU overload).
- **Expérience Utilisateur (UX) :** Refus d'accès pour les résidents légitimes en cas de mains occupées (courses) ou de capteurs d'empreintes défaillants (pluie).
- **Intégrité des données (Model Drift) :** Risque de pollution de la base de données autorisée si l'IA apprend de manière non supervisée le visage d'inconnus.

Le projet **BioGate** propose une réponse industrielle via un contrôle d'accès multimodal, 100% autonome et local, déployé sur une architecture Edge / Client-Serveur.

---

## 2. Objectifs du système

L'objectif principal est de concevoir un écosystème de sécurité infaillible capable de :

1. **Détecter et Suivre (Tracking) :** Repérer la présence humaine en temps réel (YOLOv8n) et suivre l'individu via un identifiant stable (Centroid Tracker couplé à une Re-Identification vestimentaire colorimétrique HSV pour résister aux occlusions).
2. **Identifier formellement (Biométrie) :** Extraire l'ADN facial via des embeddings 512D (Facenet512) et les comparer mathématiquement aux profils autorisés.
3. **Contrer l'Usurpation (Anti-Spoofing) :** 
   - *Soit* par un **Liveness Challenge Actif** cognitif (exiger un sourire ou un clignement d'yeux pour prouver la vie).
   - *Soit* par un **MFA (Multi-Factor Authentication)** combinant une vérification faciale (Voie Rapide) et un lecteur d'empreinte digitale.
4. **Assurer l'Expérience Client (UX) :** Fournir un Dashboard d'administration Web convivial et envoyer des alertes silencieuses (avec photo) sur le smartphone du propriétaire via WhatsApp lors d'une intrusion.
5. **Préserver la Confidentialité (Privacy-First) :** Garantir que 100% du traitement IA est fait en local. Les photos d'intrus (Snapshots Forensiques) sont soumises à une purge automatique (RGPD) après 72h.

---

## 3. Architecture Matérielle (IoT et Infrastructure)

Le système adopte une approche modulaire stricte, séparant l'acquisition vidéo de l'intelligence artificielle.

### 3.1. Le Cerveau : Serveur Edge (Hub de Décision)
* **Matériel :** Raspberry Pi 4 (4 Go RAM min) avec refroidissement actif, **ou un PC sous Linux** faisant office de serveur local (selon les coûts d'approvisionnement et tests de scalabilité).
* **Rôle :** Exécuter les réseaux de neurones (YOLOv8, DeepFace), héberger la base de données SQLite et le serveur Web FastAPI.

### 3.2. L'Œil : Nœud de Capture Vidéo (Caméra Edge)
* **Matériel :** Carte de développement **BW21-CBV Ai-Thinker** (basée sur RTL8720DN).
* **Justification :** Contrairement à un ESP32-CAM (limité au 2.4 GHz et sujet aux saturations), la BW21-CBV intègre un Wi-Fi Dual-Band **5 GHz**, garantissant un flux vidéo streaming MJPEG HD à 30 FPS sans la moindre latence pour abreuver le serveur Edge.

### 3.3. Réseau LAN "Air-Gapped"
* **Matériel :** Routeur Wi-Fi classique dédié.
* **Justification :** Le système crée son propre intranet fermé. Il ne dépend pas de la box internet de la maison pour l'analyse. Une adresse IP fixe est attribuée à chaque module domotique pour un routage infaillible.

### 3.4. Résilience Énergétique
* **Matériel :** Mini-UPS DC (Uninterruptible Power Supply).
* **Justification :** Contrairement à un Powerbank classique qui provoque une micro-coupure de 1 seconde au changement d'état (faisant redémarrer le système), le Mini-UPS possède un temps de transfert nul (Zero-Transfer Time). Il protège le système (Routeur + Pi/PC + Caméra) contre les coupures de courant accidentelles ou le sabotage.

### 3.5. Les Nœuds d'Actionneurs Domotiques (ESP32 / ESP8266)
1. **Serrure Électromagnétique (Gâche) :** Pilotée via un relais suite à la validation d'accès. Sans aucun clavier physique extérieur pour éviter le vandalisme.
2. **Lecteur d'Empreinte Digitale :** Endormi par défaut, il est "réveillé" par le réseau uniquement quand la caméra reconnaît un visage VIP autorisé.
3. **Éclairage d'Accueil Interactif (Smart Lighting) :** Un module relais gérant une ampoule extérieure. S'allume de manière accueillante si un VIP est reconnu, ou flashe/éblouit si un intrus est persistant.

---

## 4. Architecture Logicielle

### 4.1. Stack Technologique
* **Cœur IA :** Python, OpenCV, Ultralytics (YOLOv8n), DeepFace (Facenet512), modèles optimisés (Quantization Edge prévue vers ONNX/TFLite).
* **Backend & API :** FastAPI (pour gérer les flux asynchrones et l'interface), Uvicorn.
* **Base de données :** SQLite (Base relationnelle locale).
* **Alerte :** API WhatsApp (Twilio / GreenAPI).

### 4.2. Le Pipeline IA ("Garbage In, Garbage Out")
Afin d'optimiser le temps de calcul sur le Raspberry Pi / PC Linux :
1. **Downscaling YOLO :** Réduction de l'image (imgsz=320) pour alléger l'usage CPU de 60%.
2. **Face Gate :** Une cascade de Haar (Niveaux de gris + EqualizeHist) vérifie que le visage est frontal avant de "réveiller" le modèle lourd Facenet512.
3. **Filtre CLAHE :** Traitement des contre-jours en amont de la biométrie pour éviter les faux rejets.
4. **Dédoublonnage spatial :** Logique d'inclusion personnalisée pour empêcher YOLO de détecter deux fois la même personne (tête vs corps).

### 4.3. Modèle de Données (Base SQLite)
La base est structurée en 3 tables majeures :
* `profiles` : Nom et statut (VIP ou INTRUS).
* `embeddings` : Vecteurs faciaux 512D (encodés en JSON). **Sanctuarisée en Lecture Seule** pour éviter le Model Drift.
* `audit_logs` : Boîte noire médico-légale. Contient un UUID par interaction, la chronologie du *Trust Score* (de 0 à 100%), les métadonnées, et le lien direct vers le fichier image (Forensic Snapshot) enregistré sur le disque.

---

## 5. Scénarios d'Utilisation Cibles

### 5.1. Accès "Voie Rapide" (Sécurité Absolue via Apprentissage Supervisé)
1. Le VIP approche. YOLO détecte son corps et le Face Gate isole son visage.
2. Facenet512 matche l'identité avec une certitude moyenne (Trust Score = 60%).
3. Le Serveur Edge envoie l'ordre de réveiller le lecteur d'empreinte digitale.
4. Le VIP pose son doigt (Trust Score = 100%). La porte s'ouvre, l'éclairage s'allume.
5. *Bonus ("Ground Truth") :* Fort de cette certitude matérielle absolue, le système se permet d'apprendre ce "nouveau visage" (peut-être porteur d'une casquette) et l'ajoute silencieusement à la base SQLite.

### 5.2. Accès "Mains Libres" (Fallback Liveness)
1. Le VIP arrive les bras chargés de courses (impossible d'utiliser l'empreinte).
2. L'interface lui demande de sourire ou cligner des yeux (Liveness Challenge Actif).
3. S'il réussit, l'IA valide que ce n'est pas une photo 2D (Trust Score = 85%). La gâche s'ouvre.

### 5.3. Détection d'Intrusion
1. Une personne non identifiée stationne devant la caméra (Trust Score = 20%).
2. Au-delà d'un délai défini, le système le classe comme "INTRUS".
3. Un Forensic Snapshot (photo) est découpé et sauvegardé sur le disque dur.
4. L'éclairage extérieur se met en position "Alerte".
5. Une notification WhatsApp contenant la photo est expédiée de manière asynchrone au propriétaire, sans bloquer le système local.

### 5.4. Administration Locale
1. Le propriétaire se connecte au Wi-Fi local et ouvre le **Dashboard Web** (servi par FastAPI).
2. Il peut visionner le flux direct, parcourir les `audit_logs` des dernières 24h, ajouter la photo d'un nouveau membre de la famille via un formulaire (`/enroll`), ou forcer l'ouverture de la porte.

---

## 6. Livrables Attendus

1. **Code Source Complet :** Backend FastAPI, modules IA optimisés, scripts clients.
2. **Dashboard Web :** Interface d'administration fonctionnelle.
3. **Maquette Physique (Prototype) :** Routeur, Caméra BW21-CBV, Cerveau (PC Linux/Pi), Mini-UPS, et maquette de porte (gâche électrique + relais + éclairage).
4. **Base de Données et Purge :** Script opérationnel purgeant les snapshots RGPD à 72h.
5. **Rapport de Mémoire :** Document justifiant scientifiquement l'architecture Edge, les choix des seuils IA (Trade-off Faux Positifs/Négatifs), et l'analyse de robustesse de l'Anti-Spoofing.

---
**Signataires**  
Candidat : HANTAN Hugues  
Encadrant académique : Mr. Probus KIKI
