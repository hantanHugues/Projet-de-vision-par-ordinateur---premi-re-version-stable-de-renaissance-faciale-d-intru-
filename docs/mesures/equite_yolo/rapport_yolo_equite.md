# Détecteur de silhouettes (YOLOv8n) selon la région et le sexe

*Généré par `tests/mesures/mesure_yolo_equite.py` le 04/11/2026 à 13:32.*

## Protocole (fixé avant tout résultat)

- 90 personnes examinées, 939 photos admises (exactement un visage d'au moins 70 px vu par MediaPipe), 75 personnes avec au moins 3 photos admises. Photos de Wikimedia Commons déjà téléchargées pour `mesure_equite_modeles.py`.
- Appel de YOLO identique à la production (`YoloDetector.detect_humans` : yolov8n.pt, 320 px, confiance 0,5, IoU 0,35, NMS 0,30).
- Réussite d'une photo : une silhouette dont la boîte contient le centre du visage.
- **Unité : la personne.** IC à 95 % par rééchantillonnage des personnes. Sensibilité : même mesure à 640 px.

## Résultats par groupe

| Région | Personnes | Silhouette trouvée à 320 px (production) [IC 95 %] | À 640 px [IC 95 %] |
|---|---|---|---|
| Afrique | 12 | 98,8 % [96,4 ; 100,0] | 98,8 % [96,4 ; 100,0] |
| Asie | 12 | 99,3 % [97,9 ; 100,0] | 99,3 % [97,9 ; 100,0] |
| Europe | 12 | 100,0 % [100,0 ; 100,0] | 98,0 % [96,1 ; 99,6] |
| Amérique du Nord | 13 | 99,5 % [98,6 ; 100,0] | 100,0 % [100,0 ; 100,0] |
| Amérique du Sud | 14 | 98,4 % [96,1 ; 100,0] | 98,1 % [95,3 ; 100,0] |
| Océanie | 12 | 99,1 % [97,9 ; 100,0] | 99,4 % [98,2 ; 100,0] |

| Sexe | Personnes | Silhouette trouvée à 320 px (production) [IC 95 %] | À 640 px [IC 95 %] |
|---|---|---|---|
| F | 36 | 98,6 % [97,3 ; 99,7] | 98,3 % [97,1 ; 99,4] |
| M | 39 | 99,7 % [99,3 ; 100,0] | 99,5 % [98,5 ; 100,0] |

## Contrôle du cadrage

Un gros plan est peu favorable à un détecteur de personnes. Taux de réussite selon la taille du visage dans l'image (toutes personnes confondues) :

| Cadrage | Photos | Silhouette trouvée à 320 px | À 640 px |
|---|---|---|---|
| plan large (visage < 15 % de la largeur) | 122 | 98,4 % | 99,2 % |
| plan moyen (15 à 30 %) | 379 | 98,7 % | 98,9 % |
| gros plan (≥ 30 %) | 438 | 99,8 % | 98,9 % |

Taille médiane du visage (fraction de la largeur de l'image) par groupe : Afrique 24 % (106 photos), Asie 23 % (125 photos), Europe 32 % (201 photos), Amérique du Nord 32 % (196 photos), Amérique du Sud 23 % (135 photos), Océanie 35 % (176 photos), F 29 % (533 photos), M 28 % (406 photos).

## Limites

- Photos de presse, portraits et plans moyens : pas une caméra de porte avec silhouette entière.
- La présence d'une personne est définie par un visage détectable : les personnes sans visage détectable sont exclues.
- Effectifs de quelques personnes par groupe : **cette mesure décrit l'échantillon, elle ne prouve pas un biais.**
- Un écart entre groupes peut venir du cadrage plutôt que de la personne : voir le contrôle ci-dessus.

## Matériel et versions

- Système : Windows-10-10.0.26200-SP0
- Processeur : AMD64 Family 25 Model 124 Stepping 0, AuthenticAMD
- Python : 3.11.15
- Ultralytics : 8.4.47
- OpenCV : 4.11.0
- MediaPipe : 0.10.35
- Durée : 127 s
