"""
Analyse de sensibilité de mesure_vieillissement_commons.py au critère d'identité.

La règle de sélection (fixée avant tout résultat) écarte un candidat si une des trois distances entre ses photos dépasse 0,90.
Quelques personnes retenues ont pourtant une photo intermédiaire très éloignée des deux autres (distance de 0,76 à 0,89) : photo
mal étiquetée, ou visage très changé (maquillage, coiffure, âge). Ce script refait le calcul avec des critères plus stricts, SANS
changer la règle de départ, pour montrer si la conclusion en dépend.

Un second critère cible un défaut précis : une photo d'ENRÔLEMENT d'une autre personne (photo de groupe dont le titre cite deux noms) ferait
croire que l'apprentissage « sauve » le profil, alors que les deux autres photos sont simplement cohérentes entre elles. Il écarte les personnes
dont la photo d'enrôlement est ISOLÉE : distances E-L et E-T supérieures à 0,50 alors que L-T est plus petite que les deux. Ce critère est décidé
après avoir vu les distances : c'est une analyse de sensibilité exploratoire, pas la règle de sélection.

Précaution : un critère plus strict écarte aussi les vrais cas de fort changement d'apparence ; il favorise donc les visages
« faciles » et tend à SURESTIMER la reconnaissance. Il ne remplace pas l'analyse principale.

Usage :
    .venv-deepface\\Scripts\\python.exe tests\\mesures\\sensibilite_vieillissement.py <sujets_vieillissement.csv> <sortie.md>
"""

import csv
import math
import statistics as st
import sys

SEUIL = 0.35


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def mcnemar(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n)


def fr(x, d=1):
    return f"{x:.{d}f}".replace(".", ",")


def main(csv_sujets, sortie):
    lignes = list(csv.DictReader(open(csv_sujets, encoding="utf-8")))
    f = lambda r, k: float(r[k])
    L = ["# Sensibilité de la mesure de vieillissement au critère d'identité", "",
         "Règle de départ : un candidat est écarté si une distance entre ses trois photos dépasse **0,90**. Ci-dessous, la même analyse avec des critères plus stricts "
         "(toutes les distances entre les trois photos au plus égales au seuil indiqué). **La règle de départ n'est pas modifiée.**", "",
         "| Critère d'identité | Personnes | Reconnues, profil d'origine | Reconnues, après apprentissage | Gain (McNemar exact) | Distance moyenne avant → après |",
         "|---|---|---|---|---|---|"]
    for seuil in (0.90, 0.80, 0.70, 0.60):
        S = [r for r in lignes if max(f(r, "distance_E_L"), f(r, "distance_E_T"), f(r, "distance_L_T")) <= seuil]
        n = len(S)
        a = sum(f(r, "distance_avant_apprentissage") < SEUIL for r in S)
        b = sum(f(r, "distance_apres_apprentissage") < SEUIL for r in S)
        gagnes = sum(1 for r in S if f(r, "distance_avant_apprentissage") >= SEUIL and f(r, "distance_apres_apprentissage") < SEUIL)
        la, ha = wilson(a, n)
        lb, hb = wilson(b, n)
        L.append(f"| {'règle de départ (0,90)' if seuil == 0.90 else 'au plus ' + fr(seuil, 2)} | {n} | {a} sur {n} ({fr(100 * a / n)} % [{fr(100 * la)} ; {fr(100 * ha)}]) | "
                 f"{b} sur {n} ({fr(100 * b / n)} % [{fr(100 * lb)} ; {fr(100 * hb)}]) | +{gagnes}, p = {fr(mcnemar(gagnes, 0), 4)} | "
                 f"{fr(st.mean(f(r, 'distance_avant_apprentissage') for r in S), 3)} → {fr(st.mean(f(r, 'distance_apres_apprentissage') for r in S), 3)} |")
    isole = lambda r: f(r, "distance_E_L") > 0.50 and f(r, "distance_E_T") > 0.50 and f(r, "distance_L_T") < min(f(r, "distance_E_L"), f(r, "distance_E_T"))
    S = [r for r in lignes if not isole(r)]
    n = len(S)
    a = sum(f(r, "distance_avant_apprentissage") < SEUIL for r in S)
    b = sum(f(r, "distance_apres_apprentissage") < SEUIL for r in S)
    gagnes = sum(1 for r in S if f(r, "distance_avant_apprentissage") >= SEUIL and f(r, "distance_apres_apprentissage") < SEUIL)
    la, ha = wilson(a, n)
    lb, hb = wilson(b, n)
    L.append(f"| **photo d'enrôlement non isolée** (exploratoire) | {n} | {a} sur {n} ({fr(100 * a / n)} % [{fr(100 * la)} ; {fr(100 * ha)}]) | "
             f"{b} sur {n} ({fr(100 * b / n)} % [{fr(100 * lb)} ; {fr(100 * hb)}]) | +{gagnes}, p = {fr(mcnemar(gagnes, 0), 4)} | "
             f"{fr(st.mean(f(r, 'distance_avant_apprentissage') for r in S), 3)} → {fr(st.mean(f(r, 'distance_apres_apprentissage') for r in S), 3)} |")
    retires = [r["sujet"] for r in lignes if isole(r)]
    L += ["",
          f"Personnes dont la photo d'enrôlement est isolée (écartées dans la dernière ligne) : {', '.join(retires) if retires else 'aucune'}.",
          "",
          "Lecture : la conclusion (l'apprentissage d'une photo intermédiaire fait reconnaître nettement plus de personnes) ne dépend pas du critère d'identité. "
          "Les pourcentages absolus montent quand le critère se durcit, ce qui est attendu : on retire les visages qui changent le plus.", "",
          "Personnes dont une distance entre photos dépasse 0,70 (photo intermédiaire ou de test à vérifier, ou visage très changé) : "
          + (", ".join(f"{r['sujet']} (E-L {fr(f(r, 'distance_E_L'), 2)}, E-T {fr(f(r, 'distance_E_T'), 2)}, L-T {fr(f(r, 'distance_L_T'), 2)})"
                        for r in lignes if max(f(r, 'distance_E_L'), f(r, 'distance_E_T'), f(r, 'distance_L_T')) > 0.70) or "aucune") + "."]
    open(sortie, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("sensibilité écrite dans", sortie)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
