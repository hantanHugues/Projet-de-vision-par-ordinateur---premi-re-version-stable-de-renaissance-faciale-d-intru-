# Effet de l'apprentissage continu, mesuré à la webcam (profil enrôlé)

*Généré par `tests/mesures/mesure_apprentissage_webcam.py` le 02/11/2026 à 01:24.*

## Protocole

- Un profil enrôlé de **8 vecteurs** : le premier est l'enrôlement d'origine, les autres ont été ajoutés par l'apprentissage continu (confirmation par empreinte).
- Capture à la webcam pendant 40 s, la personne regardant la caméra : **78 images retenues** (silhouette trouvée par YOLO, visage de face trouvé par Haar dans la silhouette et confirmé par MediaPipe), 9 faux visages écartés par MediaPipe, 0 silhouettes sans visage de face, 0 images sans personne détectée.
- Chaîne de BioGate : YOLOv8 (silhouette), Face Gate (Haar dans la silhouette + second avis MediaPipe), puis `FaceRecognizer._extract_face_signature` (CLAHE, FaceNet512, alignement), distance cosinus. La base est lue en lecture seule ; aucune image n'est enregistrée.
- Pour **les mêmes images**, on compare la distance au seul vecteur d'origine et la distance au plus proche des vecteurs du profil complet.

## Résultats

| Référence | Moyenne | Médiane | Écart-type | 90e centile | Min | Max | Images sous 0,35 |
|---|---|---|---|---|---|---|---|
| Vecteur d'origine seul | 0.209 | 0.206 | 0.044 | 0.238 | 0.133 | 0.436 | 76 sur 78 |
| Profil complet (8 vecteurs) | 0.203 | 0.204 | 0.027 | 0.232 | 0.133 | 0.273 | 78 sur 78 |

- Baisse de la distance moyenne : **0.209 → 0.203** (différence 0.006).
- Le profil complet est plus proche que le seul vecteur d'origine pour **2 images sur 78**.
- Distance au plus proche **autre** profil : moyenne 0.423, minimum 0.288. Écart moyen avec le profil complet : 0.220 (une valeur faible ou négative signale un risque de confusion).

## Limites

- Une seule personne, une seule séance, un seul éclairage : l'ordre de grandeur est utile, pas une garantie.
- Les images consécutives sont très proches les unes des autres : leur nombre ne vaut pas un nombre égal de mesures indépendantes.
- Le profil complet contient plus de vecteurs que le vecteur d'origine : prendre le minimum sur plusieurs références baisse mécaniquement la distance. La mesure montre l'ampleur de cet effet sur ce visage, pas une meilleure reconnaissance en toutes conditions.

## Matériel et versions

- Système : Windows-10-10.0.26200-SP0
- Processeur : AMD Ryzen 5 220 w/ Radeon 740M Graphics
- Cœurs logiques : 12
- Mémoire : 15,3 Go
- Python : 3.11.15
- TensorFlow : 2.21.0
- DeepFace : 0.0.99
- OpenCV : 4.11.0
