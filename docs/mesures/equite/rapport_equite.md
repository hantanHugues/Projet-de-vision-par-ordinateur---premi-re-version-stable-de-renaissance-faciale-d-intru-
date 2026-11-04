# Équité des modèles : clignement et reconnaissance selon la région et le sexe

*Généré par `tests/mesures/mesure_equite_modeles.py` le 04/11/2026 à 11:08.*

## Protocole

- 90 personnes examinées, 1980 photos de Wikimedia Commons (mêmes règles que `mesure_vieillissement_commons.py`).
- Clignement : 75 personnes avec au moins 3 photos où MediaPipe voit un seul visage d'au moins 70 px. Score = moyenne de eyeBlinkLeft et eyeBlinkRight, comme `liveness_detector.py` ; seuil de BioGate 0.35. Une photo prise pendant un vrai clignement fait monter le score : on prend la **médiane** par personne.
- Reconnaissance : 80 personnes avec au moins une photo validée par le filtre de BioGate et une autre personne à comparer ; chaîne Haar + MediaPipe, CLAHE, FaceNet512.
- **Unité : la personne.** IC à 95 % par rééchantillonnage des personnes.

## 1. Score de clignement d'un œil ouvert (plus bas = plus de marge avant le seuil de 0,35)

| Région | Personnes | Moyenne par personne [IC 95 %] |
|---|---|---|
| Afrique | 12 | 0,096 [0,071 ; 0,125] |
| Asie | 12 | 0,129 [0,095 ; 0,166] |
| Europe | 12 | 0,125 [0,104 ; 0,143] |
| Amérique du Nord | 13 | 0,127 [0,105 ; 0,152] |
| Amérique du Sud | 14 | 0,089 [0,069 ; 0,108] |
| Océanie | 12 | 0,149 [0,130 ; 0,170] |

| Sexe | Personnes | Moyenne par personne [IC 95 %] |
|---|---|---|
| F | 36 | 0,101 [0,087 ; 0,116] |
| M | 39 | 0,135 [0,121 ; 0,149] |

Part de photos au-dessus du seuil de clignement (œil supposé ouvert)

| Région | Personnes | Moyenne par personne [IC 95 %] |
|---|---|---|
| Afrique | 12 | 3,6 % [0,0 ; 7,7] |
| Asie | 12 | 6,0 % [0,7 ; 13,4] |
| Europe | 12 | 7,3 % [3,4 ; 11,5] |
| Amérique du Nord | 13 | 6,6 % [3,1 ; 10,4] |
| Amérique du Sud | 14 | 2,2 % [0,5 ; 4,2] |
| Océanie | 12 | 9,5 % [5,1 ; 14,2] |

| Sexe | Personnes | Moyenne par personne [IC 95 %] |
|---|---|---|
| F | 36 | 5,3 % [3,4 ; 7,3] |
| M | 39 | 6,3 % [3,6 ; 9,3] |

## 2. Reconnaissance

Distance médiane entre deux photos de la même personne (plus bas = mieux reconnue)

| Région | Personnes | Moyenne par personne [IC 95 %] |
|---|---|---|
| Afrique | 11 | 0,500 [0,392 ; 0,618] |
| Asie | 11 | 0,346 [0,213 ; 0,491] |
| Europe | 12 | 0,560 [0,481 ; 0,639] |
| Amérique du Nord | 12 | 0,425 [0,374 ; 0,479] |
| Amérique du Sud | 15 | 0,587 [0,453 ; 0,737] |
| Océanie | 12 | 0,601 [0,481 ; 0,728] |

| Sexe | Personnes | Moyenne par personne [IC 95 %] |
|---|---|---|
| F | 35 | 0,537 [0,481 ; 0,594] |
| M | 38 | 0,483 [0,402 ; 0,570] |

Part des comparaisons avec une AUTRE personne de l'échantillon qui passent sous le seuil de 0,35 (fausses acceptations potentielles ; au plus 5 photos par personne, pour que chacun ait le même nombre de comparaisons)

| Région | Personnes | Moyenne par personne [IC 95 %] |
|---|---|---|
| Afrique | 14 | 0,7 % [0,2 ; 1,6] |
| Asie | 12 | 0,3 % [0,0 ; 0,7] |
| Europe | 12 | 0,3 % [0,1 ; 0,5] |
| Amérique du Nord | 13 | 0,5 % [0,1 ; 0,9] |
| Amérique du Sud | 16 | 0,5 % [0,2 ; 1,0] |
| Océanie | 13 | 0,4 % [0,2 ; 0,7] |

| Sexe | Personnes | Moyenne par personne [IC 95 %] |
|---|---|---|
| F | 37 | 0,5 % [0,3 ; 0,7] |
| M | 43 | 0,5 % [0,2 ; 0,8] |

Au total : 450 comparaisons sur 103512 (chaque paire comptée deux fois, une par personne).

## Limites

- Le clignement mesuré est le score d'un œil **ouvert**. La sensibilité (détecter un vrai clignement) n'est pas mesurée ici.
- Photos de célébrités, de presse : sourires, maquillage, lunettes, poses variables. Un score élevé peut venir de l'expression et pas de l'œil.
- Région = nationalité. Aucun visage vérifié à la main. Effectifs de quelques personnes par groupe : **ces tableaux décrivent l'échantillon, ils ne prouvent pas un biais.**

## Matériel et versions

- Système : Windows-10-10.0.26200-SP0
- Processeur : AMD Ryzen 5 220 w/ Radeon 740M Graphics
- Cœurs logiques : 12
- Mémoire : 15,3 Go
- Python : 3.11.15
- TensorFlow : 2.21.0
- DeepFace : 0.0.99
- OpenCV : 4.11.0
- Durée : 2270 s
