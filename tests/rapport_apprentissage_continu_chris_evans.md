# Rapport de test — Apprentissage continu face au changement d'apparence

*Généré le 03/09/2026 à 18:11*

## Méthodologie

Protocole en 4 étapes utilisant directement le moteur de reconnaissance du système
(FaceNet512, distance cosinus, seuil configuré), sur une base de données isolée
pour ne pas affecter les profils réels :

1. Enrôlement d'un profil de référence avec une photo "avant".
2. Tentative de reconnaissance d'une photo "après" (changement d'apparence) **avant**
   tout apprentissage — établit que le problème existe réellement.
3. Simulation du mécanisme d'apprentissage continu (Ground Truth Learning) : le
   visage "après" est ajouté comme gabarit supplémentaire du même profil, exactement
   comme le ferait une confirmation par empreinte digitale en conditions réelles.
4. Nouvelle tentative de reconnaissance sur une photo "après" — différente de celle
   utilisée pour l'apprentissage si possible — pour prouver la généralisation et pas
   seulement un rappel exact.

## Résultats

- **Sujet de test** : Chris Evans
- **Seuil de reconnaissance** (`FACE_RECOGNITION_THRESHOLD`) : 0.35
- **Rigueur du protocole** : Photo de validation différente de celle d'apprentissage — résultat scientifiquement probant.

| Étape | Distance cosinus | Résultat |
|---|---|---|
| 2. BASELINE — reconnaissance avant apprentissage | 0.4722 | NON RECONNU (attendu à ce stade) |
| 4. VALIDATION — reconnaissance après apprentissage | 0.224 | RECONNU |

## Conclusion

✅ **Hypothèse confirmée** : le système échoue à reconnaître le sujet après changement d'apparence tant qu'aucun apprentissage n'a eu lieu, et réussit après une seule confirmation d'identité — ce qui valide la légitimité du mécanisme d'apprentissage continu face au vieillissement et aux changements naturels d'apparence.

## Sujet et images utilisées

Sujet choisi pour sa couverture photographique publique sous licence libre sur
plusieurs années, ce qui permet de démontrer à la fois le changement de pilosité
faciale et le vieillissement naturel (11 ans d'écart entre la première et la
dernière photo) : **Chris Evans**, acteur américain.

| Rôle dans le test | Année | Apparence | Fichier | Auteur | Licence | Source |
|---|---|---|---|---|---|---|
| Référence (« avant ») | 2014 | Rasé de près | `tests/photos_test_apprentissage_continu/avant_2014_Chris_Evans_rase.jpg` | Gage Skidmore | CC BY-SA 3.0 | [commons.wikimedia.org/wiki/File:Chris_Evans_by_Gage_Skidmore_(cropped).jpg](https://commons.wikimedia.org/wiki/File:Chris_Evans_by_Gage_Skidmore_(cropped).jpg) |
| Apprentissage (« après » #1) | 2019 | Barbe pleine | `tests/photos_test_apprentissage_continu/apres1_2019_Chris_Evans_barbe.jpg` | Office du Représentant Don Young (Chambre des représentants des É.-U.) | Domaine public | [commons.wikimedia.org/wiki/File:Chris_Evans_in_2019.jpg](https://commons.wikimedia.org/wiki/File:Chris_Evans_in_2019.jpg) |
| Validation (« après » #2) | 2024 | Barbe pleine, photo différente | `tests/photos_test_apprentissage_continu/apres2_2024_Chris_Evans_barbe.jpg` | Amy Martin Photography | CC BY-SA 4.0 | [commons.wikimedia.org/wiki/File:Chris_Evans_Red_2024.jpg](https://commons.wikimedia.org/wiki/File:Chris_Evans_Red_2024.jpg) |

Les trois images proviennent de Wikimedia Commons, sous licence libre, avec
attribution du photographe telle qu'exigée par leur licence respective. Aucune
image n'est republiée ici — seuls les liens vers les pages de description
originales sont fournis, conformément aux conditions de ces licences.

## Reproductibilité

```
.venv-deepface\Scripts\python.exe tests\test_continuous_learning.py ^
    --clean tests\photos_test_apprentissage_continu\avant_2014_Chris_Evans_rase.jpg ^
    --after1 tests\photos_test_apprentissage_continu\apres1_2019_Chris_Evans_barbe.jpg ^
    --after2 tests\photos_test_apprentissage_continu\apres2_2024_Chris_Evans_barbe.jpg ^
    --name "Chris Evans" ^
    --report tests\rapport_apprentissage_continu_chris_evans.md
```

Base de données temporaire, isolée de `database/visages.db` — aucun profil réel n'est modifié.
