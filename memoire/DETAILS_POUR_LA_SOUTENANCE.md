# Détails retirés du mémoire, pour la soutenance

Ce fichier garde ce qui a été retiré du mémoire pour en alléger la lecture (63 pages au lieu de 70, corps de 45 pages contre 42 et 47 pour les deux mémoires de référence).
Il n'est pas destiné à être déposé. Il sert à répondre aux questions. Les versions complètes du texte sont aussi dans l'historique git (commit précédant « Allège les chapitres 2 et 3 »).

**Règle de tri retenue.** Reste dans le mémoire ce qui soutient la problématique, les objectifs et les résultats. Vont dans ce fichier : les noms de fichiers du code, les listes de paramètres secondaires, la liste des routes, les défauts mineurs, les détails d'installation.

---

## 1. Routes de l'interface de programmation (37 routes, 26 avec jeton)

**Routes de l'interface de programmation, regroupées par fonction**

| **Fonction** | **Routes** | **Jeton exigé** |
|---|---|---|
| Analyse et enrôlement | `/analyze_frame`, `/enroll` | non |
| Second facteur (simulé) | `/access_status`, `/fingerprint_result`, `/request_liveness`, `/liveness_result` | non |
| Configuration | `/config` (lecture et modification) | oui |
|  | `/config/templates`, `/config/apply_template` | non |
| Alertes | `/alerts/test`, `/alerts/telegram/detect`, `/alerts/telegram/purge` | oui |
| Journal et vie privée | `/logs`, `/logs/stats`, `/logs/purge`, `/logs/{id`, `/rgpd/status` | oui |
| Profils | `/profiles` (lecture), `/profiles/{nom` (suppression) | oui |
| Actionneurs (simulés) | `/iot/door`, `/iot/fingerprint`, `/iot/light`, `/iot/door/open`, `/iot/door/lock` | oui |
| Caméras | `/cameras` (4 routes), `/cameras/scan/usb`, `/snapshot`, `/snapshot/{cam_id` | oui |
| Flux vidéo | `/stream`, `/stream/{cam_id` | oui, dans l'adresse |
| Couplage et santé | `/pair/request`, `/auth/token`, `/health` | non, par conception |

## 2. Réglages complets

**Réglages de la détection et de la reconnaissance**

| **Réglage** | **Rôle, et effet d'une hausse** | **Défaut** | **Où** |
|---|---|---|---|
| Seuil de reconnaissance | Distance maximale entre deux vecteurs pour les juger identiques. Une hausse reconnaît plus de résidents mais augmente le risque de confondre deux personnes. | 0,35 | Curseur, de 0,15 à 0,70 |
| Intervalle de revérification | Délai entre deux contrôles d'une personne déjà identifiée. Plus long : moins de calcul, mais un remplacement de personne est détecté plus tard. | 0,8 s | Curseur, de 0,3 à 3 s |
| Durée d'analyse d'un visage inconnu | Temps laissé à la reconnaissance avant de classer l'individu intrus provisoire. Plus long : moins de faux intrus, mais alerte plus tardive. | 1 s | Curseur, de 0,5 à 5 s |
| Durée de réanalyse d'un résident | Même rôle pour un résident déjà reconnu qui retombe en analyse. | 5 s | Fichier |
| Échecs avant remise en question | Nombre de revérifications ratées de suite avant de reclasser un individu. Plus élevé : identité plus stable, remplacement détecté plus tard. | 3 | Profil |
| Distance de correspondance forte | Distance sous laquelle un intrus provisoire reconnu comme résident est reclassé aussitôt. | 0,25 | Fichier |
| Attente d'un visage avant classement en intrus | Durée au-delà de laquelle une silhouette sans visage est classée intrus ; 0 signifie jamais. | 0 | Profil |
| Confiance minimale de détection | Score minimal pour garder une personne détectée. Plus élevé : moins de fausses personnes, mais risque d'en manquer une. | 0,5 | Paramètre |
| Taille de l'image de détection | Réduction de l'image avant la détection. Plus petite : calcul plus rapide, détection moins fine. | 320 px | Paramètre |

**Réglages du second facteur, des alertes et de la conservation**

