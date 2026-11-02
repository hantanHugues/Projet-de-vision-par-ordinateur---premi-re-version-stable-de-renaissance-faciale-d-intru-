# Décisions prises ou en attente (à appliquer après la lecture complète de l'étudiant)

L'étudiant lit d'abord tout le mémoire et revient avec ses remarques. Rien de ce qui suit n'est encore appliqué au texte.

## Décidées
- **D1** : « se prêtent à la présentation d'une photographie » devient « sont vulnérables à l'usurpation par photographie » (résumé, abstract, introduction).
- **D4** : le résumé et l'abstract sont réécrits selon la fiche de style (contexte, problème, objectif, démarche, résultats ; 150 à 200 mots ; pas de chiffre ; mots courants), avec le brouillon 3 ci-dessous.
- **D5** : garder « Au Bénin… » en ouverture du résumé.
- **D6** : garder la dernière phrase sur l'efficacité du geste, à mesurer.

## Règle de placement (D8, énoncée par l'étudiant)
Le risque d'une mise à jour sans contrôle (apprentissage erroné, 47,9 %) est un détail du troisième problème. Il ne se dit qu'à sa place : chapitre 2, section 2.4.4 (raison de la conception), chapitre 3, section 3.2.7.1 et tableau de synthèse (mesure). À retirer ou à réduire ailleurs : résumé et abstract (le brouillon 3 perd « car une mise à jour erronée ferait accepter un inconnu » ; il garde « améliore la reconnaissance » et la confirmation par l'empreinte dans la démarche), problématique de l'introduction (dernière phrase), bilan du chapitre 3 (paragraphe « Troisièmement »), conclusion générale. Le « Contexte et justification » (D7) ne le mentionne pas.

## En attente
- **D2** : remplacer « supportent mal les changements d'apparence de leurs utilisateurs ». Proposition : « perdent en fiabilité lorsque le visage de leurs utilisateurs évolue (vieillissement, barbe, coiffure) ». Le brouillon 3 l'intègre déjà sous la forme « lorsque le visage de leurs utilisateurs évolue ».
- **D3** : ajouter ou non un chiffre sur les photographies datées. Avec D4 (pas de chiffre dans le résumé), la réponse probable est non.

## Brouillon 3 du résumé (français)
Au Bénin, le coût de l'accès à Internet et l'instabilité de l'alimentation électrique conviennent mal aux systèmes de contrôle d'accès par reconnaissance faciale qui envoient les images à un service en ligne. Ces systèmes sont, de plus, vulnérables à l'usurpation par photographie et perdent en fiabilité lorsque le visage de leurs utilisateurs évolue. Face à ces limites, ce projet vise à concevoir et à implémenter BioGate, un prototype de contrôle d'accès par reconnaissance faciale exécuté en local. Une démarche itérative a été adoptée : le système détecte et suit les personnes devant la caméra, compare leur visage à celui des personnes enregistrées, demande un geste tiré au sort pour vérifier leur présence et met à jour les données d'une personne dont le visage change, après confirmation par l'empreinte digitale. Il comprend aussi une alerte d'intrusion par Telegram et un tableau de bord de supervision. Les essais montrent que cette mise à jour améliore la reconnaissance. L'efficacité du geste contre les attaques reste à mesurer.

Version anglaise à produire dans le même esprit.

## Points de style relevés (à corriger au travail final)
Résumé : jargon non défini (profil, vecteur, seuil, second facteur, pipeline). Introduction : « beaucoup de calculs » ; « références enregistrées » (ambigu : dire « données enregistrées »). Chapitre 1 : « beaucoup de foyers supportent difficilement » ; « très rapide » ; « vraisemblablement » ; « on peut envisager ». Chapitre 2 : « intrus fantômes » ; « calibrée de façon empirique » ; « tourne » (dire « s'exécute ») ; « calcul très léger ». Chapitre 3 : « au prix de nombreux refus », « un peu plus haut », « bien plus grave », « très photographiées » ; « caméra de porte » (dire « caméra installée à l'entrée d'un lieu ») ; chien de garde, contre-épreuve, recette (définir au premier emploi). Termes à définir avant leur première apparition : seuil, pipeline, revérification, contre-épreuve, recette.

## Reste à mesurer ou à fournir par l'étudiant
Voir `QUESTIONS_ET_MANQUES.md`. En résumé : essais d'attaque photo et vidéo, débit de la chaîne complète (script à écrire si l'étudiant le demande), couverture, dédicace, remerciements, capture de la page de surveillance, photo du montage.

## D7 (contexte et justification) : précisions
Cinq points : constat général ; situation locale (Bénin) ; trois limites des solutions actuelles avec une preuve chacune ; cadre légal en deux phrases ; solution proposée. Usurpation : argument de l'auteur (les caméras locales sans gros serveur sont trop peu performantes pour résister sans capteur dédié, sauf cas particuliers comme Apple), à sourcer ou à présenter comme raisonnement de l'auteur. Changement de visage : montrer le problème (un visage enregistré une seule fois devient moins représentatif, l'écart grandit, les refus se multiplient ; Best-Rowden et Jain, Deb) et la raison d'être de l'adaptation (Face ID s'adapte et demande le code avant une mise à jour importante, Apple 102381), sans parler du risque d'apprentissage erroné (D8). La contrainte de calcul passe dans le point « solution proposée ».

## D11 : mesure de performance du pipeline (dernier push de main, commit fdba84f, 02/11)
À intégrer au chapitre 3 (nouvelle sous-section « Performance », tableaux des étapes, des régimes, du temps de décision, endurance) et à corriger partout où figure « de l'ordre de deux à cinq images par seconde » (chapitre 2, section 2.2.3 ; chapitre 3, section 3.2.3 ; conclusion du chapitre 3 ; conclusion générale). Valeurs mesurées : identification 401 ms (médiane, environ 2,5 images par seconde, FaceNet512 : 74 %) ; régime stable médiane 30 ms et jusqu'à 18,3 images par seconde ; YOLO 21 ms à 320 px contre 43 ms à 640 px ; cache en mémoire 46 fois plus rapide que SQLite à 1 600 vecteurs ; décision d'un résident 0,45 s ; endurance de 5 minutes sans dégradation (18,42 → 18,47 images par seconde, mémoire stable). Le coût de Haar est de 84 ms sur la silhouette de cette scène (58 ms dans le rapport du Face Gate) : citer la scène. Limites : scène = photo fixe sur fond noir, une machine, CPU seul, pas de Raspberry Pi. Restent non faits d'après le plan : essais d'attaque photo et vidéo, résilience (serveur tué puis relancé, coupure d'Internet pendant une alerte).
