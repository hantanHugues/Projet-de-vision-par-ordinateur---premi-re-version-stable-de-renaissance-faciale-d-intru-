# Plan de finalisation BioGate — du prototype à la soutenance
*Créé le 28/10/2026. Décision prise : option A (problématique centrée sur la logique de décision biométrique ; IoT complet et Raspberry Pi en perspectives). Informations détaillées du mémoire : voir `BRIEF_REDACTIONNEL_MEMOIRE.md`.*

**Date de soutenance : ____ / ____ / 2026   |   Remise du mémoire : ____ / ____ / 2026**
(à remplir en premier : tout le calendrier en dépend)

---

## ÉTAT D'AVANCEMENT (mis à jour le 02/11/2026)

| Étape | État | Reste à faire |
|---|---|---|
| Dates soutenance / remise | ❌ À remplir | Les noter en haut de ce fichier : tout le calendrier en dépend |
| 1.1 Alertes Telegram + e-mail | ✅ Telegram réel testé (message de test reçu, puis supprimé par la nouvelle route le 01/11) ; 57 tests d'alertes | **E-mail jamais essayé en réel** (mot de passe d'application Google) ; alerte avec photo en réel (voir « Recette finale ») ; **révocation du jeton Telegram** en fin de projet |
| Suppression automatique des messages Telegram (01/11) | ✅ 24 h par défaut, plafond 47 h (l'API refuse au-delà de 48 h), route `POST /alerts/telegram/purge`, table `telegram_messages` (6e table), essai réel concluant | Le chemin avec photo n'est couvert que par des tests automatiques ; les anciens messages restent dans la conversation |
| 1.2 Bug Haar en double | ✅ Corrigé et mesuré (−48 % à −78 %) | |
| 1.3 Purge RGPD automatique | ✅ Vérifiée en réel (29/10 : 41 photos ; 01/11 : 9 expirées et 1 orpheline au démarrage) | |
| 1.4 Carte BW21-CBV | ✅ Flux protégé stable, lu par BioGate (640x480, 17 à 30 images/s), reconnaissance et vivacité validées sur ce flux ; défauts de la bibliothèque contournés et documentés | **Écran LCD : reporté à la toute fin** ; mesure FPS et latence ; photo de la carte pour le mémoire ; bande Wi-Fi à trancher (l'auteur dit 5 GHz, le journal note 2,4 GHz canal 1) ; reprise après coupure Wi-Fi jugée évidente par l'auteur, non testée (à écrire comme telle) |
| 1.5 Hygiène des dépôts | 🟡 Presque fini | ✅ `requirements.txt` corrigé et vérifié dans un environnement neuf (un seul OpenCV cohérent, 167 tests), ✅ `telecharger_modeles.py` (modèle MediaPipe ignoré par git, empreinte vérifiée), ✅ README (étape 4), ✅ tout poussé. **Reste** : script de lancement unique, README du dépôt du tableau de bord à relire |
| 1.6 Robustesse de la démo | ⬜ À faire | Profils propres, vidéo de secours, démo après redémarrage à froid |
| 1.7 Routes sans jeton | ⬜ À décider | 37 routes, 26 avec jeton, 11 sans. **Recommandé : option A** (protéger `/config/templates` et `/config/apply_template`), le reste assumé comme limite |
| Faux visages, faux intrus, compteur d'intrus (29/10) | ✅ Corrigés, poussés, validés en direct | Retester la chemise à la webcam ; le frère est hors des tests finaux |
| Reconnaissance dans une pièce sombre (02/11) | ✅ Observé : 39 re-confirmations de `Ash` en 46 s, distance moyenne 0,178, toutes sous 0,35, accès accordé | À citer comme observation d'une séance |
| Profil « Haute sécurité » (02/11) | ✅ Tranché : empreinte seule, sans vivacité, comme le mémoire ; libellés du tableau de bord corrigés | |
| Apprentissage par empreinte | ✅ **Trois preuves** : (1) 150 sujets de LFW, 47,8 % → 71,6 % reconnus, fausses acceptations 0,1 % → 0,3 %, un apprentissage erroné fait accepter 47,9 % des photos de l'inconnu ; (2) **38 personnes de 6 régions, deux sexes, photos datées (écart moyen 16 ans) : 34,2 % → 60,5 % reconnues, p = 0,002** ; (3) à la webcam, première lecture de nuit 0,209 → 0,203, pire image 0,436 → 0,274. La baisse « 0,269 → 0,106 » du journal n'est pas reproduite | Seconde lecture à la webcam en journée, bien face à la caméra et sans contre-jour ; écrire les trois mesures avec leurs limites (aucun visage vérifié à la main pour la mesure de vieillissement) |
| Caméra IP protégée, miroir, bouton « Modifier », clé masquée | ✅ Poussés (backend et tableau de bord) | |
| Images du mémoire | ✅ Six captures du tableau de bord en données de démonstration (`docs/images_memoire/`) + **la page de surveillance réelle, fournie par l'auteur le 02/11** | **Manque** : photo de la carte BW21 (la sienne, ou une photo du fabricant avec sa source) |
| 2.1 Anti-spoofing | ⬜ **À faire, priorité haute** | 20 essais photo, 20 vidéo, 20 légitimes, avec l'auteur, environ 1 h |
| 2.2 FAR / FRR | ✅ **Fait le 01/11** sur LFW (1 000 paires) : au seuil 0,35, **FAR 0,0 %, FRR 52,0 %** ; égalité des erreurs 13,1 % au seuil 0,74 ; aire ROC 0,931 (`docs/mesures/far_frr/`). **Écart éclairci en partie le 02/11** (1 429 images, 3 variantes) : ni Haar ni CLAHE n'expliquent l'écart (aires ROC 0,919 / 0,921 / 0,924). **Filtre de visage selon la région et le sexe (04/11, descriptif)** : un visage de face validé sur 20,6 % à 42,4 % des photos selon la région, 33,8 % (femmes) contre 25,1 % (hommes) ; MediaPipe seul suit le même ordre | Restent non testés : détecteur et alignement de DeepFace, protocole des paires ; écrire « écart non expliqué » ; filtre de visage : limite et perspective, à tester sur des visages variés en conditions réelles (ne pas conclure à un biais) |
| 2.3 Performance | ✅ **Fait le 02/11** (`docs/mesures/performance/`) : identification 401 ms (≈ 2,5 images/s), régime stable médiane 30 ms et jusqu'à 18,3 images/s, YOLO 320 px 2,1 fois plus rapide que 640 px, cache en mémoire 46 fois plus rapide que SQLite à 1 600 vecteurs, décision résident 0,45 s, endurance de 5 minutes sans dégradation ni fuite | Corriger le mémoire (« 2 à 5 images/s » venait d'un commentaire) ; limites : scène fixe, une machine, pas de Raspberry Pi ; la latence caméra → écran n'est pas mesurée de bout en bout |
| 2.4 Résilience | ⬜ À faire | Serveur tué puis relancé, coupure d'Internet pendant une alerte |
| 3. Mémoire | 🟡 **Branche du téléphone** `claude/memoire-latex-telephone-h1vdti` : 66 pages, introduction, chapitres 1 à 3, conclusion, résumé ; corrections du brief reportées ; FAR/FRR rédigé ; réponses du poste dans `docs/REPONSES_AU_TELEPHONE.md` | Page de garde, remerciements, dédicace, captures manquantes, coût, annexes, mots clés (décisions de l'auteur, liste dans `memoire/QUESTIONS_ET_MANQUES.md`) ; corriger Face ID (caméra de profondeur) ; **fusionner `main` dans la branche puis relancer les tests (180 attendus)** ; relecture du chapitre 1 ; décision sur la mention des assistants d'IA |
| 4. Soutenance | ⬜ À faire | Diapositives, démo chronométrée, vidéo de secours, répétitions |

**Git au 02/11** : tout est **poussé** sur `main` (backend `c0a3513`, tableau de bord `e70e53f`). Aucun travail en attente. Tests : **172 réussis** sur `main` (180 attendus une fois les 8 tests de vivacité de la branche du mémoire fusionnés). La branche du mémoire n'est pas fusionnée dans `main`. **Les deux dépôts sont publics** : le texte du mémoire y est lisible avant la soutenance (décision de l'auteur : les passer en privé ou non).

---

## 0. Problématique retenue (à coller dans l'intro et la conclusion)

> **Comment contrôler l'accès à un lieu par reconnaissance faciale, sans passer par le cloud, tout en empêchant l'usurpation et en acceptant que les visages changent avec le temps ?**

Titre officiel (cahier des charges, à garder s'il est validé par Mr KIKI) : *Conception et implémentation d'une infrastructure de contrôle d'accès biométrique intelligente par vision artificielle et architecture Edge Computing : le système BioGate*.

Trois questions qui structurent le mémoire :
1. Comment faire tourner l'IA en local, sans matériel puissant ?
2. Comment empêcher qu'une photo ou une vidéo ouvre la porte ?
3. Comment suivre l'évolution des visages sans risquer d'apprendre un intrus ?

Réponse en 4 contributions :
1. **Cascade IA économe** (FaceGate, cache RAM, YOLO à 320 px, NMS maison, Color Re-ID HSV) qui tourne en local.
2. **Trust Score gradué** 20 % → 60 % → 85 % → 100 % et MFA empreinte/liveness en parallèle.
3. **Liveness aléatoire** (geste, nombre de clignements et durée du sourire tirés au sort) contre le rejeu vidéo.
4. **Apprentissage validé par preuve forte** : un visage n'entre en base que si l'empreinte l'a confirmé (test Chris Evans : 0.47 → 0.22).

Limites assumées (à dire d'emblée, ça désarme le jury) : tourne sur PC, actionneurs simulés (mock), empreinte simulée par un bouton, pas de test sur Raspberry Pi.

---

## 1. FINIR LE PROTOTYPE

Ordre conseillé. Chaque tâche a un critère « fini quand ».

### 1.1 Alertes Telegram + e-mail (remplace WhatsApp)   ✅ FAIT le 28/10/2026
Telegram validé avec un vrai message de test. **Reste à faire, regroupé dans la « Recette finale » en bas de ce fichier** : intrusion réelle avec photo, e-mail (mot de passe d'application Google), révocation du jeton Telegram.
Ce qui a été réalisé : `core/notifier.py`, routes `/alerts/test` et `/alerts/telegram/detect`, secrets masqués, photo d'intrus reliée à l'alerte (elle n'existait pas), page Alertes réécrite, 44 tests automatiques + 25 vérifications navigateur, docs mises à jour. Texte d'origine de la tâche conservé ci-dessous.
- [ ] Créer un bot via @BotFather → noter le token ; récupérer le `chat_id` (envoyer un message au bot puis lire `getUpdates`).
- [ ] Backend : fonction d'envoi `sendPhoto` (requête HTTPS vers l'API Bot, dans un thread pour ne pas bloquer), déclenchée quand un intrus est **confirmé** (après la fenêtre de grâce de 60 s). À localiser dans `api.py` (logique `ALERT_GRACE_PERIOD`).
- [ ] `config.py` : remplacer `WHATSAPP_*` par `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ALERT_TELEGRAM_ENABLED`.
- [ ] **Sécurité** : `GET /config` ne doit jamais renvoyer le token en clair (le masquer).
- [ ] Front, onglet Alertes : remplacer les champs « numéro / clé API » par « token du bot / chat id », avec un bouton « Envoyer un message test ».
- [ ] Fini quand : un intrus devant la caméra → photo reçue sur ton téléphone ; l'alerte est annulée si un VIP est reconnu dans les 60 s.

### 1.2 Bug Haar en double   ✅ FAIT le 28/10/2026
Résultat : `identify()` mémorise la position du visage, `api.py` la réutilise (`get_face_box`) ; 2 → 1 détection par image en identification, 1,28 → 0,24 en régime stable. Mesures dans `tests/rapport_face_gate.md` (à reprendre dans le chapitre 3, tableau avant/après de la section 2.3 : cette ligne est faite), tests dans `tests/test_face_gate.py`, journal entrée 018. Texte d'origine de la tâche conservé ci-dessous.
- [ ] Vérifier dans `face_recognizer.identify()` que Haar est bien lancé aussi à cet endroit.
- [ ] Faire retourner les coordonnées du visage par `identify()` et les réutiliser dans `api.py:429` (supprimer la 2e détection).
- [ ] Mesurer le temps par frame avant/après (réutilisable dans le tableau du chapitre 3).
- [ ] Fini quand : une seule détection Haar par personne et par frame ; `erreur.md` mis à jour (point 1 résolu).

### 1.3 Purge RGPD automatique   ✅ FAIT le 28/10/2026
Résultat : tâche de fond au démarrage puis toutes les heures ; elle supprime les photos expirées et orphelines mais **garde le journal** (le réglage s'appelle « Rétention snapshots » et les statistiques/alertes sur 30 jours en dépendent). La purge manuelle du Journal reste plus radicale (événements + photos) et son texte l'explique. Découvertes : 41 photos de 107 à 128 jours jamais purgées, coupure calculée en heure locale au lieu d'UTC, routes du journal sans jeton (corrigé). Statut visible dans Configuration. Journal entrée 019. Texte d'origine de la tâche conservé ci-dessous.
- [ ] Au démarrage de l'API, lancer une tâche de fond qui appelle `purge_old_snapshots()` toutes les heures (retention 72 h déjà dans `config.py`).
- [ ] Fini quand : un snapshot plus vieux que 72 h disparaît sans aucun clic (tester en mettant la rétention à 1 min).

### 1.4 Carte Ai-Thinker BW21-CBV + écran LCD   ~1 à 3 jours (le plus incertain)
- [ ] Flasher un exemple de streaming vidéo du SDK Arduino (vérifier dans les exemples : RTSP ou MJPEG) ; noter l'URL du flux.
- [ ] Ajouter la caméra dans le dashboard (page Config → Caméras, type `rtsp` ou `mjpeg`) ; vérifier la reconnaissance sur ce flux.
- [ ] Mesurer FPS et latence avec cette caméra (donnée réelle d'architecture Edge).
- [ ] LCD : définir un mini-protocole, par exemple `GET http://IP_CARTE/lcd?text=...`. Messages minimum : « Bienvenue <nom> », « Souriez », « Clignez 3 fois », « Accès refusé ».
- [ ] Backend : envoyer le texte au LCD à chaque changement d'état du Trust Score et au démarrage d'un challenge liveness (passer par `IoTController`, comme les autres actionneurs, avec mock si désactivé).
- [ ] Tester le liveness avec cette caméra : le client OpenCV à 30 fps n'est plus dans la boucle, donc le repli serveur à 5 fps est utilisé. Noter le taux de réussite d'un vrai clignement et d'un vrai sourire.
- [ ] Plan B si le firmware bloque : garder la webcam, présenter la carte comme « nœud de capture prévu, flux testé sans reconnaissance », et dire où ça a coincé.
- [ ] Fini quand : un visage reconnu sur le flux de la carte, avec le message correspondant sur l'écran.

### 1.5 Hygiène du dépôt et du livrable   ~2 h   🟡 presque fini (voir le tableau d'état)
- [x] `requirements.txt` (fait le 01/11) : deux paquets OpenCV fixés à la même version (mediapipe exige `-contrib`, deepface et ultralytics `opencv-python`), `retina-face` à 0.0.17, versions des essais ; installation testée dans un environnement neuf, 167 tests réussis. Plus `telecharger_modeles.py` pour le modèle MediaPipe.
- [x] `README.md` du backend : installation en 4 étapes avec `uv`, Python 3.11 (fait). [ ] README du dépôt du tableau de bord à relire.
- [ ] Un script de lancement unique (backend + dashboard).
- [ ] Mettre à jour `docs/` : entrées de journal pour liveness v3, MFA parallèle, Telegram, carte BW21 ; réconcilier l'historique du seuil (0.20 → 0.23 → 0.35 : une évolution datée).
- [ ] Commit et push des deux dépôts après chaque tâche. Vérifier avant chaque push que `visages.db` et les `.bak` ne partent pas.

### 1.6 Robustesse de la démo   ~2 h
- [ ] Préparer 3 à 5 profils VIP propres (toi, un proche) et un « intrus » de démo.
- [ ] Faire une **vidéo de secours** de la démo complète (écran + caméra) au cas où le matériel ou le réseau lâche le jour J.
- [ ] Tester la démo sur une 2e machine, ou au moins après un redémarrage à froid.
- [ ] Prévoir : ordinateur de secours, câbles, routeur, alimentation de la carte.

---

### 1.7 Routes encore sans jeton (découvert le 28/10, à décider)   ~1 à 3 h selon l'option
L'entrée 016 du journal laissait entendre que toutes les routes sensibles exigent le jeton. Ce n'est pas le cas : le jeton a été ajouté le 28/10 aux routes du journal et de la purge, mais restent ouvertes, parce qu'elles sont appelées par le client OpenCV ou les ESP32 qui n'envoient aucun jeton : `/analyze_frame`, `/enroll` (**enrôler un visage donne un accès physique**), `/fingerprint_result` (**un simple appel avec `success=true` accorde l'accès**), `/request_liveness`, `/liveness_result`, `/access_status`, `/config/apply_template` et `/config/templates`.
- [ ] **Option A, minimale** : protéger `/config/apply_template` et `/config/templates` (seul le dashboard les appelle, il envoie déjà son jeton). Garder le serveur lié à `127.0.0.1` pour la démo. Assumer le reste comme limite dans le mémoire : réseau local fermé, authentification d'équipement en perspective.
- [ ] **Option B, complète** : une clé d'équipement partagée (en-tête) pour le client OpenCV et les ESP32, exigée sur `/analyze_frame`, `/enroll`, `/fingerprint_result`, `/request_liveness`, `/liveness_result`, `/access_status` ; le jeton du dashboard reste accepté. Demande de modifier `client_camera.py` et le futur firmware.
- Recommandation : A tout de suite, B si le temps le permet (c'est la première question qu'un jury IoT posera sur la sécurité). Dans tous les cas, le dire dans le chapitre sécurité.

---

## 2. MESURES POUR LA SECTION 3.3 « TESTS ET RÉSULTATS » DU MÉMOIRE (tout est gratuit)

Noter le matériel de test : modèle du PC, processeur, RAM, système, versions de Python / PyTorch / DeepFace.

### 2.1 Anti-spoofing   ~1 h
- [ ] Attaque photo : photo de toi sur un téléphone devant la caméra, 20 essais, avec le liveness actif. Noter combien passent (objectif : 0).
- [ ] Attaque vidéo : vidéo de toi qui sourit/cligne sur le téléphone, 20 essais. Noter le taux de réussite de l'attaque (honnêteté > perfection).
- [ ] Contrôle : 20 essais légitimes (toi, vrai geste) → taux de réussite normal. Mesurer le temps moyen.
- [ ] Table : type d'attaque / essais / réussies / taux.

### 2.2 FAR / FRR et choix du seuil   ✅ FAIT le 01/11/2026 (protocole B ; reste l'explication de l'écart)
Résultat : au seuil 0,35, FAR 0,0 % et FRR 52,0 % sur 1 000 paires de LFW ; point d'égal taux d'erreur 13,1 % au seuil 0,74 ; aire ROC 0,931. Fichiers : `docs/mesures/far_frr/`. Le FRR élevé tient à des photos non contrôlées comparées à un seul échantillon (BioGate en compare plusieurs) ; l'écart avec les performances publiées de FaceNet **n'est pas expliqué**. Pistes à tester : sans CLAHE, sans recadrage de Haar, détecteur et alignement de DeepFace, normalisation.
- [ ] FAR = faux acceptés (un inconnu reconnu comme VIP) ; FRR = faux rejetés (un VIP refusé).
- [ ] Protocole A (réaliste) : 5 à 10 personnes enrôlées (toi, proches, ou photos libres) ; comparer chaque personne à elle-même (essais légitimes) et aux autres (essais imposteurs).
- [x] Protocole B (gratuit, standard) : paires LFW (`pairsDevTest.txt`), embeddings FaceNet512, distances cosinus. Fait.
- [x] Calculer FAR et FRR pour des seuils de 0.20 à 0.60 ; courbe FAR/FRR ; seuil 0.35 marqué. Fait.
- [ ] Fini quand : une figure justifie 0.35 par les données. **Partiel** : la figure existe, mais elle montre un seuil prudent (FAR nul) et un FRR élevé sur LFW ; il faut l'expliquer, pas seulement la montrer.

### 2.3 Performance (tableau avant/après)   ~2 h
- [ ] Mesurer en ms/frame : sans cache RAM vs avec ; sans FaceGate vs avec ; YOLO à 640 vs 320 ; sans NMS maison vs avec ; Haar double vs simple.
- [ ] Latence de bout en bout (visage devant la caméra → porte « OPEN » dans le dashboard).
- [ ] FPS du flux ; CPU et RAM pendant un test de 5 minutes.
- [ ] Compléter les estimations de `notes_projet.md` (FaceNet 100-300 ms) avec tes vraies mesures.

### 2.4 Résilience (sans matériel)   ~1 h
- [ ] Tuer le backend en plein fonctionnement puis le relancer : état de la porte au redémarrage (doit être verrouillée = fail-secure), profils conservés.
- [ ] Couper le réseau/la caméra : comportement affiché dans le dashboard.
- [ ] Redémarrage automatique après coupure : documenter (même si c'est « à faire » côté Pi, avec la carte et un Mini-UPS en perspective).

### 2.5 Test déjà fait
- [x] Apprentissage continu Chris Evans (0.4722 → 0.224, seuil 0.35) : changement d'apparence réel sur trois photos datées. [x] Fait le 02/11 : 150 sujets de LFW (`docs/mesures/apprentissage_lfw/`). [x] **Fait le 04/11 : 38 personnes de 6 régions et des deux sexes avec photos datées de Wikimedia Commons** (`docs/mesures/vieillissement/`) : 34,2 % → 60,5 % reconnues, McNemar p = 0,002, robuste aux critères d'identité ; limites : aucun visage vérifié à la main, célébrités, effectifs de 4 à 8 par région.
- [x] Première lecture à la webcam, de nuit (02/11, chaîne de BioGate, 78 images) : moyenne 0,209 → 0,203, pire image 0,436 → 0,274, images au-dessus du seuil 2 → 0. La baisse « 0,269 → 0,106 » du journal n'est **pas** reproduite. Détails : `docs/mesures/apprentissage_webcam/`.
- [ ] **Seconde lecture en journée, en pleine lumière, sur le poste de l'auteur** (même script, serveur arrêté) pour confirmer les valeurs.

---

## 3. RÉDACTION DU MÉMOIRE

Ordre conseillé (le plus facile et le plus utile d'abord) :

1. [x] **Nettoyage** : fait dans la branche du téléphone (gabarit IFRI, bibliographie, annexe du projet IPv6 retirée).
2. [x] **Introduction** : réécrite le 30/10 puis au style des mémoires de référence (contexte, problématique en un paragraphe, objectifs, organisation). Reportée dans la branche du téléphone.
3. [x] **Chapitres 1, 2 et 3** (sections 3.1 à 3.4 incluses) rédigés dans la branche du téléphone ; corrections du brief reportées (caméra, Telegram, 37 routes, six tables, tests, FAR/FRR, défauts, limites). **Le mémoire a 3 chapitres, il n'y a pas de chapitre 4.**
4. [x] **Section « Taux de fausse acceptation et de faux rejet »** rédigée avec les chiffres du 01/11. [ ] Restent à rédiger : anti-spoofing (2.1), performance (2.3), résilience (2.4), quand les mesures existent.
5. [x] **Conclusion** et **résumé / abstract** : premiers jets dans la branche. [ ] À reprendre quand les mesures restantes sont faites.
6. [ ] **Corrections connues** : Face ID a une caméra de profondeur (TrueDepth) ; ne pas écrire la bande Wi-Fi ; distance « 0,269 → 0,106 » à présenter comme relevé du journal ; plage « 0,23 à 0,35 » entre profils à présenter comme observation en direct.
7. [ ] **À fournir par l'auteur** : page de garde (option, grade, année, jury, date), dédicace, remerciements, mots clés, coût du prototype, annexes, décision sur la mention des assistants d'IA, photo de la carte, capture de surveillance.
8. [ ] **Fusion** : ramener `main` dans la branche, relancer les 180 tests, compiler, relire (chapitre 1 à alléger), puis décider de la fusion dans `main`.

**Figures et tableaux à produire :**
- [ ] Architecture globale (caméra BW21 + LCD, serveur Edge, dashboard, actionneurs ESP32 en perspective)
- [ ] Pipeline IA en cascade
- [ ] Machine à états du Trust Score
- [ ] Schéma du réseau LAN fermé + Mini-UPS
- [x] Captures du dashboard : Journal, VIP, Config, Stats, Alertes, Couplage faites (données de démonstration) ; [x] Surveillance : capture réelle fournie par l'auteur le 02/11
- [ ] Capture de l'alerte Telegram reçue
- [x] Courbe FAR/FRR (`docs/mesures/far_frr/far_frr.png`), test Chris Evans. [ ] Table anti-spoofing, tableau avant/après des optimisations
- [ ] Photo du montage réel (carte + LCD)

**Bibliographie minimale** : YOLOv8 (Ultralytics), FaceNet (Schroff et al., 2015), DeepFace (Serengil & Ozpinar), LFW (Huang et al., 2008), MediaPipe FaceLandmarker (Google), OpenCV, FastAPI, texte sur l'Edge Computing, texte de loi sur la protection des données (RGPD ; loi béninoise à citer après vérification du numéro exact).

**Livraison** : compiler le PDF final, vérifier la pagination, les images et la table des matières ; prévoir les délais d'impression et de reliure.

---

## 4. PRÉPARATION DE LA SOUTENANCE

### 4.1 Structure de l'exposé (adapter à la durée imposée)
1. Contexte et problème (SBEE, cloud, vie privée)
2. Problématique et contributions
3. Architecture (matériel + logiciel)
4. Pipeline IA et choix justifiés
5. Sécurité : Trust Score, liveness, MFA, apprentissage validé
6. Démo en direct
7. Résultats chiffrés (FAR/FRR, anti-spoofing, performance, Chris Evans)
8. Limites assumées et perspectives (Raspberry Pi, quantization, ESP32 réels, Mini-UPS)
9. Conclusion

### 4.2 Script de démo (5 minutes maximum, chronométré)
VIP reconnu → Trust 60 % → défi liveness (message sur le LCD) → accès → intrus → alerte Telegram → dashboard (journal, stats). Vidéo de secours prête.

### 4.3 Questions probables du jury — réponses à préparer
- Pourquoi pas le cloud ? (vie privée, coupures, latence, coût)
- Pourquoi FaceNet512 et la distance cosinus ? Pourquoi un seuil de 0.35 ? (réponse : courbe FAR/FRR)
- Que se passe-t-il avec une photo, une vidéo, un masque 3D ? (liveness aléatoire, chiffres ; limite : pas de capteur de profondeur)
- Que fait le système en cas de coupure de courant ? (fail-secure ; Mini-UPS prévu, non testé)
- Pourquoi HTTP et pas MQTT ? (LAN fermé, sans broker, simplicité ; limite : pas d'authentification sur les ESP32 → perspective prioritaire)
- Pourquoi pas sur Raspberry Pi ? (FaceNet512 lourd ; architecture prévue : détection sur la carte, FaceNet sur le serveur ; quantization ONNX/TFLite)
- Où est votre contribution, puisque vous utilisez des modèles existants ? (l'intégration, le Trust Score, le Color Re-ID, le liveness aléatoire, l'apprentissage validé, la cascade économe)
- Les données biométriques : où, comment protégées, combien de temps ? (local, base hors dépôt, snapshots purgés à 72 h, jeton chiffré côté dashboard)
- Qu'est-ce qui est réel et qu'est-ce qui est simulé ? (réponse franche : caméra, IA, API, dashboard, alertes = réels ; porte, empreinte, éclairage = simulés)
- Combien ça coûte ? À quoi ça sert au Bénin ? Passage à l'échelle ?

### 4.4 La veille
- [ ] Répétition complète chronométrée (au moins 2 fois), avec un auditeur qui pose des questions.
- [ ] Sauvegardes : mémoire PDF, code (clé USB + GitHub), vidéo de démo, diapositives en PDF.
- [ ] Vérifier le matériel et le réseau de la salle, prévoir un partage de connexion.

---

## 5. ORDRE GLOBAL ET TEMPS ESTIMÉ

| Phase | Contenu | Temps |
|---|---|---|
| 0 | Fixer les dates | 15 min |
| 1.2, 1.3 | Haar, purge automatique | 2 h |
| 1.1 | Telegram | 3 h |
| 2.1 à 2.4 | Mesures (anti-spoofing, FAR/FRR, perf, résilience) | 1 à 2 jours |
| 1.4 | Carte BW21 + LCD | 1 à 3 jours |
| 1.5, 1.6 | Hygiène, démo, vidéo de secours | 4 h |
| 3 | Rédaction du mémoire | 5 à 8 jours |
| 4 | Diapositives, répétitions | 2 à 3 jours |

## 6. RECETTE FINALE (à faire en fin de projet, avec le vrai matériel et les vrais comptes)

### VERSION SIMPLE (29/10) : 3 tests à la webcam, environ 15 minutes
Déjà validés, rien à refaire : message de test Telegram, purge RGPD au démarrage (41 photos supprimées), 97 tests automatiques, affichage du dashboard.
- [x] **Étape 0** : **annulée** (30/10) : `Nadish` est le frère de l'utilisateur, pas un doublon de `Ash`. Ne rien supprimer.
- [x] **Test 1** : visage visible devant la caméra → un cadre avec son nom, jamais « Intrus ». ✅ Revalidé le 02/11 sur le serveur réel (pièce sombre) : 39 re-confirmations de `Ash` en 46 s, aucun intrus.
- [x] **Test 2** : main ou torse devant l'objectif, puis partir → lignes `[PASSAGE]` au journal, aucun faux intrus (29 et 30/10).
- [ ] **Test 3** : 🟡 la chaîne a été validée (alertes Telegram envoyées le 29/10 à 16:18 et 16:36). Reste : fenêtre de grâce à 15 s, une personne non enrôlée visage visible, et **confirmer que la photo reçue montre bien un visage**.

À garder pour la toute fin du projet : test de l'e-mail (R3), révocation du jeton Telegram (R6), choix sur les routes sans jeton (section 1.7), démo chronométrée (R7), coupure d'Internet (R8). Le détail R1 à R9 ci-dessous reste la référence complète.

Tests réels que les tests automatiques ne remplacent pas. Le serveur et le dashboard doivent tourner (`python -m uvicorn api:app --host 127.0.0.1 --port 8000` puis `npm run dev`).

- [ ] **R1 — Intrusion réelle, Telegram** : fenêtre de grâce réglée à 10 s (Configuration), une personne non enrôlée reste devant la caméra → message « ALERTE BioGate — intrus confirmé » **avec la photo** sur Telegram, et une ligne dans l'onglet Alertes avec le nom du fichier.
- [ ] **R2 — Fausse alerte annulée** : un VIP est d'abord pris pour un intrus puis reconnu dans la fenêtre de grâce → **aucune alerte** reçue, et **aucune photo** ne reste dans `database/snapshots/` (conformité RGPD).
- [ ] **R3 — E-mail** : créer le mot de passe d'application Google, saisir les réglages dans l'onglet Alertes, « Envoyer un test », puis une intrusion réelle → e-mail reçu avec la photo en pièce jointe.
- [ ] **R4 — Deux canaux et délai minimal** : Telegram et e-mail activés ensemble → les deux reçoivent l'alerte ; deux intrusions à moins de 30 s → une seule alerte.
- [ ] **R5 — Persistance** : redémarrer le serveur → jeton, canaux activés et réglages conservés ; l'API ne renvoie jamais le jeton en clair.
- [ ] **R6 — Nettoyage** : révoquer le jeton Telegram (`/revoke` dans @BotFather), ressaisir le nouveau dans le dashboard, remettre la fenêtre de grâce à la valeur voulue (60 s en profil Domicile).
- [x] **R9 — Purge RGPD réelle** *(faite : 41 photos le 29/10, 9 expirées et 1 orpheline le 01/11)* : redémarrer le serveur (il faudra se ré-appairer avec un PIN : d'après le code, le jeton du dashboard n'est conservé qu'en mémoire côté serveur) → le journal du serveur affiche `[RGPD] Purge automatique : … orpheline(s) supprimée(s)` (attendu : 41), `database/snapshots` ne contient plus de photo de plus de 72 h, Configuration → « Purge automatique » montre la dernière purge, et le Journal, les Statistiques et les Alertes s'affichent toujours (le jeton est maintenant exigé).
- [ ] **R7 — Démo complète chronométrée** (script de la section 4.2), puis vidéo de secours.
- [ ] **R8 — Sans Internet** : couper la connexion pendant une intrusion → l'alerte distante échoue proprement (visible dans le journal du serveur), la lumière et le journal local continuent. À citer comme résultat de résilience dans le mémoire.

---

**Règle** : si le temps manque, couper dans cet ordre : 1.4 (carte, plan B prévu) → 2.4 (résilience) → 1.1 (Telegram). Ne jamais couper : 2.1 (anti-spoofing), 2.2 (FAR/FRR), 3 (mémoire) et la répétition.