| **Réglage** | **Rôle, et effet d'une hausse** | **Défaut** | **Où** |
|---|---|---|---|
| MFA obligatoire | Exige un second facteur après la reconnaissance du visage. | non | Interrupteur, profil |
| Vivacité activée | Inclut le test de vivacité dans le second facteur. Désactivé, seule l'empreinte reste possible. | oui | Interrupteur, profil |
| Délai de l'empreinte | Temps accordé pour valider l'empreinte, au-delà duquel l'accès est refusé. | 15 s | Curseur, de 5 à 60 s |
| Durée du défi de vivacité | Temps accordé pour exécuter le geste demandé. | 10 s | Paramètre |
| Scores après vivacité et après empreinte | Niveaux de confiance affichés lorsqu'un second facteur réussit. | 85 % et 100 % | Paramètre |
| Fenêtre de grâce | Délai avant de confirmer un intrus provisoire. Plus long : plus de temps pour reconnaître un résident, mais alerte plus tardive ; plus court : alerte rapide, mais plus de fausses alertes. | 60 s | Curseur, de 10 à 120 s |
| Délai minimal entre deux alertes | Évite l'envoi de nombreux messages pour une même personne. | 30 s | Fichier |
| Canaux d'alerte | Activent l'envoi par Telegram et par courrier électronique. | désactivés | Page Alertes, profil |
| Conservation des photos | Durée avant la suppression automatique des photos. | 72 h | Curseur, de 24 à 720 h |
| Période de la purge | Fréquence du contrôle des photos et des messages à supprimer. | 60 min | Fichier |
| Suppression des messages Telegram | Délai avant la suppression d'un message d'alerte dans la conversation. Plafonné à 47 h ; 0 désactive la suppression. | 24 h | Fichier |

## 3. Paramètres du pipeline

**Principaux paramètres du pipeline**

