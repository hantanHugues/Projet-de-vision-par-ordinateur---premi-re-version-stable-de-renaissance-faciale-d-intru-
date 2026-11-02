# Brief pour continuer le mémoire (session du téléphone)

Écrit le 01/11/2026 depuis le poste de développement. Il réunit **l'état réel du code**, **les consignes de l'auteur**
et **les corrections à reporter** dans `memoire/` (branche `claude/memoire-latex-telephone-h1vdti`).
À lire en entier avant de toucher au texte. La branche a été créée sur le code du 29/10 ; ce qui a changé depuis est ici.

Pour récupérer le code à jour : `git fetch origin && git merge origin/main` (sur la branche du mémoire).

**Les réponses aux questions de `memoire/QUESTIONS_ET_MANQUES.md` sont dans `docs/REPONSES_AU_TELEPHONE.md`** (même numérotation).
Deux corrections importantes qu'elles contiennent : Face ID a bien une caméra de profondeur (TrueDepth) et la plage « 0,23 à 0,35 »
entre profils proches vient d'observations en direct, pas des vecteurs enregistrés.

---

## 1. Consignes de l'auteur

- **Langue et ton** : français, ton académique formel, mots simples. Phrases courtes, concrètes, sans tournure de conversation
  (« ça découle directement de… », « s'y ajoute… ») et sans tic de rédaction automatique. Un terme anglais se définit dans une
  phrase (« le traitement en périphérie de réseau, ou Edge Computing, consiste à… »), pas entre parenthèses.
- **Une affirmation = une source**, ou la mention « observation de l'auteur ». Pas de chiffre sans origine. Le contexte béninois
  (coût d'Internet, instabilité du courant) reste présenté comme une observation de l'auteur.
- **Ne pas centrer l'introduction sur le projet** ni la rendre technique d'emblée : elle part du contrôle d'accès en général,
  puis de ce qu'un visage vaut comme preuve, avant d'arriver à BioGate. Pas de détail de fonctionnalité (durée de purge,
  noms de modèles) dans l'introduction.
- **Plan de l'introduction des mémoires de référence** (Dyanos, Espérance) : introduction générale en deux paragraphes,
  1- Contexte et justification, 2- Problématique, 3- Objectifs, 4- Organisation du mémoire. La problématique est un
  paragraphe qui nomme les problèmes (« Sur le plan technique… Sur le plan de la sécurité… Enfin… »), puis « La problématique
  centrale de ce mémoire peut donc être formulée comme suit : Comment… ? ». Une seule question, pas de sous-questions, pas de
  liste à puces. Pas de section « démarche » ni « périmètre et limites » dans l'introduction : les limites vont en 3.x et en conclusion.
- **Texte de référence** : l'annexe A reprend l'introduction écrite dans ce style (validée dans sa forme, sources à compléter
  avec celles de la branche quand elles s'y prêtent : Ring/FTC, Best-Rowden, Deb…).
- **Ne pas faire perdre de temps** : pas de long raisonnement, pas de test « évident » demandé à l'auteur. Dire clairement ce qui
  est fait, ce qui ne l'est pas, et ce qu'il doit décider.
- **Décisions déjà prises** : le frère de l'auteur est hors des tests finaux ; l'écran LCD est reporté à la toute fin ;
  aucune marge de décision entre profils proches n'est ajoutée au code ; le chapitre 3 contient « les mesures » (pas de chapitre 4).

---

## 2. État réel du projet à reporter

### Caméra BW21-CBV (firmware final : `firmware/bw21_camera_protegee/bw21_camera_protegee.ino`)
- Puce Realtek **RTL8735B** (module BW21-CBV) ; dans l'IDE Arduino : carte `AMB82-MINI`, paquet Realtek AmebaPro2 4.1.0.
- **Plus de `secrets.h`, de `cle_flux.txt` ni de `generer_secrets.py`.** Au premier démarrage, la carte demande sur le port série :
  le réseau Wi-Fi (liste par balayage), son mot de passe, et la **clé du flux (12 à 32 caractères alphanumériques, choisie par
  l'auteur)**. Ces réglages sont mémorisés dans la mémoire flash de la carte (non chiffrée : à ajouter aux limites). Une touche
  pressée dans les 5 premières secondes du démarrage permet de les modifier.
- Au redémarrage, la carte **se reconnecte seule au dernier réseau enregistré** (vérifié). Si le Wi-Fi tombe, une boucle du programme
  relance la connexion (reprise non éprouvée par une coupure provoquée : à écrire comme telle, l'auteur la juge évidente).
- Flux MJPEG 640×480, lu par BioGate à 17-30 images par seconde. Reconnaissance et test de vivacité validés sur ce flux.
- Protection : identifiant + clé (en-tête d'authentification), comparaison en temps constant, requête bornée (1024 octets, 3 s),
  blocage 30 s après 5 refus. Pas de HTTPS ni de filtrage par adresse (la bibliothèque de la carte ne les offre pas).
- **Défauts trouvés sur la vraie carte, à ajouter au tableau « Défauts découverts et corrigés » du chapitre 3** :
  1. redémarrage de la carte toutes les 30 s : chien de garde de 20 s armé avant la connexion Wi-Fi et l'initialisation de la caméra ; corrigé en le supprimant (0 coupure sur 87 s ensuite) ;
  2. OpenCV ne lisait aucune image : la ligne de séparation du flux doit précéder la première image (l'exemple Realtek ne l'envoie qu'après) ; corrigé avec un test de contre-épreuve ;
  3. carte bloquée après le départ d'un client : `ServerDrv::sendData` est déclarée `bool` et renvoie `-1` en échec, donc les écritures ratées ne sont jamais vues ; contourné par `client.setRecvTimeout(20)` et une lecture par image ;
  4. première requête après un repos de 7 à 27 s : économie d'énergie du Wi-Fi ; corrigé par `WiFi.disablePowerSave()`.
- **Bande Wi-Fi** : l'auteur affirme que la carte s'est connectée en 5 GHz ; l'entrée 024 de `docs/lab_journal.md` note 2,4 GHz canal 1
  (relevé du port série). Ne pas écrire la bande dans le mémoire avant que l'auteur ait tranché ; la fiche technique indique le bi-bande.

### Serveur
- Correctifs du 29/10 déjà dans `main` : second avis MediaPipe contre les faux visages, réanalyse patiente d'un résident (5 s),
  correspondance forte (distance < 0,25), compteur d'intrus qui ne recule plus, purge RGPD automatique.
- Webcam : l'image est retournée **à l'affichage seulement** ; l'analyse reçoit toujours l'image brute.
- **Nouveau : suppression des messages Telegram** (`core/notifier.py`, `database/db_manager.py`, `api.py`, `config.py`).
  - Chaque message envoyé (alerte avec photo, message de test) est enregistré (table `telegram_messages`, **la sixième table**).
  - La boucle de purge RGPD (au démarrage puis toutes les heures) supprime ceux qui ont dépassé `TELEGRAM_DELETE_AFTER_HOURS`
    (**24 h par défaut, plafonné à 47 h** : l'API des bots ne supprime qu'un message de moins de 48 h ; 0 désactive).
  - Route `POST /alerts/telegram/purge?older_than_hours=` (jeton exigé) pour la lancer à la main.
  - **Essai réel (01/11)** : message de test envoyé puis supprimé par la route, `deleted: 1` ; seconde purge `deleted: 0` ; route sans jeton : 401.
  - Non couvert par un essai réel : le chemin d'une alerte avec photo (couvert par les tests automatiques). Les messages envoyés
    avant cette version restent dans la conversation (identifiant non enregistré).
- **37 routes** (26 avec jeton, 11 sans : 3 par conception, 8 pour le programme client et le choix des profils).
- Le jeton Telegram a été collé dans une conversation : à révoquer chez @BotFather en fin de projet, puis à ressaisir dans l'onglet Alertes.

### Tableau de bord
- Page Configuration : bouton **Modifier** par caméra ; l'adresse d'une caméra IP s'affiche avec la clé masquée (`********`) ; la clé
  est conservée côté serveur quand la valeur masquée est renvoyée.

### Tests : 172 réussis sur `main` (180 une fois les 8 tests de vivacité de la branche fusionnés ; à relancer après fusion)
La branche actuelle (175 tests) a été vérifiée le 01/11 dans un environnement neuf : tout passe, à condition que le modèle MediaPipe soit présent
(voir « Installation »). Sans lui, `test_a_shirt_is_never_judged_as_an_unknown_face` échoue.
Voir l'annexe B pour le tableau par domaine. Commande : `.venv-deepface\Scripts\python.exe -m unittest discover -s tests -t .`

### Installation (`requirements.txt` corrigé le 01/11)
- Problème : `mediapipe` exige `opencv-contrib-python` alors que `deepface` et `ultralytics` exigent `opencv-python`. Les deux paquets installent le
  même dossier `cv2` ; dans l'environnement de l'auteur ils avaient des versions différentes (4.11 et 4.13). De plus `retina-face` 0.0.19 et suivantes
  exigent un troisième paquet OpenCV (5.x), le fichier avait un BOM et presque aucune version n'était fixée.
- Correction : les deux paquets OpenCV sont fixés à la même version (4.11.0.86), `retina-face` à 0.0.17, `keras` à 3.14.1, les autres bibliothèques
  principales aux versions des essais. Vérifié dans un environnement neuf (`uv venv` puis installation du fichier tel quel) : un seul cv2 cohérent et
  les 167 tests réussis. `torch` n'est pas fixé (essais avec la 2.11.0, tests vérifiés aussi avec la 2.15.0).
- Python 3.11 est exigé (la 3.13 pose des incompatibilités).
- **Modèle MediaPipe** : `models/face_landmarker.task` (3,6 Mo) est ignoré par git et rien ne le téléchargeait. Sans lui, le test de vivacité ne démarre pas
  et le second avis contre les faux visages disparaît (la chemise est de nouveau prise pour un visage). Le script `telecharger_modeles.py` le télécharge
  depuis l'adresse officielle de Google et vérifie son empreinte SHA-256 (identique au fichier des essais) ; l'étape est dans le README.
  Procédure complète vérifiée : environnement neuf, `requirements.txt`, modèle, puis tous les tests réussis.

### Mesures
- Faites : filtre de visage (Haar), apprentissage continu, temps de traitement (voir `docs/lab_journal.md`).
- **FAR/FRR sur LFW (fait le 01/11)** : `tests/mesures/mesure_far_frr.py`, résultats dans `docs/mesures/far_frr/`
  (`rapport_far_frr.md`, `far_frr.csv`, `far_frr.png`, `distances.csv`). 500 paires de la même personne, 500 de personnes différentes,
  chaîne de BioGate (Haar, CLAHE, FaceNet512, distance cosinus). Au seuil de BioGate (0,35) : **FAR 0,0 %, FRR 52,0 %**. Point d'égal
  taux d'erreur : 13,1 % au seuil 0,74. Aire sous la courbe ROC : 0,931. À écrire dans une nouvelle sous-section « Taux de fausse
  acceptation et de faux rejet » du chapitre 3, en retirant la limite « sans mesure des taux » (elle devient « une seule série de
  1 000 paires de LFW, pas une caméra de porte »).
  **Lecture à écrire honnêtement** : le seuil de 0,35 est prudent (aucune fausse acceptation sur 500 paires) au prix de nombreux refus
  sur ces photos non contrôlées, comparées à un seul échantillon. BioGate compare à plusieurs échantillons enrôlés à la webcam, donc son
  FRR réel est plus bas. Ne pas écrire que le FRR de BioGate vaut 52 % en usage réel, ni qu'il vaut moins : ce n'est pas mesuré.
  L'écart avec les performances publiées de FaceNet n'est pas expliqué (détecteur, recadrage, CLAHE possibles) : le dire, ne pas l'inventer.
  Le seuil par défaut de DeepFace pour Facenet512 est 0,30 ; BioGate retient 0,35 (réglé à la webcam).
- **Distance moyenne « 0,269 → 0,106 »** (chapitre 3, adaptation) : c'est la moyenne des distances que le serveur a journalisées lors de reconnaissances
  réelles à la webcam, avant puis après quatre validations d'empreinte (189 puis 45 mesures, recette du 29/10). Source unique : entrée 023 du journal.
  **Non reproduite depuis** : à écrire « relevé dans le journal du serveur lors d'une séance », sans dire « confirmé ».
- **Observation en direct (02/11, serveur réel, webcam sombre : luminosité 49 sur 255)** : le journal du serveur montre 39 re-confirmations de « Ash »
  en 46 secondes, distance moyenne **0,178** (médiane 0,160, minimum 0,11, maximum 0,29, écart-type 0,04), toutes sous le seuil de 0,35, et un accès
  accordé à 75,2 %. BioGate reconnaît donc l'auteur même dans une pièce peu éclairée. C'est une séance, un visage : à citer comme observation.
- **Reproduction contrôlée (02/11, valide) : la baisse « 0,269 → 0,106 » n'est PAS reproduite.** `tests/mesures/mesure_apprentissage_webcam.py` (chaîne de BioGate : YOLO, Haar dans la silhouette, MediaPipe, `_extract_face_signature`) compare, sur les **mêmes 78 images** d'une séance de 40 s, le seul vecteur d'origine du profil de l'auteur (enrôlement du 10/04) et le profil complet de 8 vecteurs. Résultats (`docs/mesures/apprentissage_webcam/`) : distance moyenne **0,209 → 0,203** (différence 0,006) ; pire image **0,436 → 0,274** ; images au-dessus du seuil de 0,35 : **2 sur 78 → 0** (reconnues : 76 sur 78 → 78 sur 78) ; écart-type 0,044 → 0,027 ; marge face à l'autre profil toujours positive (minimum 0,109, moyenne 0,220) : l'autre profil passe sous 0,35 sur 2 images mais n'est jamais plus proche que le profil de l'auteur.
  **Lecture honnête** : sur un visage proche de son enrôlement, l'apprentissage ne baisse presque pas la moyenne mais supprime les pires cas (les deux images au-dessus du seuil). Les moyennes du journal (0,269 puis 0,106) viennent de deux séances aux conditions différentes : **ne pas écrire que l'apprentissage fait passer la distance moyenne de 0,269 à 0,106**. Citer le relevé du journal comme tel (« moyennes relevées dans le journal du serveur lors de deux séances ») et présenter la mesure contrôlée comme preuve de l'effet, avec ses limites : une personne, une séance, un éclairage ; images consécutives très proches ; prendre le minimum sur plusieurs vecteurs baisse mécaniquement la distance. L'essai avec changement d'apparence (Chris Evans, 0,4722 → 0,224) reste la démonstration d'un vrai changement.
- Pas encore faites : attaque par photographie et par vidéo (avec l'auteur, environ une heure), performance complète (ms par image).

---

## 3. Corrections à reporter dans `memoire/`

1. **Clé du flux** (`2-partie` §Caméra, `3-partie` §Réalisation de la caméra) : retirer « clé de 192 bits générée par un script
   (`generer_secrets.py`) » ; écrire clé de 12 à 32 caractères choisie par l'auteur, saisie à la première mise en service et mémorisée
   dans la mémoire flash de la carte, avec le réseau Wi-Fi. Ajouter aux limites : réglages non chiffrés dans la carte.
2. **Reconnexion** (`2-partie` tableau des composants et §Caméra, `3-partie` §Caméra et §Résilience) : remplacer « testé : reconnexion
   automatique après une coupure du réseau » par la formulation du §2 (vérifié après redémarrage ; boucle de reconnexion dans le programme).
3. **Suppression Telegram** : `2-partie` §Alertes (la « perspective » de suppression après trois jours devient réalisée, avec 24 h et le
   plafond de 47 h dû à l'API), `3-partie` §Bilan (« sa suppression chez le fournisseur n'est pas encore automatisée ») et §Perspectives
   (« Réduire la sortie de données »), tableau des réglages (ligne `TELEGRAM_DELETE_AFTER_HOURS`, 24 h, « Fichier »), liste des routes
   (une ligne de plus, avec jeton), modèle de données (**six tables** ; figure : ajouter `telegram_messages` sans clé étrangère).
4. **Tests** : remplacer « 137 cas » et le tableau par l'annexe B ; retirer la note rouge sur la suite à relancer après l'avoir relancée.
5. **Défauts** : ajouter les quatre défauts de la caméra (§2) au tableau du chapitre 3.
6. **Versions** (note rouge `\adonner` du chapitre 3) : annexe C.
7. **Introduction** : adopter le plan et le ton de l'annexe A (cf. §1).
8. **Distance « 0,269 → 0,106 »** : voir la section « Mesures » (non reproduite par la mesure contrôlée). La ligne « visages proches non testés devant la caméra » est à recouper avec `docs/lab_journal.md` (il contient des confusions observées entre l'auteur et son frère).
   et la ligne « visages proches non testés devant la caméra » (le journal contient des confusions observées entre l'auteur et son frère).
9. **Captures du tableau de bord** : produites le 01/11 dans `docs/images_memoire/` ; les copier dans `memoire/images/` sous ces noms,
   qui sont ceux attendus par les `\imageouplace` : `dashboard_journal.png`, `dashboard_profils.png`, `dashboard_config.png`,
   `dashboard_alertes.png`, `dashboard_couplage.png` (écran de saisie du code). `dashboard_stats.png` est en plus : elle permet d'ajouter
   une figure à la page des statistiques, aujourd'hui décrite en texte seulement.
   **Les légendes doivent dire « données de démonstration »** : les captures viennent d'un serveur simulé (`biogate-dashboard/scripts/mock-api.mjs`),
   avec des noms fictifs (sauf celui de l'auteur) et les réglages par défaut du profil Domicile, pas d'une session réelle.
   **Restent à fournir par l'auteur** : `dashboard_surveillance.png` (il faut la vraie caméra : le serveur simulé n'envoie pas de vidéo, la page
   affiche alors « Flux vidéo indisponible ») et `bw21_carte.jpg` (sa propre carte : le fichier actuel est une photo de vendeur de 225×225 pixels).
   Ne rien inventer à leur place.
10. **Profil « haute sécurité » et vivacité : tranché par l'auteur le 02/11 — le mémoire fait foi.** Haute sécurité = empreinte seule, sans test de vivacité
    (`LIVENESS_ENABLED` à `False` dans `database/db_manager.py`, présent depuis le 21/08). C'est ce que décrit déjà le chapitre 2, donc rien à changer
    dans le texte ni dans le code. Seul le libellé du tableau de bord était faux (« MFA + fingerprint + liveness ») : corrigé en « MFA · Empreinte seule »,
    et celui du profil Bureau en « MFA · Empreinte ou liveness ». La figure `dashboard_config.png` a été refaite avec ces libellés.

---

## 4. Règles pour ce dépôt (public)

- Ne jamais committer : `database/visages.db` (embeddings), `*.db.bak*`, `database/snapshots/`, un jeton Telegram, une clé de flux,
  un mot de passe Wi-Fi ou SMTP, un PIN.
- Photos de test : seulement des images libres de droits, avec leur licence indiquée dans la légende.
- Ne pas fusionner dans `main` ni pousser sans demande de l'auteur.
- Les dépôts sont publics : le texte du mémoire y est lisible avant la soutenance. L'auteur décidera de les passer en privé.

---

## Annexe A — Introduction de référence (style validé)

```latex
\introduction
\markboth{Introduction générale}{Introduction générale}

Le contrôle d'accès vise à réserver l'entrée d'un lieu aux personnes autorisées. Il repose classiquement sur un objet détenu, tel qu'une clé ou un badge, ou sur un secret, tel qu'un code. Ces facteurs authentifient la possession d'un objet ou la connaissance d'une information, et non la personne elle-même : ils peuvent être copiés, prêtés, perdus ou observés. Les systèmes à badge ou à code conservent un historique des passages, mais celui-ci identifie le badge ou le code utilisé, et non son porteur.

La biométrie remplace ces facteurs par une caractéristique propre à l'individu. La reconnaissance faciale a pour avantage de s'effectuer sans contact, à partir d'une simple caméra. Elle repose cependant sur une comparaison statistique dont le résultat est une mesure de ressemblance et non une certitude. La décision d'accès est donc prise sous incertitude et expose à deux types d'erreur : la fausse acceptation, qui admet une personne non autorisée, et le faux rejet, qui refuse une personne autorisée.

\section*{1- Contexte et justification}
Une architecture courante de reconnaissance faciale consiste à transmettre les images à des serveurs distants, où elles sont analysées. Ce modèle est désigné par le terme d'informatique en nuage, ou \gls{cloudcomputing}. Il suppose une alimentation électrique et un accès à Internet continus, et il place les données biométriques hors du contrôle du site qui les produit. Lorsque ces conditions ne sont pas garanties, le service s'interrompt avec la liaison.

Les données biométriques font par ailleurs l'objet d'un encadrement juridique particulier. Le \gls{rgpd} \cite{rgpd2016} classe les données biométriques utilisées pour identifier une personne de façon unique parmi les catégories particulières de données, dont le traitement est en principe interdit sauf exceptions. Au Bénin, la protection des données à caractère personnel est encadrée notamment par la loi n°2009-09 \cite{loi2009benin}. Contrairement à un mot de passe, un visage ne peut pas être remplacé après une fuite, ce qui justifie de limiter sa transmission et sa conservation.

Le traitement en périphérie de réseau, ou \gls{edgecomputing} \cite{shi2016edge}, consiste à analyser les données à proximité de leur source plutôt que dans un centre de données distant. Il réduit la dépendance à la connexion et permet de conserver les images sur le site. Il impose en contrepartie de travailler avec des ressources de calcul limitées \cite{chen2019deep}.

\section*{2- Problématique}
Le contrôle d'accès par reconnaissance faciale pose plusieurs problèmes.

Sur le plan technique, l'analyse des images demande beaucoup de calculs, alors qu'un équipement installé sur place dispose de peu de ressources \cite{chen2019deep}.

Sur le plan de la sécurité, le système peut être trompé par une photographie, une vidéo ou un écran présenté devant la caméra \cite{galbally2014spoofing}.

Enfin, le visage d'un utilisateur change avec le temps, ce qui dégrade la reconnaissance si les références enregistrées ne sont pas mises à jour \cite{pisani2019adaptive}. Or une mise à jour sans contrôle peut faire entrer un inconnu dans la base.

La problématique centrale de ce mémoire peut donc être formulée comme suit : \textit{comment concevoir un système de contrôle d'accès par reconnaissance faciale, exécuté en local selon le principe de l'Edge Computing, qui résiste aux attaques par présentation et reste fiable malgré l'évolution du visage de ses utilisateurs ?}

\section*{3- Objectifs de la recherche}
L'objectif général est de concevoir et de réaliser \textbf{BioGate}, un système de contrôle d'accès par reconnaissance faciale fonctionnant en périphérie de réseau.

Les objectifs spécifiques sont les suivants :
\begin{itemize}
    \item concevoir une chaîne de traitement d'images adaptée aux ressources d'un équipement local ;
    \item définir une règle de décision fondée sur un score de confiance gradué (\gls{trustscore}), qui associe la reconnaissance du visage à un second facteur d'authentification ;
    \item intégrer une détection de vivacité (\gls{livenessdetection}) pour limiter les attaques par présentation ;
    \item encadrer la mise à jour des références biométriques par une confirmation indépendante du visage ;
    \item limiter la transmission et la conservation des données biométriques ;
    \item évaluer le système par des mesures : taux de fausses acceptations et de faux rejets, résistance aux attaques par présentation, temps de traitement et comportement en cas de panne.
\end{itemize}

\section*{4- Organisation du mémoire}
Ce document s'organise en trois chapitres :
\begin{itemize}
    \item Le \textbf{chapitre~1} présente l'état de l'art : les systèmes de contrôle d'accès et leurs limites, le traitement en périphérie, les bases de la reconnaissance de visages et de la détection de vivacité, ainsi que le cadre éthique et légal.
    \item Le \textbf{chapitre~2} analyse les besoins et décrit la conception du système : architecture, chaîne de traitement, règle de décision et mécanismes contre l'usurpation.
    \item Le \textbf{chapitre~3} décrit la réalisation, puis l'évaluation chiffrée du système, ses limites et ses perspectives.
\end{itemize}
```

## Annexe B — Tests automatiques par domaine (172 sur `main`, 180 avec les 8 tests de vivacité de la branche)

| Domaine | Cas | Fichiers |
|---|---|---|
| Alertes à distance | 46 | `test_notifier.py` (27), `test_alerts_api.py` (19) |
| Suppression des messages Telegram | 11 | `test_telegram_purge.py` |
| Filtre de visage | 28 | `test_face_gate.py` |
| Purge des photos | 25 | `test_rgpd_purge.py` |
| Sources vidéo et caméras (flux, affichage, routes) | 37 | `test_camera_sources.py` (7), `test_camera_display.py` (12), `test_camera_api.py` (18) |
| Logique des intrus | 20 | `test_intruder_logic.py` |
| Téléchargement du modèle MediaPipe | 5 | `test_telecharger_modeles.py` |
| Réglage de vivacité (branche) | 8 | `test_liveness_toggle.py` |
| **Total** | **180** | |

## Annexe C — Versions utilisées (environnement `.venv-deepface`)

Python 3.11.15 · OpenCV 4.11.0.86 · FastAPI 0.136.1 · Uvicorn 0.46.0 · Ultralytics 8.4.47 (YOLOv8) · DeepFace 0.0.99 ·
MediaPipe 0.10.35 · TensorFlow 2.21.0 · NumPy 2.4.4 · Requests 2.33.1
