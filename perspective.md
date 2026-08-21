# Perspectives et Fonctionnalités à Implémenter (Roadmap Technique)

Ce document centralise toutes les idées architecturales et les fonctionnalités documentées lors de la conception, mais qui restent à développer (coder) avant de finaliser le système BioGate pour la soutenance. 

Ces briques transforment le "Code de laboratoire" actuel en un **Produit Industriel** complet.

---

## 1. Expérience Utilisateur (UX) & Interfaces

### 1.1 Le Dashboard Admin (Interface Web Locale)
* **Concept :** Remplacer les commandes terminales (ex: `enroll Ash`) par une véritable interface de gestion.
* **Mise en œuvre :** Puisque le Hub utilise déjà **FastAPI**, celui-ci servira un front-end (HTML/JS, React ou Vue) hébergé localement.
* **Fonctionnalités prévues :** 
  - Visionnage du flux vidéo en direct (Web Stream).
  - Tableau de bord des événements passés (Logs d'audit + affichage des photos d'intrus).
  - Interface d'enrôlement officiel des VIP (upload de photo ou capture directe).
  - Contrôle manuel des portes.

### 1.2 Alertes à Distance (Intégration WhatsApp)
* **Concept :** Être alerté instantanément sur son smartphone lorsqu'une intrusion est avérée, en envoyant le "Forensic Snapshot" de l'intrus.
* **Paradoxe de confidentialité :** Comment rester "Local-Only" ? L'analyse lourde (YOLO/DeepFace) reste 100% hors-ligne (Edge). L'internet n'est sollicité que comme un tuyau ponctuel pour l'alerte sortante.
* **Mise en œuvre :** Intégration d'une API (Twilio, GreenAPI, ou CallMeBot) dans FastAPI, déclenchée lors de la classification `INTRUS`.

---

## 2. Anti-Spoofing & Contrôle d'Accès

### 2.1 Le "Liveness Challenge" Actif (Anti-Spoofing Cognitif)
* **Concept :** Empêcher l'usurpation par une photo imprimée HD. L'attente passive de 5 secondes ayant été identifiée comme une faille.
* **Mise en œuvre :** L'interface client demandera à l'usager de réaliser une action physique (sourire ou cligner des yeux), validée par des classifieurs dédiés (ex: `haarcascade_smile.xml`).

### 2.2 Le Système de "Trust Score" (Machine à États)
* **Concept :** L'identification n'est plus binaire, c'est une escalade de la confiance cumulée :
  - **20% :** Présence humaine détectée (YOLO).
  - **60% :** Match facial 2D réussi (Facenet512).
  - **85% :** Défi Liveness (Sourire) réussi.
  - **100% :** Empreinte digitale validée (MFA matériel).
* **Mise en œuvre :** Refonte de la variable `status` dans `face_recognizer.py` pour intégrer ce scoring cumulatif.

---

## 3. Le Tracking Avancé (Continuité Visuelle)

### 3.1 La Re-Identification Vestimentaire (Color Re-ID HSV)
* **Concept :** Si une personne passe derrière un pilier, le Tracker géométrique la perd. L'idée est d'encoder la couleur de ses vêtements pour lui ré-attribuer instantanément son Identité (ID) sans relancer l'analyse faciale (DeepFace).
* **Mise en œuvre :** Extraction d'un histogramme de couleurs dans l'espace HSV (`cv2.calcHist`) sur la boîte YOLO entière du corps, puis comparaison via la distance de Bhattacharyya.

---

## 4. Intégration Matérielle (Domotique / IoT)

### 4.1 Les Routes de Commandes et Actionneurs
* **Concept :** Interfacer le Hub IA logiciel avec le monde physique.
* **Mise en œuvre :** Création de nouveaux Endpoints FastAPI (ex: `GET /mfa/door_status`, `POST /door/open`) pour envoyer des signaux réseau ou GPIO vers des relais, gâches électriques, ou capteurs ESP32.

### 4.2 L'Apprentissage Supervisé Hardware (Le "Ground Truth")
* **Concept :** Permettre à l'IA d'enrichir sa base de données faciale (qui est actuellement verrouillée en lecture seule) de manière 100% sécurisée.
* **Mise en œuvre :** Si la caméra obtient un match incertain (60%), mais que l'utilisateur valide son entrée physique avec son empreinte digitale, le système utilise cette preuve matérielle irréfutable pour ajouter le nouveau cliché du visage (ex: avec un bonnet/lunettes) dans SQLite.

---

## 5. Le Backend & Conformité Légale

### 5.1 La Journalisation d'Audit Avancée (`audit_logs`)
* **Concept :** Transformer l'historique basique actuel en une véritable "Boîte Noire" médico-légale.
* **Mise en œuvre :** Création d'une nouvelle table SQLite `audit_logs` contenant : un UUID unique pour l'interaction, l'évolution précise du Trust Score, des métadonnées JSON, et le chemin relatif vers le fichier photo du "Forensic Snapshot".

### 5.2 La Purge Automatique RGPD
* **Concept :** Ne pas conserver les snapshots des intrus indéfiniment pour respecter les lois sur la vie privée et éviter l'engorgement du disque.
* **Mise en œuvre :** Un script asynchrone ou une tâche cron qui supprime automatiquement les clichés vieux de plus de 72 heures.

---

## 6. L'Optimisation Edge Ultime

### 6.1 La Quantization des Modèles
* **Concept :** Rendre les modèles d'Intelligence Artificielle compatibles avec les petits processeurs ARM (comme le Raspberry Pi 4).
* **Mise en œuvre :** Convertir les réseaux PyTorch (`yolov8n.pt`) et Keras (DeepFace) aux formats spécialisés Edge comme `.tflite` (TensorFlow Lite) ou `ONNX` avec une Quantification INT8.