| **Paramètre** | **Valeur** |
|---|---|
| Confiance minimale de la détection des personnes | 0,5 |
| Taille de l'image pour la détection | 320 pixels |
| Seuil de reconnaissance (distance cosinus, FaceNet512) | 0,35 |
| Distance de correspondance forte (reclassement d'un intrus provisoire) | 0,25 |
| Fenêtre d'identification d'un visage inconnu | 1 s |
| Fenêtre de réanalyse d'un résident déjà reconnu | 5 s |
| Intervalle de revérification | 0,8 s |
| Échecs consécutifs avant remise en question | 3 |
| Corrélation des couleurs de vêtements pour retrouver une personne | 0,85 |
| Fenêtre de grâce avant une alerte | 60 s |

## 4. Défauts mineurs retirés du tableau du chapitre 3

| Défaut | Cause | Correction |
|---|---|---|
| Alertes sans photo | La photo n'était jamais rattachée à l'intrus | Rattachement à l'intrus provisoire, jamais à un résident |
| Photos hors de portée de la purge | Fichier sans ligne de journal quand le résident revient ou que la personne s'éloigne | Suppression dans ces deux cas |
| Noms d'intrus dupliqués | Compteur remis à zéro au rechargement des vecteurs | Compteur qui ne recule jamais |
| Détection de Haar en double | Seconde détection pour dessiner l'encadré | Réutilisation de la position mémorisée |
| Carte bloquée après le départ d'un client | La fonction d'écriture de la bibliothèque est déclarée booléenne mais renvoie $-1$ en cas d'échec, que rien ne détecte | Délai de réception court et lecture d'un octet par image |
| Première requête lente après un repos | Économie d'énergie du Wi-Fi, de 7 à 27 secondes | Économie d'énergie désactivée |
| Installation non reproductible | Deux paquets OpenCV de versions différentes pour le même dossier de programmes | Les deux paquets fixés à la même version, versions des bibliothèques fixées, vérification dans un environnement neuf |
| Libellés des profils faux au tableau de bord | Libellé non aligné sur le comportement du serveur | Libellés des profils bureau et haute sécurité corrigés |

## 5. Modules du code

- **Serveur** (`api.py`) : application FastAPI qui regroupe les routes, le pipeline d'analyse et les tâches de fond ;
- **Détection** (`core/yolo_detector.py`) : repérage des personnes avec YOLOv8 ;
- **Suivi** (`core/centroid_tracker.py`) : attribution d'un identifiant stable à chaque individu ;
- **Reconnaissance** (`core/face_recognizer.py`) : filtre de visage, calcul du vecteur, comparaison et décisions d'identité ;
- **Score de confiance** (`core/trust_score.py`) : machine à états et authentification multifacteur ;
- **Vivacité** (`core/liveness_detector.py`) : défi du geste tiré au sort ;
- **Caméras** (`core/camera_manager.py`) : ouverture et reconnexion des sources vidéo ;
- **Alertes** (`core/notifier.py`) : envois vers Telegram et par courrier électronique ;
- **Actionneurs** (`core/iot_controller.py`) : porte, lumière et lecteur d'empreinte, simulés dans le prototype ;
- **Base de données** (`database/db_manager.py`) : profils, vecteurs, journal, configuration et purge ;
- **Installation** (`requirements.txt`, `telecharger_modeles.py`) : versions fixées des bibliothèques et téléchargement du modèle MediaPipe, dont l'empreinte est vérifiée ;
- **Micrologiciel** (`firmware/bw21_camera_protegee`) : programme de la caméra ;
- **Tests** (`tests/`) : tests automatiques et rapports de mesure.

## 6. Gestion des pannes : cas retirés

- **Actionneur injoignable** : la requête a un délai d'une seconde et part dans un fil séparé. Dans le prototype, les actionneurs sont simulés.
- **Individu disparu avant le verdict** : une alerte de fuite est journalisée si un visage avait été vu, et un passage sans visage laisse une trace discrète. Pendant la fenêtre de grâce d'un intrus provisoire, l'alerte est annulée et la photo supprimée.
- **Photo absente au moment de l'alerte** : le message est envoyé sans photo.

## 7. Limites détaillées (version longue)

- **Périmètre de validation** : l'évaluation est exploratoire ; les taux d'erreur reposent sur une seule série de 1 000 paires de LFW, et non sur une caméra de porte, et les autres essais portent sur peu de personnes et de photographies ;
- **Efficacité anti-usurpation** : aucune attaque par photographie, vidéo rejouée ou masque n'a été présentée, et la caméra ne mesure pas la profondeur ;
- **Matériel simulé** : le lecteur d'empreinte, la gâche et la lumière sont simulés, et l'écran LCD des consignes, reporté à la fin du projet, n'est pas réalisé ;
- **Portage** : l'exécution sur un micro-ordinateur monocarte de type Raspberry Pi est visée mais n'a pas été essayée, et la quantification des modèles n'est pas faite ;
- **Visages proches** : deux profils de résidents ont des visages proches : le vecteur du second profil le plus proche du profil principal est à 0,306, sous le seuil de 0,35, et une confusion est possible. En direct, des distances de 0,23 à 0,35 ont été observées entre le visage de l'auteur et ce second profil. La mesure à la webcam donne une marge toujours positive entre les deux profils, d'au moins 0,109. Aucune marge de décision entre profils proches n'est ajoutée, et ce cas est exclu des essais finaux ;
- **Caméra** : la clé du flux et le réseau Wi-Fi sont mémorisés sans chiffrement dans la mémoire flash de la carte, et la reprise après une coupure provoquée du Wi-Fi n'a pas été éprouvée ;
- **Sources vidéo** : le flux RTSP n'a pas été vérifié, faute de serveur RTSP, ni le HTTPS ;
- **Sécurité des échanges** : pas de HTTPS, onze routes sans jeton dont celles utilisées par l'outil de développement, et aucun audit de sécurité externe ;
- **Protection des données** : les vecteurs ne sont pas chiffrés dans la base, les identifiants des canaux d'alerte y sont enregistrés en clair, et la table d'audit prévue n'est pas implémentée ;
- **Messages Telegram** : les messages envoyés avant la suppression automatique restent dans la conversation, et la suppression d'une alerte accompagnée d'une photo n'a pas été essayée en conditions réelles ;
- **Journal** : les lignes du journal ne sont pas purgées, seules les photos le sont ;
- **Alertes** : un envoi qui échoue n'est pas renvoyé, un intrus qui quitte le champ avant la fin de la fenêtre de grâce n'est pas signalé, et un passant sans visage ne déclenche aucune alerte à distance ;
- **Réglages** : la durée d'analyse et l'intervalle de revérification ne prennent effet qu'au redémarrage du serveur ;
- **Alimentation** : une coupure d'électricité arrête le serveur et fait perdre les états en mémoire, dont le jeton du tableau de bord.

## 8. Questions probables du jury

Les réponses s'appuient sur ce que le mémoire, le journal de bord et les mesures établissent. Quand une réponse n'est pas démontrée, elle le dit.

**Pourquoi Electron et non Python pour le tableau de bord ?**
Electron permet une seule base de code pour Windows, macOS et Linux, stocke le jeton chiffré par le système d'exploitation, produit un installateur en une commande et affiche le flux MJPEG avec une simple balise image. Le serveur reste en Python et le tableau de bord n'en dépend pas. Point faible reconnu : Electron embarque un navigateur, donc l'application est lourde. Aucune comparaison avec une bibliothèque graphique Python n'a été faite.

**Pourquoi FastAPI et non Node.js ?**
Tout le moteur d'intelligence artificielle (YOLO, DeepFace, MediaPipe, OpenCV) est en Python. Une API en Python appelle ces bibliothèques directement, sans passerelle entre deux langages. FastAPI se présente comme un cadre moderne et rapide, fondé sur les annotations de types standard. Aucune comparaison avec Node.js n'a été faite pendant le développement.

**Pourquoi Telegram et non WhatsApp ?**
L'interface officielle de WhatsApp exige un portefeuille d'entreprise Meta et, depuis le 1er juillet 2025, facture au message les envois faits par l'entreprise. Un robot Telegram est gratuit par défaut et accepte une photo de 10 Mo au plus.

**Pourquoi la BW21-CBV et non l'ESP32-CAM ?**
L'ESP32-CAM n'émet qu'en 2,4 GHz. La BW21-CBV offre un Wi-Fi bi-bande. La bande réellement utilisée par l'auteur n'est pas tranchée : ne pas l'affirmer.

**Pourquoi FaceNet512 et non VGG-Face ?**
VGG-Face, avec une détection basique, s'est révélé trop imprécis sous la lumière d'une webcam. Observation du 02/11 : dans une pièce peu éclairée, 39 reconfirmations avec une distance moyenne de 0,178, toutes sous le seuil. C'est une observation, pas une comparaison chiffrée.

**Le taux de faux rejet de 52 % n'est-il pas énorme ?**
Mesuré sur LFW, avec un seul échantillon par personne et des photos non contrôlées, au seuil prudent de 0,35 (aucune fausse acceptation sur 500 paires). BioGate compare à plusieurs échantillons enrôlés à la webcam, donc son taux réel est plus bas, mais il n'est pas mesuré. L'écart avec les performances publiées de FaceNet n'est pas expliqué ; quatre pistes restent à tester (sans CLAHE, image entière, détecteur d'alignement de DeepFace, normalisation).

