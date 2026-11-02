# Ce qui manque et ce que je ne comprends pas

Document écrit le 2 novembre 2026, sur la branche `claude/memoire-latex-telephone-h1vdti`.
État du mémoire au moment de l'écriture : 66 pages, compilation sans erreur, aucune référence manquante.

Comment répondre : écris tes réponses sous chaque point, ou dis-les-moi dans la conversation.
Chaque point indique où il apparaît dans le mémoire et ce que j'ai fait en attendant.

---

## A. Ce que toi seul peux fournir

### A1. Page de garde (fichier `memoire.tex`, lignes 35 à 55)
Cinq informations sont encore en rouge dans le PDF :
- l'option de formation (par exemple Sécurité informatique, Génie logiciel) ;
- le grade de M. Probus KIKI (docteur, professeur, maître de conférences, ingénieur) ;
- l'année académique (par exemple 2025-2026) ;
- le nom, le grade et l'entité de chaque membre du jury : président, examinateur, rapporteur ;
- la date de soutenance, aujourd'hui « - ».

Le titre est long : « Conception et implémentation d'une infrastructure de contrôle d'accès biométrique intelligente par vision artificielle et architecture Edge Computing : le système BioGate ». Le garde-t-on, ou le raccourcit-on ?

### A2. Dédicace et remerciements (`0-dedicace.tex`, `1-remerciements.tex`)
Les deux sont vides. Je n'écris pas à ta place ce qui est personnel. Pour les remerciements, l'IFRI attend en général : la direction, l'encadrant, le corps professoral, le jury, la famille. Dis-moi si tu veux que je rédige un premier jet à corriger.

### A3. Images (dossier `memoire/images/`)
Les cadres rouges « Image à fournir » se remplissent seuls dès que le fichier existe, avec le nom exact :

| Fichier à déposer | Figure | Chapitre |
|---|---|---|
| `bw21_carte.jpg` | Carte BW21-CBV | 2 |
| `dashboard_surveillance.png` | Page de surveillance | 2 |
| `dashboard_journal.png` | Page du journal | 3 |
| `dashboard_profils.png` | Page des profils | 3 |
| `dashboard_config.png` | Page de configuration | 3 |
| `dashboard_alertes.png` | Page des alertes | 3 |
| `dashboard_couplage.png` | Page de couplage | 3 |

Attention : `bw21_carte.jpg` contient aujourd'hui la photo que tu m'as envoyée. Elle fait 225 par 225 pixels et ressemble à une photo de vendeur. La légende dit « utilisée dans le prototype », ce qui n'est vrai que si c'est ta carte. Une photo prise par toi règle la résolution et les droits.
La page des statistiques est décrite en texte seulement, sans capture. Veux-tu en ajouter une ?

### A4. Attaques par photographie et par vidéo
Le brief de `main` les annonce comme « pas encore faites, environ une heure avec l'auteur ». Elles figurent dans les objectifs de l'introduction (« résistance aux attaques par présentation »). Le chapitre 3 les déclare « non mesurées ». Deux options :
1. tu les fais, et je rédige les résultats avec la même prudence que pour le FAR et le FRR ;
2. tu ne les fais pas, et on retire le mot « résistance » de l'objectif d'évaluation pour que l'introduction ne promette pas ce que le chapitre 3 ne livre pas.

Quel protocole minimal acceptes-tu : une photo imprimée, une photo sur téléphone, une vidéo sur téléphone ? Combien d'essais par attaque ?

### A5. Suite de tests complète
Le chapitre 3 annonce 175 cas dont 167 réussis (relevé du poste de développement). Un marqueur rouge demande de relancer toute la suite après la fusion des deux branches. Commande donnée par ton brief :
`.venv-deepface\Scripts\python.exe -m unittest discover -s tests -t .`
Dis-moi le résultat, ou colle la dernière ligne. Je retire alors le marqueur.

### A6. Fenêtre de grâce réelle
Le mémoire écrit 60 secondes par défaut, réglable de 5 à 120 secondes selon le profil. Tu m'as dit l'avoir baissée. Ton journal (entrée 023) dit « pas encore réduite ». Quelle valeur utilises-tu vraiment, et depuis quand ?

### A7. Mots clés
Je propose : reconnaissance faciale, contrôle d'accès, test de vivacité, edge computing, protection des données personnelles. À valider ou à changer.

### A8. Coût du prototype
Tu m'as demandé plus tôt si je traitais ton modèle économique. Je n'ai écrit que « sans abonnement ». Je n'ai aucun prix. Veux-tu une courte sous-section avec le coût du matériel (carte, ordinateur, éventuels abonnements Telegram, Internet) ? Alors donne-moi les montants et la monnaie.

