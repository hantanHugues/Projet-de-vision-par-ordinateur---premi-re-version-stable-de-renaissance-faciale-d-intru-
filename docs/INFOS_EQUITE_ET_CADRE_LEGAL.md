# Informations pour le mémoire : équité des modèles et cadre légal du prototype

Document d'**informations**, sans phrase à recopier : les faits, les chiffres, leurs sources et leurs limites. L'auteur formule lui-même.
Date : 04/11/2026. Mesures : `tests/mesures/mesure_equite_modeles.py`, résultats dans `docs/mesures/equite/`.

---

## Partie A. Les modèles de BioGate sont-ils moins efficaces selon l'origine ?

### A1. Ce que dit la documentation publiée

| Sujet | Ce qui est publié | Source | Ce qui n'existe pas |
|---|---|---|---|
| Reconnaissance faciale en général | Des écarts démographiques existent dans la majorité des 189 algorithmes évalués (99 développeurs). Les algorithmes les plus justes sont aussi parmi les plus précis. Pour la comparaison un-à-plusieurs, les femmes afro-américaines ont les plus hauts taux de faux positifs. Le résultat varie fortement d'un algorithme à l'autre. | NIST, rapport FRVT Part 3 (NISTIR 8280, 2019) : https://pages.nist.gov/frvt/reports/demographics/ | Aucun résultat sur FaceNet512 ni DeepFace. |
| Reconnaissance, jeu RFW | Jeu à 4 sous-ensembles (caucasien, asiatique, indien, africain), environ 10 000 images et 3 000 identités chacun. Précision de vérification d'un service commercial sur 6 000 paires difficiles : 87,6 % (caucasien) à 75,8 % (africain) ; autre service : 93,9 % à 87,5 %. Biais attribué à la fois aux données d'entraînement et à l'algorithme. | Wang et al., ICCV 2019, https://arxiv.org/pdf/1812.00194 | Pas de test de FaceNet512. |
| Données d'entraînement de type VGGFace2 | Équilibre démographique non visé ; rapport estimé de 5 à 6 visages caucasiens pour un afro-américain. Un entraînement équilibré ne garantit pas un test équilibré. | https://arxiv.org/pdf/2109.03229 ; https://arxiv.org/pdf/2304.09818 | Aucune mesure sur le modèle exact de DeepFace. |
| Classification du genre (hors reconnaissance) | Erreur jusqu'à 34,7 % pour les femmes à peau foncée contre 0,8 % pour les hommes à peau claire, sur trois systèmes commerciaux. | Buolamwini et Gebru, *Gender Shades*, PMLR 81, 2018 : https://proceedings.mlr.press/v81/buolamwini18a.html | Tâche différente de celle de BioGate. |
| MediaPipe BlazeFace (détection du visage) | Évalué sur 5 teintes de peau (annotation aux catégories de Fitzpatrick) et 17 sous-régions géographiques ; rappel moyen de 98,4 % entre les sexes pour la version courte portée. | Fiches de modèle Google : https://storage.googleapis.com/mediapipe-assets/MediaPipe%20BlazeFace%20Model%20Card%20(Full%20Range).pdf | Le détail par groupe est dans un tableur annexe, non lu ici. |
| MediaPipe Face Mesh V2 | La fiche contient une section « fairness » (erreur sur la distance inter-oculaire, objectif d'écart de 2,56 %). | Fiche Face Mesh V2 | Groupes exacts non lus. |
| MediaPipe, clignement (blendshapes) | Aucune étude trouvée sur le clignement selon la forme des yeux ou l'origine. | Recherche web du 04/11 | Tout. |

Points d'attention sur les sources : la valeur 34,7 % est une erreur absolue d'un sous-groupe, pas un écart relatif ; les fiches de modèle ont été lues sur des copies, à reprendre sur le site de Google ; pour DeepFace et FaceNet512 la recherche n'a rien trouvé de mesuré par origine.

### A2. Ce qui a été mesuré ici

- Données : les 90 personnes examinées par `mesure_vieillissement_commons.py` (Wikimedia Commons, licence libre, datées, nom dans le nom du fichier), 1 980 photos, 6 régions, deux sexes. Photos non copiées dans le dépôt.
- Unité statistique : la personne. IC à 95 % par rééchantillonnage des personnes (graine fixe).
- Chaîne : celle de BioGate (Haar + MediaPipe, CLAHE, FaceNet512, seuil 0,35).
- Matériel : AMD Ryzen 5 220, 15,3 Go, CPU seul, Windows 11, TensorFlow 2.21.0, DeepFace 0.0.99, OpenCV 4.11.0. Durée 2 270 s.

**1. Clignement (défi de vivacité).** BioGate compte un clignement quand la moyenne de eyeBlinkLeft et eyeBlinkRight dépasse 0,35 (`core/liveness_detector.py`). Ici : score d'un œil **ouvert**, médiane par personne, 75 personnes ayant au moins 3 photos lues.

| Région | Personnes | Score moyen, œil ouvert [IC 95 %] | Photos au-dessus de 0,35 |
|---|---|---|---|
| Afrique | 12 | 0,096 [0,071 ; 0,125] | 3,6 % |
| Asie | 12 | 0,129 [0,095 ; 0,166] | 6,0 % |
| Europe | 12 | 0,125 [0,104 ; 0,143] | 7,3 % |
| Amérique du Nord | 13 | 0,127 [0,105 ; 0,152] | 6,6 % |
| Amérique du Sud | 14 | 0,089 [0,069 ; 0,108] | 2,2 % |
| Océanie | 12 | 0,149 [0,130 ; 0,170] | 9,5 % |
| Femmes | 36 | 0,101 [0,087 ; 0,116] | 5,3 % |
| Hommes | 39 | 0,135 [0,121 ; 0,149] | 6,3 % |

Lecture factuelle : le score d'un œil ouvert reste loin du seuil de 0,35 dans toutes les régions ; l'Asie (0,129) est au niveau de l'Europe (0,125) et de l'Amérique du Nord (0,127) ; les intervalles se recouvrent. Les photos au-dessus de 0,35 sont le fait de sourires, de photos prises pendant un clignement et de lunettes (non vérifié photo par photo).
**Non mesuré : la sensibilité**, c'est-à-dire si un œil fermé est détecté chez tous. Elle exige des vidéos de clignements réels. L'auteur a décidé de ne pas la mesurer.

**2. Reconnaissance (FaceNet512).**

Part des comparaisons avec une AUTRE personne qui passent sous 0,35 (fausses acceptations potentielles). Au plus 5 photos par personne, pour que chacun ait le même nombre de comparaisons.

| Groupe | Personnes | Part sous le seuil [IC 95 %] |
|---|---|---|
| Afrique | 14 | 0,7 % [0,2 ; 1,6] |
| Asie | 12 | 0,3 % [0,0 ; 0,7] |
| Europe | 12 | 0,3 % [0,1 ; 0,5] |
| Amérique du Nord | 13 | 0,5 % [0,1 ; 0,9] |
| Amérique du Sud | 16 | 0,5 % [0,2 ; 1,0] |
| Océanie | 13 | 0,4 % [0,2 ; 0,7] |
| Femmes | 37 | 0,5 % [0,3 ; 0,7] |
| Hommes | 43 | 0,5 % [0,2 ; 0,8] |

Au total : 450 comparaisons sur 103 512 (chaque paire comptée deux fois), soit environ 0,4 %. Tous les intervalles se recouvrent. Cela diffère du FAR de 0,0 % observé sur 1 000 paires de LFW : les photos de célébrités de même profil et les noms mal attribués peuvent y contribuer (non vérifié).

Distance médiane entre deux photos de la même personne (plus bas = mieux) : Afrique 0,500 ; Asie 0,346 ; Europe 0,560 ; Amérique du Nord 0,425 ; Amérique du Sud 0,587 ; Océanie 0,601 ; femmes 0,537 ; hommes 0,483. Presque toutes dépassent le seuil de 0,35 : sur des photos de presse prises à des années d'écart, la reconnaissance avec une seule photo échoue le plus souvent, comme dans le FRR de 52 % sur LFW. C'est une faiblesse générale de la chaîne dans ces conditions, pas une différence entre régions : l'Asie a la meilleure valeur, ce qui est contraire à l'hypothèse de départ, mais les photos validées par le filtre ne sont pas les mêmes selon la région (voir le filtre de visage, 20,6 % à 42,4 % de photos validées), donc un effet de sélection est possible.

### A3. Piège évité

Une première version de la mesure de reconnaissance (distance au « sosie » le plus proche) dépendait du nombre de photos validées par personne : moins de photos, moins de comparaisons, donc un minimum plus élevé. Les chiffres de cette version (Asie 0,383, Océanie 0,159) sont **invalides** et ne doivent être cités nulle part. Version corrigée : au plus 5 vecteurs par personne.

### A4. Limites à ne jamais omettre

- Aucun visage n'est vérifié à la main ; région = nationalité.
- Célébrités, photos de presse : sourires, maquillage, lunettes, poses variables. Pas une caméra de porte.
- 11 à 16 personnes par région : **les tableaux décrivent l'échantillon, ils ne prouvent ni n'excluent un biais.**
- Les paires « même personne » dépendent de l'exactitude des noms de fichiers.
- Le filtre de visage (Haar puis MediaPipe) valide un visage de face pour 33,8 % des photos de femmes contre 25,1 % de celles d'hommes, et de 20,6 % (Amérique du Sud) à 42,4 % (Europe) selon la région ; MediaPipe seul suit le même ordre. Le type de photo pèse autant que le détecteur. Voir `docs/mesures/vieillissement/rapport_detection.md`.
- Le contre-jour est une limite réelle du filtre (Haar 3 à 7 % des images contre MediaPipe 87 à 95 %, séance du 02/11).
- Pour la comparaison avec le NIST : les modèles de BioGate n'ont pas été évalués selon les protocoles du NIST ; la mesure ci-dessus est un contrôle exploratoire.

---

## Partie B. Le prototype respecte-t-il le cadre légal ?

### B1. Ce que le mémoire (version du téléphone) annonce
Deux exigences : le consentement explicite des personnes enrôlées et la limitation de la conservation des images. Références citées : RGPD (art. 4 point 14, art. 5, art. 9), Code du numérique béninois (loi n° 2017-20 du 20 avril 2018 : art. 383, 394, 405, 407, 433), règlement type de la CNIL (bonne pratique sans valeur de loi au Bénin), NIST 8280. Les formalités auprès de l'APDP et le consentement figurent déjà dans les perspectives.

### B2. État du code

| Exigence | Dans BioGate | État |
|---|---|---|
| Limitation de la conservation des photos | Photos d'intrus supprimées après 72 h par défaut (24 h Haute sécurité, 12 h profil strict) ; boucle automatique au démarrage puis toutes les heures ; photos orphelines balayées ; testée (`test_rgpd_purge.py`). | Fait |
| Messages d'alerte Telegram | Supprimés de la conversation après 24 h (maximum 47 h, limite de l'API) ; essai réel. | Fait |
| Droit à l'effacement | Suppression d'un profil avec ses vecteurs ; suppression d'un événement avec sa photo. | Fait |
| Preuve de la rétention | Route `/rgpd/status` (dernière purge, nombre supprimé, erreurs). | Fait |
| Minimisation | Traitement 100 % local ; pour un résident, un vecteur numérique et aucune photo ; seules les photos d'intrus sont gardées. | Fait |
| Accès restreint | PIN puis jeton opaque ; identifiants des canaux d'alerte jamais renvoyés en clair ; 11 routes restent sans jeton. | Partiel |
| Données hors du dépôt public | `*.db` et `database/snapshots/` exclus de git. | Fait |
| Consentement explicite et retrait | Aucun écran ni trace d'accord. | Non fait (perspective) |
| Formalités APDP (déclaration art. 405, autorisation art. 407) | Démarche administrative. | Hors prototype |
| Chiffrement des vecteurs | En clair dans SQLite, protégés par le système de fichiers. | Non fait |
| Journal des événements | La purge automatique supprime les photos, pas les lignes (nom, heure) ; suppression des lignes manuelle. | Partiel |
| Photos d'intrus envoyées à Telegram | Elles quittent la machine ; atténuation : suppression à 24 h. | Entorse à « 100 % local » |
| HTTPS | Prévu dans les notes de projet ; non retrouvé dans le code du serveur. | Non vérifié : ne pas affirmer |
| Réglages Wi-Fi de la carte | Mémorisés dans la flash, non chiffrés. | Non fait |