**Pourquoi le seuil de 0,35 alors que DeepFace donne 0,30 ?**
Valeur réglée à la webcam : 0,20 refusait trop de résidents et 0,60 acceptait trop d'inconnus. Relever le seuil réduit les refus mais augmente le risque de confondre deux personnes.

**Votre test de vivacité résiste-t-il à une vidéo ?**
Non démontré. Le geste est tiré au sort, ce qui oblige une vidéo à contenir exactement le geste demandé, mais aucune attaque n'a été présentée au système. La caméra est en deux dimensions, sans capteur de profondeur, alors que Face ID emploie une caméra TrueDepth.

**La photo de l'intrus passe par Telegram : où est le traitement local ?**
L'analyse, les vecteurs, la base et la purge restent en local. Seule l'alerte sort, désactivée par défaut. Le message est supprimé de la conversation après 24 heures (plafond de 47 heures imposé par l'API des robots).

**Pourquoi pas de HTTPS ?**
La bibliothèque Wi-Fi de la carte n'offre ni serveur chiffré ni filtrage par adresse. Le serveur et le tableau de bord n'utilisent pas HTTPS dans le prototype ; c'est une perspective. La protection repose sur un réseau Wi-Fi chiffré et isolé.

**Pourquoi une photo de l'acteur Chris Evans ?**
Photographies publiques sous licence libre, couvrant 11 ans, qui montrent le vieillissement et le passage d'un visage rasé à une barbe. Elles ne servent qu'à mesurer une distance entre deux vecteurs.

**Les 137 puis 180 tests prouvent-ils que le système marche ?**
Ils vérifient le comportement de chaque module, avec contre-épreuve. Ils n'ont pas détecté le défaut des inconnus sans cadre : il a fallu un essai réel. Le mémoire le dit.