### A9. Annexes
Il n'y en a aucune. Veux-tu, par exemple, la liste des 37 routes, le plan du dépôt, ou la procédure de mise en service de la carte ?

---

## B. Ce que je ne comprends pas ou qui se contredit

### B1. Le taux de faux rejet de 52 % me paraît très élevé
La mesure sur LFW donne, au seuil 0,35, un FAR de 0,0 % et un FRR de 52,0 %. Le point d'égal taux d'erreur est de 13,1 %. Les performances publiées pour FaceNet sur LFW sont bien meilleures, et ton brief le note : « l'écart n'est pas expliqué ». Un jury le remarquera.
Je n'ai pas d'explication vérifiée. Pistes, à tester une par une avec ton script `tests/mesures/mesure_far_frr.py` :
1. sans CLAHE ;
2. avec le détecteur et l'alignement propres à DeepFace à la place de Haar ;
3. avec le recadrage du visage que DeepFace attend (marge autour du visage) ;
4. avec la distance mesurée sur des vecteurs normalisés.
Veux-tu que j'écrive une courte sous-section « causes possibles de l'écart » une fois que tu auras fait au moins un de ces essais ? Aujourd'hui je me limite à écrire que l'écart n'est pas expliqué.

### B2. Le profil « haute sécurité » désactive la vivacité
Dans `database/db_manager.py`, ce profil met `LIVENESS_ENABLED` à `False` et `MFA_REQUIRED` à `True`. Avant ma correction, ce réglage n'avait aucun effet. Depuis, il en a un : en haute sécurité, seule l'empreinte peut accorder l'accès.
- Est-ce voulu ? Je m'attendais plutôt à l'inverse : plus de sécurité, donc plus de facteurs.
- Conséquence : l'empreinte étant simulée, un résident ne peut plus entrer en haute sécurité avec un simple geste.
Dis-moi si le profil doit garder la vivacité active. Je corrige alors la valeur dans le code, dans le tableau des profils (chapitre 2) et dans les tests.

### B3. Le paramètre `TRUST_FACE_THRESHOLD = 60` n'est utilisé nulle part
Il est lu dans la configuration mais ne commande rien : le score du visage est la confiance réelle de la reconnaissance. L'état « visage reconnu » (`FACE_MATCHED`) est aussi défini mais traversé instantanément. Les deux sont-ils des restes d'une version précédente ? Si oui, je peux les retirer du code ou les laisser et les mentionner comme tels. Je n'y touche pas sans ton accord.

### B4. Distance moyenne 0,269 puis 0,106
Le brief demande de recouper ce chiffre, car « le journal donne d'autres relevés ». Je ne trouve qu'un seul relevé, dans l'entrée 023 (quatre validations d'empreinte simulées : 189 mesures à 0,269, puis 45 mesures à 0,106). Où sont les autres relevés ? Sinon le chiffre reste dans le mémoire avec cette seule source.

### B5. Bande Wi-Fi de la carte
Tu affirmes 5 GHz. Le journal (entrée 024) relève 2,4 GHz, canal 1, sur le port série. Je n'ai rien écrit sur la bande, comme demandé. Je dis seulement « bi-bande » d'après la fiche technique. Si tu tranches, dis-moi laquelle : le mémoire pourra la citer.

### B6. Authentification annoncée dans les notes et réalisée
Tes notes du 30 juillet prévoient HTTPS (TLS 1.3) et un jeton JWT. Le code actuel utilise un jeton aléatoire opaque et pas de HTTPS. Le mémoire décrit la version réalisée et classe HTTPS en perspective. Peux-tu confirmer que le JWT est abandonné ?

### B7. Table d'audit
Le mémoire cite parmi les limites « la table d'audit prévue n'est pas implémentée ». Je m'appuie sur `perspective.md` (section 5.1, « partiellement implémenté ») et sur le `README.md` (« prévu, non implémenté »). Confirmes-tu qu'elle était prévue et ne l'est pas, et que `event_logs` en tient lieu aujourd'hui ?

### B8. Visages proches
Le brief dit : le frère de l'auteur est hors des tests finaux, aucune marge de décision n'est ajoutée. Mon texte (chapitre 3, limites) écrit : « deux membres d'une même famille ont été confondus lors de la recette, leurs distances se situant de 0,23 à 0,35 autour du seuil de 0,35 ». Acceptes-tu de mentionner un lien familial dans un mémoire public, ou préfères-tu « deux profils dont les visages se ressemblent » ?