### B3. Position retenue avec l'auteur
Prototype de laboratoire, pas un déploiement : les exigences de mise en production (consentement, APDP, chiffrement) sont des perspectives, les limites sont documentées. Le minimum pertinent pour un prototype est atteint (traitement local, peu de données, conservation limitée, effacement, accès protégé).

### B4. Réserves et vérifications
1. Photos d'intrus vers Telegram : à déclarer comme entorse au traitement local.
2. Consentement des personnes testées : l'auteur ; son frère (un profil, un vecteur) : l'accord est à noter.
3. Le dépôt public contient quatre photos : `tests/photos_test_apprentissage_continu/` (trois photos de Chris Evans) et `tests/photos_test_faux_visage/chemise_alerte_telegram.jpg`. Leur licence est à vérifier, ou à remplacer par un lien de téléchargement. À trancher par l'auteur.
4. L'article 394 du Code du numérique a été lu par Perplexity, pas par l'assistant : à relire sur l'édition de l'APDP (https://archive.apdp.bj/wp-content/uploads/2019/04/CODE-DU-NUMERIQUE-DU-BENIN_2018-version-APDP.pdf).
5. Les photos des mesures viennent de Wikimedia Commons (licences CC BY, CC BY-SA, CC0, domaine public) et de LFW (usage de recherche) ; le manifeste `docs/mesures/vieillissement/manifeste_photos.csv` liste les pages, auteurs et licences ; aucune photo n'est copiée dans le dépôt.

---

## Fichiers

- `tests/mesures/mesure_equite_modeles.py` ; `docs/mesures/equite/rapport_equite.md` ; `docs/mesures/equite/equite_personnes.csv`.
- `tests/mesures/mesure_vieillissement_commons.py` : réessais ajoutés pour les coupures de connexion (aucun résultat modifié).
