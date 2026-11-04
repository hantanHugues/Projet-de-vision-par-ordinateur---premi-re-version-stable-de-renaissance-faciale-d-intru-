# Le filtre de visage de BioGate selon la région et le sexe

*Généré par `tests/mesures/mesure_detection_commons.py` le 04/11/2026 à 04:11.*

## Protocole

- 90 personnes, 1980 photos de Wikimedia Commons (licence libre, datées, nom de la personne dans le nom du fichier, largeur d'au moins 400 px), les mêmes que `mesure_vieillissement_commons.py`.
- Pour chaque photo : (1) le filtre actuel de BioGate : Haar de face, un seul visage d'au moins 70 px, confirmé par MediaPipe ; (2) MediaPipe seul : exactement un visage d'au moins 70 px, quelle que soit la pose.
- **Unité statistique : la personne.** Taux de validation par personne, moyenne par groupe, intervalle de confiance à 95 % (entre crochets) par rééchantillonnage des personnes.

## Résultats

| Région | Personnes | Photos testées | Filtre actuel de BioGate (Haar + MediaPipe) : un visage de face validé | MediaPipe seul : exactement un visage |
|---|---|---|---|---|
| Afrique | 16 | 250 | 23,7 % [15,5 ; 32,0] | 41,5 % [30,5 ; 52,4] |
| Asie | 13 | 258 | 30,8 % [20,7 ; 40,9] | 50,7 % [40,6 ; 61,4] |
| Europe | 12 | 331 | 42,4 % [33,7 ; 50,6] | 62,9 % [51,7 ; 71,9] |
| Amérique du Nord | 13 | 408 | 30,4 % [21,8 ; 38,4] | 49,5 % [38,4 ; 59,8] |
| Amérique du Sud | 17 | 397 | 20,6 % [13,5 ; 28,7] | 37,2 % [26,0 ; 48,8] |
| Océanie | 13 | 336 | 31,8 % [24,5 ; 38,8] | 50,9 % [40,7 ; 60,0] |

| Sexe | Personnes | Photos testées | Filtre actuel de BioGate (Haar + MediaPipe) : un visage de face validé | MediaPipe seul : exactement un visage |
|---|---|---|---|---|
| F | 39 | 982 | 33,8 % [28,6 ; 38,9] | 53,4 % [46,5 ; 59,8] |
| M | 45 | 998 | 25,1 % [20,2 ; 30,1] | 43,0 % [36,8 ; 49,4] |

Les effectifs par groupe sont petits et les photos varient (événements, groupes, poses) : **ces tableaux décrivent l'échantillon, ils ne prouvent pas un biais du détecteur**. Ils justifient en revanche de **tester le filtre de visage sur des visages variés avant tout déploiement**, ce que le chapitre 3 doit présenter comme limite et perspective.

## Limites

- Les motifs de rejet dépendent du type de photo : photos d'événement avec plusieurs personnes (« plusieurs visages »), poses de profil, lumière de scène.
- MediaPipe seul détecte un visage quelle que soit la pose, alors que Haar exige un visage de face (nécessaire à FaceNet) : il n'est pas, tel quel, un remplaçant du filtre actuel.
- Échantillon de célébrités, photos de presse : pas une caméra de porte. Les effectifs par groupe interdisent toute conclusion sur des différences entre groupes.

## Matériel et versions

- Système : Windows-10-10.0.26200-SP0
- Processeur : AMD Ryzen 5 220 w/ Radeon 740M Graphics
- Cœurs logiques : 12
- Mémoire : 15,3 Go
- Python : 3.11.15
- TensorFlow : 2.21.0
- DeepFace : 0.0.99
- OpenCV : 4.11.0
- Durée : 1146 s