### B9. Duplication de profils dans ton journal
L'entrée 020 parle d'abord de deux profils « Ash » et « Fuck » qui portent « le même visage », puis l'entrée 023 explique que le second est le frère. Je veux m'assurer que l'identité alterne bien parce que les deux visages se ressemblent, et non parce qu'un des deux profils est une copie.

---

## C. Ce que j'ai écrit sans pouvoir le vérifier moi-même

| Affirmation | Où | Pourquoi je ne suis pas sûr |
|---|---|---|
| L'interface des robots Telegram ne supprime qu'un message de moins de 48 heures | Chapitre 2, section 2.6, et choix du délai de 47 h | Je n'ai pas pu lire la page de l'API (accès bloqué depuis mon environnement). Ton journal cite « la documentation officielle ». À recouper avec la méthode `deleteMessage`. |
| Face ID : rien n'est écrit sur un capteur de profondeur | Chapitres 1 et 2 | La page Apple est inaccessible pour moi. Prompt Perplexity prêt : demander les passages exacts sur la profondeur, l'infrarouge ou la caméra TrueDepth. |
| YOLOv8 nano : 3,2 millions de paramètres | Chapitre 2, choix techniques | Chiffre relevé par Perplexity (niveau A), que je n'ai pas lu moi-même sur la page. |
| Vitesse du pipeline complet : « de l'ordre de deux à cinq images par seconde » | Chapitres 2 et 3 | Cette valeur vient d'un commentaire du code, pas d'une mesure. Le brief note la « performance complète (ms par image) » comme non faite. |
| Description des sept pages du tableau de bord | Chapitres 2 et 3 | Je l'ai écrite d'après le code React, sans avoir lancé l'application ni vu les écrans. Les captures serviront à la vérifier. |
| Correction de la vivacité | Code (`core/trust_score.py`, `api.py`) | Je n'ai pu lancer que les 8 tests qui n'ont besoin que de la bibliothèque standard. Le serveur complet et le tableau de bord modifié (`Surveillance.jsx`) n'ont pas été lancés. |
| FaceNet512 « robuste aux conditions lumineuses » | Chapitre 2 | Raison tirée de ton code et de ton journal, pas d'une comparaison chiffrée. |
| Nouvelle introduction : article 394 du Code du numérique | Introduction | L'annexe A du brief citait la loi 2009-09. J'ai préféré le Code du numérique vérifié par Perplexity. À confirmer. |

---

## D. Questions de style et de forme

1. **Acronymes** : la première apparition affiche la forme anglaise entre parenthèses (par exemple « You Only Look Once (YOLO) »). Ton brief demande de définir les termes anglais dans une phrase et non entre parenthèses. Pour YOLO, CLAHE, HSV, MJPEG, API, ce mécanisme est celui du gabarit IFRI. Le gardes-tu, ou faut-il une phrase de définition à chaque fois ?
2. **Tableaux contre listes** : tu as préféré une liste au tableau des défaillances. Veux-tu la même chose pour d'autres tableaux (réglages, tests, défauts) ? Je garde les tableaux qui comparent des valeurs.
3. **Longueur** : le chapitre 3 fait environ 13 pages (pages 45 à 57), contre 14 à 18 pour les deux mémoires de référence. Les captures du tableau de bord l'allongeront un peu. Veux-tu l'étoffer, le laisser ainsi, ou le resserrer ?
4. **Détection du style « IA »** : le chapitre 1 n'a pas été relu par toi depuis la réécriture du chapitre 2. Il contient encore des phrases longues avec beaucoup de chiffres. Veux-tu que je l'allège dans le même esprit ?
5. **Sources** : une partie des sources a été vérifiée par Perplexity (niveau A ou B), pas par moi. Veux-tu une relecture finale de toute la bibliographie contre un nouveau passage Perplexity avant le dépôt ?

---

## E. Décisions qui ne dépendent pas du texte

1. **Usage d'assistants d'intelligence artificielle.** Ton journal et `erreur.md` parlent de « deux instances Claude Code » et d'« hallucinations de code ». Les messages de commit portent aussi une mention de co-auteur. Le mémoire ne dit rien à ce sujet. Il faut décider : une mention dans les remerciements, dans l'introduction, ou dans une annexe ? Vérifie aussi le règlement de l'IFRI et de l'UAC sur ce point. Je ne rédige rien sans ta décision.
2. **Dépôts publics.** D'après ton brief, les dépôts sont publics : le texte du mémoire est lisible avant la soutenance. Je t'avais dit à tort qu'ils étaient privés. Décide si tu les passes en privé jusqu'au dépôt.
3. **Jeton Telegram.** Ton brief indique qu'il a été collé dans une conversation. À révoquer chez @BotFather en fin de projet, puis à ressaisir dans l'onglet Alertes.
4. **Photos de l'acteur.** La photo de 2019 porte le bandeau « droits de la personnalité » sur Wikimedia Commons. Le texte précise que les images servent seulement à mesurer une distance. Acceptes-tu cette formulation, ou préfères-tu un autre sujet ?
5. **Fusion dans `main`.** Je n'ai rien fusionné dans `main` ni forcé quoi que ce soit. La branche du mémoire contient le code de `main` (fusion faite dans ma branche) et mes corrections. À toi de décider quand la fusionner.

