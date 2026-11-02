# Fiche de style : mémoires de Licence IFRI/UAC (références : Ayiwahoun, Sanni)

Sources lues : Espérance Ayiwahoun (63 p., AIoT pointage, option SE-IoT) et Dyanos Charbel Sanni (58 p., Clap Influence, Génie Logiciel).
Le mémoire de Gaël Dansou est ÉCARTÉ à la demande de l'utilisateur.
Règle : reprendre structure, conventions et ton. Ne jamais recopier ni paraphraser leurs phrases, chiffres ou sources.

## 1. Pièces liminaires (ordre)
Page de garde (République du Bénin, Ministère, UAC, IFRI + logos ; MÉMOIRE ; "pour l'obtention du Diplôme de Licence en Informatique" ;
Option ; Présenté par ; titre ; Sous la supervision de ; Membres du jury ; Année académique) ; Sommaire ; Dédicace ; Remerciements
(liste à puces : DG et DG adjoint IFRI, encadrants, corps professoral, jury, structure d'accueil, famille) ; Résumé (1 paragraphe,
150-200 mots : contexte, problème, objectif, démarche, résultats, + Mots clés 4-5) ; Abstract (traduction EN) ; Liste des figures ;
Liste des tableaux ; Liste des acronymes (avec renvoi de page) ; Glossaire (terme en gras, définition 1-3 phrases, renvoi de page).

## 2. Introduction générale (3 à 4 rubriques)
- Contexte et justification : constat général, puis situation locale (Bénin), puis limite des pratiques actuelles, puis solution proposée.
  Chiffres sourcés [n] ; texte légal cité (loi 2009-09, Code du numérique loi 2017-20).
- (Problématique : 1 constat en deux volets, organisationnel et technologique, puis UNE question en gras "Comment concevoir...?")
- Objectif du projet : objectif général (1 phrase "Concevoir et implémenter...") + objectifs secondaires/spécifiques en 4 puces.
- Organisation du document : 3 puces, "Le chapitre 1 présente... Le chapitre 2 décrit... Le chapitre 3 expose...".

## 3. Plan retenu (3 chapitres)
1. Revue de littérature et état de l'art
2. Conception / Analyse, conception et choix techniques
3. Implémentation, validation et perspectives (ou Résultats et discussion)
Puis Conclusion générale (et perspectives), Bibliographie, Webographie, Table des matières.

## 4. Gabarit d'un chapitre
- "Chapitre N" + titre.
- "Introduction" (non numérotée) : rappelle l'apport du chapitre précédent, énonce l'objectif, annonce le plan ("Dans un premier temps... Ensuite... Enfin...").
- Sections N.M, sous-sections N.M.K, chacune introduite par 1-2 phrases.
- "Conclusion" (non numérotée) : bilan du chapitre en 3-5 phrases + annonce du chapitre suivant ("Le chapitre 3 sera consacré à...").

## 5. Conventions de rédaction
- Registre impersonnel : "ce travail", "ce projet", "le système", voix passive ("a été conçu", "ont été testés"). Pas de "je" hors remerciements.
- Connecteurs récurrents : Cependant, Ainsi, De plus, Par ailleurs, Face à ces défis, Dans ce contexte, Néanmoins, En définitive.
- Verbes récurrents : permettre de, garantir, assurer, s'appuyer sur, mettre en œuvre, répondre aux besoins, s'inscrire dans.
- Puces : "**Terme** : explication." ; fin de ligne ";" et dernier élément ".".
- Définition d'un concept : "Un X est un/une ... permettant de ...", 1 à 3 phrases, sous-section dédiée.
- Tableau : annoncé par une phrase ("Le tableau 2.1 synthétise..."), légende AU-DESSUS ("TABLEAU 2.1 : ..."), numérotation par chapitre.
- Figure : légende EN DESSOUS ("FIGURE 2.1 : ..."), appelée dans le texte ("la figure 2.8 montre...").
- Acronyme : nom complet à la première occurrence, puis sigle ; sigles et termes du glossaire en lien.
- Citations numériques [n] ; bibliographie numérotée.

## 6. Contenu type par chapitre
Ch.1 : concepts clés ; limites des méthodes traditionnelles (chiffrées, sourcées) ; solutions existantes (description, "Ses principales
fonctionnalités sont :", "Malgré..., X présente certaines limites :") ; tableau comparatif (Oui/Non/Partiel, coût, limites) ; techniques
(évolution classique -> deep learning, métriques FAR/FRR/EER, biais NIST) ; cadre légal (Bénin + RGPD) ; analyse critique et positionnement ;
"Ces constats justifient la pertinence du projet".
Ch.2 : besoins fonctionnels / non fonctionnels (puces à étiquette en gras, objectifs chiffrés ex. "< 5 s") ; contraintes du contexte ;
tableau de synthèse ; architecture globale (figure + composants) ; sécurité (tableau technologies) ; gestion des pannes ; processus principal
en étapes numérotées 1 à 6 avec étiquette en gras ; gestion des erreurs ; diagrammes UML si pertinent (cas d'utilisation, description
textuelle : Cas / Acteur / Description / Pré-condition / Post-condition / Scénario basique-alternatif-exceptionnel ; classes ; séquences) ;
JUSTIFICATION DES CHOIX : "A, B et C ont été envisagés. Le choix de X s'explique par... Contrairement à Y, ...".
Ch.3 : implémentation par module (matériel, logiciel, boîtier), captures d'écran commentées ; protocole de test (durée, nombre de
participants, métriques) ; tableau "Métrique / Objectif / Résultat obtenu / Commentaires" ; résilience ; retour utilisateurs ;
discussion critique : bilan, limites observées (étiquettes en gras), axes d'amélioration ; perspectives ; conclusion avec les chiffres clés.
Discussion (Sanni) : "Premièrement... Deuxièmement... Troisièmement..." puis "Certaines limites subsistent néanmoins...".
Conclusion générale : rappel problématique, objectif, solution, technologies, résultats, limites, perspectives (liste de 3), phrase finale
("première pierre", "en définitive").

## 7. Bibliographie
"[n] Auteur, I. Titre en italique. Éditeur/Revue, volume(numéro), pages, année." Webographie à part :
"Organisation. Titre. URL. Consulté le JJ mois AAAA."

## 8. Défauts de ces mémoires à NE PAS reproduire
Espace manquant après un point (ex. "...structurée.Au Bénin"), coquilles, en-têtes "Chapter" en anglais, paragraphes-blocs de
discussion sans respiration, affirmations trop fortes ("imparable", "tous les objectifs atteints") sans donnée, répétitions de formules,
excès de gras. Aucun chiffre sans source ou sans mesure issue des tests de l'étudiant.
