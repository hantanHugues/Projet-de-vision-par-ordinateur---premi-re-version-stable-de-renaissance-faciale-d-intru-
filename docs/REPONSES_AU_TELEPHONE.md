# Réponses du poste de développement à `memoire/QUESTIONS_ET_MANQUES.md`

Écrit le 02/11/2026. Même numérotation que le document de la branche. Légende : ✅ répondu et vérifié sur le poste ;
⚠ réponse partielle ou à nuancer ; 👤 donnée ou décision de l'auteur, que le poste ne peut pas fournir.
Avant de continuer : `git fetch origin && git merge origin/main` (le brief `docs/BRIEF_MEMOIRE.md` a été mis à jour plusieurs fois).

---

## A. Ce que seul l'auteur peut fournir

| Point | État | Réponse |
|---|---|---|
| A1 Page de garde | 👤 | Option, grade de M. KIKI, année, jury, date de soutenance : non fournis. Les dates de soutenance et de remise ne sont toujours pas connues. |
| A2 Dédicace, remerciements | 👤 | Premier jet possible si l'auteur le demande. |
| A3 Images | ⚠ | Déposées dans `docs/images_memoire/` : `dashboard_journal.png`, `dashboard_profils.png`, `dashboard_config.png`, `dashboard_alertes.png`, `dashboard_couplage.png` (écran de saisie du code), et `dashboard_stats.png` en plus (permet une figure pour la page des statistiques). À copier dans `memoire/images/`. Ce sont des **données de démonstration** (serveur simulé) : le dire dans les légendes. **Manquent** : `dashboard_surveillance.png` (il faut la vraie caméra) et `bw21_carte.jpg`. L'auteur a envoyé une photo du kit (carte, objectif, antenne) : à lui de confirmer que c'est la sienne ; sinon la légende doit citer la source. |
| A4 Attaques photo et vidéo | 👤 | Non faites. Protocole du plan : photo imprimée, photo sur téléphone, vidéo sur téléphone, 20 essais chacune, plus 20 essais légitimes ; environ une heure avec l'auteur. À défaut, retirer « résistance aux attaques par présentation » de l'objectif d'évaluation. |
| A5 Suite de tests | ✅ | `main` : **172 réussis**. La branche (175) a été lancée sur une copie propre dans un environnement neuf : tout passe, **à condition que le modèle MediaPipe soit présent** (`python telecharger_modeles.py`, sinon le test de la chemise échoue). Après fusion de `main` : 180 attendus ; relancer la commande du brief et écrire le résultat réel. |
| A6 Fenêtre de grâce | ✅ | **60 s** dans la base réelle (valeur enregistrée le 30/10). « Pas encore réduite » (entrée 023) et le mémoire sont exacts. |
| A7 Mots clés | 👤 | La proposition convient techniquement ; décision de l'auteur. |
| A8 Coût | 👤 | Montants et monnaie à fournir. |
| A9 Annexes | 👤 | Choix de l'auteur. La liste des 37 routes et la procédure de mise en service de la carte sont prêtes à reprendre (chapitre 2, brief). |

## B. Contradictions et incompréhensions

