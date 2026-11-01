# Mémoire de Licence (LaTeX) — gabarit officiel IFRI

Basé sur le gabarit officiel « New IFRI template latex 05-04-2020 (Bachelor / Licence) ».

## Compiler

```bash
cd memoire
latexmk memoire.tex        # produit build/memoire.pdf
```

Prérequis : TeX Live avec pdfLaTeX, `latexmk`, `makeglossaries`, et les paquets `glossaries`, `minitoc`,
`algorithm2e`, `pstricks`, `SIunits`, `nomencl`. Le PDF `build/memoire.pdf` est le seul fichier de `build/` versionné.

## Organisation (structure du gabarit)

- `memoire.tex` : fichier principal (ancien `main.tex`) et informations de la page de garde.
- `ifri.cls` : classe officielle de l'IFRI.
- `0-dedicace.tex`, `1-remerciements.tex`, `2-resume.tex` : pièces liminaires.
- `3-introduction.tex`, `4-conclusion.tex` : introduction et conclusion générales.
- `1-partie/`, `2-partie/`, `3-partie/` : chapitres 1 à 3.
- `glossaire_reduit.tex` : acronymes et glossaire.
- `biblio.bib` : références (vide tant qu'aucune source réelle n'est fournie).
- `images/` : logos UAC et IFRI du gabarit.
- `archive_provisoire/` : première version provisoire (imitation), conservée au cas où.

## Modifications faites par rapport au gabarit d'origine

- `ifri.cls` : `utf8x` + `ucs` remplacés par `utf8` (le gabarit ne compile pas avec un TeX Live récent sinon).
- `memoire.tex` : `\selectlanguage{french}` ajouté après le résumé (sinon « List of Figures » en anglais),
  liste des algorithmes retirée (vide), glossaire activé, bibliographie en attente de sources.

## Marqueurs visibles dans le PDF

- `[SOURCE À FOURNIR]` : affirmation qui attend une référence réelle.
- `[… à confirmer]` : information manquante.
- `À rédiger.` : section en attente de contenu validé.