---

## F. Ce que je peux faire dès que tu réponds

- Remplir la page de garde dès que tu me donnes A1.
- Insérer les images dès que les fichiers sont dans `memoire/images/`.
- Rédiger les résultats des attaques (A4) et les causes possibles du FRR (B1).
- Corriger le profil haute sécurité, le paramètre inutilisé et les tests (B2, B3).
- Écrire la section coût (A8), les annexes (A9), le premier jet des remerciements (A2).
- Alléger le chapitre 1 et ajuster la longueur du chapitre 3 (D3, D4).

---

## État au 2 novembre, après lecture de `main` (réponses du poste de développement)

Source : `docs/REPONSES_AU_TELEPHONE.md` et `docs/BRIEF_MEMOIRE.md` (mis à jour le 02/11). Ce que j'ai reporté dans le mémoire :

| Point | Décision ou constat | Reporté |
|---|---|---|
| A3 Images | Six captures reçues (données de démonstration) | Placées dans `memoire/images/`, légendes « données de démonstration », nouvelle figure pour les statistiques, descriptions des pages corrigées d'après les captures |
| A5 Tests | 172 réussis sur `main`, 180 après fusion | Tableau à 180 cas (+ 5 tests du téléchargement du modèle), marqueur rouge conservé pour la suite complète |
| A6 Fenêtre de grâce | 60 s dans la base réelle | Aucun changement nécessaire |
| B2 Haute sécurité | Empreinte seule, tranché par l'auteur | Aucun changement, le mémoire était juste |
| B3 Paramètre inutilisé | Ne rien retirer | Aucun changement |
| B4 Distance 0,269 → 0,106 | Non reproduite par la mesure contrôlée | Retirée comme effet de l'apprentissage ; remplacée par la mesure à la webcam (0,209 → 0,203, pire image 0,436 → 0,273), première lecture de nuit |
| B6 JWT | Jeton opaque, commentaire périmé corrigé | Le mémoire décrit déjà la version réalisée |
| B8 Visages proches | Plage 0,23–0,35 issue d'observations en direct ; vecteur le plus proche à 0,306 | Limite réécrite sans mention familiale, avec les deux sources |
| C Face ID | Caméra TrueDepth documentée par Apple | Chapitre 1 corrigé (paragraphe, tableau, analyse critique) ; chapitre 2 y renvoie |
| C Vitesse 2 à 5 images/s | Estimation, non mesurée | Écrit comme telle aux chapitres 2 et 3 |
| C Faible éclairage | Observation du 02/11 (39 reconfirmations, distance moyenne 0,178) | Nouvelle sous-section, présentée comme observation |

Ce qui reste ouvert : A1 (page de garde), A2 (dédicace, remerciements), A4 (attaques photo et vidéo), A7 à A9, B1 (FRR de 52 %, quatre pistes à tester), B5 (bande Wi-Fi), E1 à E5, la seconde lecture de l'apprentissage en pleine lumière (marqueur rouge au chapitre 3), la capture `dashboard_surveillance.png` (il faut la vraie caméra) et la confirmation que la photo de la carte est bien celle de l'auteur.

Deux points que je n'ai pas pu vérifier moi-même : la source Apple sur la carte de profondeur (page « Biometric security », lue par le poste de développement) et l'article 394 du Code du numérique (lu par Perplexity sur l'édition de l'APDP).

### Mise à jour du 2 novembre (soir) : longueur et photo de la carte

- La photo de la carte vient de Youpilab : la légende le dit (« Source de l'image : Youpilab »). Reste à vérifier que l'usage dans un mémoire est permis par le vendeur, ou à indiquer l'adresse de la page produit si tu veux la citer.
- Longueur : 70 pages ramenées à 63 (corps de 45 pages, contre 42 et 47 pour les deux mémoires de référence). Ce qui a été retiré est dans `DETAILS_POUR_LA_SOUTENANCE.md`, avec des réponses aux questions probables du jury.