- **B1 — FRR de 52 % : ⚠ éclairci en partie (02/11).** La chaîne du script est celle de BioGate (comparée au code de production : écart 1,2e-07). Trois variantes testées sur les mêmes 1 429 images de LFW (`docs/mesures/apprentissage_lfw/`) : aires ROC presque identiques (0,919 ; 0,921 ; 0,924), donc **ni Haar ni CLAHE n'expliquent l'écart** avec les performances publiées. Au seuil fixe de 0,35, CLAHE ajoute environ 8 points de FRR sur ces photos bien éclairées (51,4 % contre 43,7 % sans CLAHE) ; ce n'est pas un argument contre CLAHE pour la webcam (non testé). Le point d'égal taux d'erreur se situe vers le seuil 0,71 : 0,35 est un seuil très prudent sur LFW. Restent non testés : le détecteur et l'alignement de DeepFace, et le protocole des paires. Écrire : « écart non expliqué, la correction de contraste et le recadrage de Haar n'en sont pas la cause ».
- **B2 — Haute sécurité : ✅ tranché par l'auteur (02/11).** Empreinte seule, sans vivacité, **comme le décrit déjà le mémoire**. Ne rien changer au code, au tableau des profils ni aux tests. Le libellé du tableau de bord était faux (« MFA + fingerprint + liveness ») : corrigé, avec celui du profil Bureau. La correction de la branche (`liveness_channel_active`) reste valable.
- **B3 — `TRUST_FACE_THRESHOLD` : ✅ confirmé inutilisé.** Il est seulement copié dans les profils (`database/db_manager.py`, ligne 577) ; aucune logique ne le lit. `STATE_FACE_MATCHED` est défini et cité (`core/trust_score.py` ligne 82, affichage du client) ; je n'ai pas vérifié qu'il est « traversé instantanément ». Consigne de l'auteur : ne pas compliquer le code. Ne rien retirer ; le mentionner seulement si utile.
- **B4 — Distance 0,269 → 0,106 : ✅ vérifiée, ⚠ non reproduite.** C'est la moyenne des distances que **le serveur a journalisées lors de reconnaissances réelles à la webcam** (recette du 29/10), avant puis après quatre validations d'empreinte (189 puis 45 mesures). Source unique : entrée 023. **Mesure contrôlée du 02/11, première lecture de nuit ; seconde lecture en journée prévue** (même chaîne que BioGate, 78 images, les mêmes pour les deux références) : distance moyenne 0,209 → 0,203, pire image 0,436 → 0,274, images au-dessus du seuil 2 → 0. L'apprentissage supprime donc les pires cas mais ne baisse presque pas la moyenne pour un visage proche de son enrôlement : **ne pas écrire « 0,269 → 0,106 » comme l'effet de l'apprentissage**. Détails dans le brief et `docs/mesures/apprentissage_webcam/`.
- **B5 — Bande Wi-Fi : 👤.** L'auteur affirme 5 GHz ; l'entrée 024 note 2,4 GHz canal 1. Ne rien écrire avant sa décision.
- **B6 — JWT : ✅ (à confirmer par l'auteur).** Le code délivre un **jeton opaque aléatoire** (`secrets.token_urlsafe(32)`), gardé en mémoire côté serveur, valable 30 jours, conservé chiffré côté tableau de bord. Aucun JWT. La mention « JWT » était un commentaire périmé de `api.py`, corrigé. Le mémoire décrit bien la version réalisée.
- **B7 — Table d'audit : ✅.** Prévue, non implémentée : le README la classe « Prévu, non implémenté » et `perspective.md` §5.1 « Partiellement implémenté ». `event_logs` tient lieu de journal d'événements, sans identifiant d'interaction ni évolution détaillée du score. La limite du mémoire est correcte.
- **B8 — Visages proches : ⚠ 👤.** Mentionner un lien familial dans un mémoire public : décision de l'auteur. Chiffres vérifiés dans la base (lecture seule) : le vecteur du second profil est à **0,306 à 0,549 (moyenne 0,422)** des 8 vecteurs du profil principal ; le plus proche (0,306) est **sous le seuil de 0,35**, donc une confusion est possible. La plage « 0,23 à 0,35 » du journal vient d'observations **en direct** (visage de l'auteur contre le profil du second), pas de ces vecteurs enregistrés : citer l'une ou l'autre en disant laquelle. Entre vecteurs du même profil : 0,027 à 0,370 (moyenne 0,176).
- **B9 — Duplication de profils : ✅.** Le second profil est le frère de l'auteur (confirmé le 30/10). La base contient deux profils distincts (8 et 1 vecteurs) dont les vecteurs sont à 0,306 au minimum l'un de l'autre : ce ne sont pas des copies.

## C. Affirmations à vérifier

- **Suppression Telegram sous 48 h : ✅.** Documentation officielle de la méthode `deleteMessage` ([Bot API](https://core.telegram.org/bots/api)) et essai réel sur le vrai bot (message supprimé, `deleted: 1`).
- **Face ID et la profondeur : ✅ à corriger dans le mémoire.** Apple documente une **caméra TrueDepth** : projection de points infrarouges formant une carte de profondeur et une image infrarouge 2D, vérification de l'attention (yeux ouverts, regard vers l'appareil), réseaux de neurones contre l'usurpation, ordre des captures et motif de points aléatoires, comparaison dans le Secure Enclave ([Face ID, technologie avancée](https://support.apple.com/en-us/102381) ; [sécurité biométrique](https://support.apple.com/guide/security/biometric-security-sec067eb0c9e/web)). Le mémoire ne doit donc pas laisser croire que Face ID n'a pas de capteur de profondeur : chapitre 1 (§ Face ID, tableau comparatif, analyse critique) à compléter ; c'est précisément ce que BioGate n'a pas.
- **YOLOv8 nano, 3,2 millions de paramètres : ✅.** 3 157 200 paramètres comptés sur le fichier de poids du projet, soit 3,16 millions ; « 3,2 » est correct.
- **Vitesse du pipeline « deux à cinq images par seconde » : ✅ mesurée le 02/11 (`docs/mesures/performance/`).** Ce n'était qu'un commentaire du code. Mesuré : environ **2,2 à 2,5 images par seconde pendant l'identification** (401 à 443 ms par image, FaceNet512 en représente 74 %), et **jusqu'à 18,3 images par seconde une fois la personne identifiée** (médiane de 30 ms par image). Écrire les deux régimes. Scène fixe sur fond noir, une machine, CPU seul.
- **Description des sept pages du tableau de bord : ✅ vérifiée sur les captures.** Statistiques : quatre indicateurs, **plus** un graphique « Accès par jour » et la liste « VIPs les plus actifs » (le texte actuel omet ces deux éléments). Journal : filtres par période, par type et par nom, export CSV, bouton de purge, suppression par ligne. Profils : l'entrée du menu s'appelle « VIP », avec enrôlement et retrait. Alertes : liste des intrusions confirmées, réglage Telegram et e-mail, notifications du bureau. Couplage : étape 1 adresse du serveur, étape 2 code PIN. Configuration : profils de sécurité, curseurs, interrupteurs, purge automatique, actionneurs, sources vidéo avec modification.
- **Correction de la vivacité : ✅ en partie.** Les 8 tests et toute la suite de la branche passent sur une copie propre. Le serveur complet avec cette correction n'a pas tourné en réel (le serveur lancé le 02/11 est celui de `main`, sans elle).
- **FaceNet512 « robuste aux conditions lumineuses » : ⚠.** Raison tirée du journal. Observation du 02/11 : dans une pièce sombre (luminosité 49 sur 255), 39 re-confirmations avec une distance moyenne de 0,178, toutes sous 0,35. Elle peut appuyer l'affirmation comme observation, pas comme comparaison chiffrée avec VGG-Face.
- **Article 394 du Code du numérique : ⚠ non vérifié ici.** À lire dans le texte officiel (ou à faire vérifier par l'auteur).

## D. Style et forme (décisions de l'auteur, avec une recommandation)

1. **Acronymes** : garder le mécanisme du glossaire IFRI pour YOLO, CLAHE, HSV, MJPEG, API ; définir **dans une phrase**, à la première apparition, les notions centrales (Edge Computing, informatique en nuage, vivacité). 👤
2. **Tableaux ou listes** : garder les tableaux qui comparent des valeurs. 👤
3. **Longueur du chapitre 3** : décision de l'auteur après ajout des captures. 👤
4. **Chapitre 1** : alléger les phrases longues chargées de chiffres, comme pour le chapitre 2 : oui, recommandé. 👤
5. **Bibliographie** : une relecture finale avant le dépôt est recommandée ; elle vaut aussi pour les sources vérifiées par Perplexity. 👤

## E. Décisions qui ne dépendent pas du texte

1. **Assistants d'intelligence artificielle** : 👤 à décider avec le règlement de l'IFRI et de l'UAC ; rien n'est écrit.
2. **Dépôts publics : ✅ constat** — les deux dépôts sont **publics** (vérifié le 01/11). 👤 les passer en privé ou non.
3. **Jeton Telegram** : collé dans une conversation, à révoquer chez @BotFather en fin de projet puis à ressaisir. 👤
4. **Photos de l'acteur** : 👤 (licence CC BY-SA indiquée dans la légende ; la mention « droits de la personnalité » est à lire).
5. **Fusion dans `main`** : rien n'a été fusionné de la branche vers `main`. 👤 À décider à la fin ; en attendant, ramener `main` dans la branche.
