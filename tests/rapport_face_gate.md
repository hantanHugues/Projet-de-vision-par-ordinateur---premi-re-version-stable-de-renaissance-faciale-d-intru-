# Rapport de mesure — Face Gate (détection Haar en double)

*Généré le 28/10/2026 à 12:10*

## Méthodologie

Banc d'essai `tests/bench_face_gate.py` : la vraie route `/analyze_frame` est rejouée (décodage JPEG, tracker, `identify()`, Trust Score) avec une photo de test, dans deux configurations.

- **Avant** : `api.py` relançait la détection Haar à chaque image et pour chaque personne (encadré affiché par le client), en plus de celle d'`identify()`. Le bloc supprimé est rejoué à l'identique.
- **Après** : l'encadré réutilise la position du visage mémorisée par `identify()` (`FaceRecognizer.get_face_box`) et la replace sur la silhouette courante.

YOLO et FaceNet512 sont remplacés par des doubles de coût nul : la mesure isole le Face Gate et le reste de la route, pas l'IA lourde. Un seul appel Haar coûte, sur ce matériel, **58.17 ms** en médiane (silhouette de 296×380 px).

## Matériel

- Processeur : AMD64 Family 25 Model 124 Stepping 0, AuthenticAMD
- Système : Windows-10-10.0.26200-SP0
- Python 3.11.15, OpenCV 4.11.0

## Résultats

| Situation | Personnes | Avant (ms/image) | Avant (Haar/image) | Après (ms/image) | Après (Haar/image) | Gain de temps |
|---|---|---|---|---|---|---|
| Identification en cours (chaque image passe par le Face Gate) | 1 | 121.2 | 2.00 | 63.4 | 1.00 | +48 % |
| Identification en cours (chaque image passe par le Face Gate) | 3 | 172.8 | 6.00 | 87.4 | 3.00 | +49 % |
| Personne identifiée, flux à 5 images/s (re-vérification toutes les 0.8 s) | 1 | 79.2 | 1.28 | 19.1 | 0.24 | +76 % |
| Personne identifiée, flux à 5 images/s (re-vérification toutes les 0.8 s) | 3 | 114.7 | 3.96 | 25.3 | 0.72 | +78 % |

## Lecture

Pendant l'identification, la détection d'`identify()` est indispensable (c'est le Face Gate de sécurité) : le correctif supprime seulement le doublon, soit un appel sur deux. Une fois la personne identifiée, `identify()` ne relance le Face Gate qu'à chaque re-vérification ; avant le correctif, l'encadré de l'interface continuait à déclencher une détection par image et par personne.

Limites : mesure sur une seule photo et un seul processeur ; le gain absolu dépend de la taille des silhouettes et du nombre de personnes. Le gain relatif en nombre d'appels, lui, vient de la structure du code.

## Reproductibilité

```
.venv-deepface\Scripts\python.exe tests\bench_face_gate.py --report tests\rapport_face_gate.md
```
