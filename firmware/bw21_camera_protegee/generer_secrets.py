"""
Génère secrets.h (lu par le sketch) et cle_flux.txt (l'URL à donner à BioGate).

La clé est tirée au hasard ici, jamais choisie ni affichée : elle ne passe ni par le terminal ni par
git (secrets.h et cle_flux.txt sont dans .gitignore). Les identifiants Wi-Fi restent à saisir à la
main dans secrets.h.

    python generer_secrets.py            # première fois
    python generer_secrets.py --force    # remplacer la clé (à refaire aussi dans BioGate)
"""

import base64
import os
import secrets
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SECRETS_H = os.path.join(HERE, "secrets.h")
KEY_FILE = os.path.join(HERE, "cle_flux.txt")
USER = "biogate"


def main(force=False):
    if os.path.exists(SECRETS_H) and not force:
        print("secrets.h existe déjà : rien n'est changé (--force pour remplacer la clé).")
        return 1

    # Reprend les identifiants Wi-Fi déjà saisis quand on change seulement la clé
    wifi_ssid, wifi_pass = "NOM_DU_RESEAU", "MOT_DE_PASSE_WIFI"
    if os.path.exists(SECRETS_H):
        for line in open(SECRETS_H, encoding="utf-8"):
            if line.startswith("#define WIFI_SSID"):
                wifi_ssid = line.split('"', 2)[1]
            elif line.startswith("#define WIFI_PASS"):
                wifi_pass = line.split('"', 2)[1]

    key = secrets.token_urlsafe(24)   # 32 caractères, 192 bits
    token = base64.b64encode(f"{USER}:{key}".encode()).decode()

    with open(SECRETS_H, "w", encoding="utf-8", newline="\n") as f:
        f.write("// Généré par generer_secrets.py : ne pas commiter (déjà dans .gitignore).\n")
        f.write(f'#define WIFI_SSID "{wifi_ssid}"\n')
        f.write(f'#define WIFI_PASS "{wifi_pass}"\n')
        f.write(f'#define STREAM_AUTH_B64 "{token}"\n')

    with open(KEY_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write("URL du flux à saisir dans BioGate (type mjpeg), en remplaçant IP_DE_LA_CARTE\n")
        f.write("par l'adresse affichée par la carte sur le moniteur série :\n\n")
        f.write(f"http://{USER}:{key}@IP_DE_LA_CARTE/stream\n")

    print("secrets.h et cle_flux.txt créés. Ouvrez secrets.h pour saisir le nom et le mot de passe Wi-Fi.")
    return 0


if __name__ == "__main__":
    sys.exit(main(force="--force" in sys.argv[1:]))
