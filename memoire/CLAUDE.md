# Règles permanentes pour le mémoire (à relire à chaque session)

1. **Avant d'écrire ou de réécrire un texte, relire `FICHE_DE_STYLE.md`** (style des deux mémoires de référence : registre impersonnel, voix passive, connecteurs, structure du résumé, de l'introduction, des chapitres). Ne pas écrire de mémoire. Ne pas citer le mémoire de Gaël Dansou ni celui d'Espérance Ayiwahoun dans le texte.
2. **Clarté d'abord** : chaque terme, sigle ou valeur est défini à sa première apparition (voir `QUESTIONS_ET_MANQUES.md`). Le résumé et l'introduction se comprennent seuls. Pas de chiffre sans mesure ni source.
3. **Style simple** : phrases courtes, mots simples, pas de tournure familière ni de formule vague. Le résumé ne présente pas de résultats chiffrés (voir `DECISIONS_EN_ATTENTE.md`).
4. **Ne modifier le texte qu'après accord** quand l'étudiant demande « pas de modification pour l'instant » : noter la décision dans `DECISIONS_EN_ATTENTE.md`, appliquer plus tard.
5. Annoncer en une ou deux phrases ce qui va être fait, puis recompiler, vérifier, commiter (message en français), pousser sur `claude/memoire-latex-telephone-h1vdti`, mettre à jour `build/memoire.pdf`. Jamais de poussée sur `main`, jamais de force push, pas de pull request sans demande.
6. Ne jamais inventer une source ou une mesure. Marqueurs rouges `\adonner{}` seulement pour ce que l'étudiant doit fournir.
7. Relire la section 9 de `FICHE_DE_STYLE.md` (règles complémentaires de l'étudiant) avant chaque rédaction : aucun terme du journal de travail dans le mémoire, aucune trace d'assistance, aucune histoire du développement, chaque terme défini à sa première apparition. Ne pas demander de source pour une évidence.
8. Livrer deux PDF : `build/memoire.pdf` (version propre) et `build/memoire_surligne.pdf` (passages réécrits surlignés ; commande propre : `latexmk -jobname=memoire_propre -pdflatex="pdflatex -interaction=nonstopmode -file-line-error %O '\def\versionpropre{1}\input{%S}'" memoire.tex`).
9. Terminer chaque réponse par un résumé de trois lignes : changements, état de compilation, ce qui reste.
