# Mémoire de Licence (LaTeX)

Modèle inspiré des mémoires de Licence de l'IFRI/UAC. Moteur : pdfLaTeX, avec `latexmk`.

## Compiler

```bash
cd memoire
latexmk memoire.tex        # produit build/memoire.pdf
```

Le PDF `build/memoire.pdf` est le seul fichier de `build/` versionné (voir `.gitignore`).

## Organisation

- `memoire.tex` : fichier principal et informations de la page de garde (auteur, titre, option, encadrant, jury, année).
- `preambule.tex` : paquets, mise en forme, en-têtes, commandes de travail.
- `frontmatter/` : page de garde, dédicace, remerciements, résumé, abstract, acronymes, glossaire.
- `chapitres/` : introduction, chapitres 1 à 3, conclusion.
- `biblio/` : bibliographie et webographie (aucune source n'est saisie sans avoir été fournie).
- `images/` : logos et figures.

## Marqueurs visibles dans le PDF

- `[SOURCE À FOURNIR]` : affirmation qui attend une référence réelle.
- `[… à confirmer]` : information manquante sur la page de garde ou ailleurs.
- `À rédiger.` : section en attente de contenu validé.
