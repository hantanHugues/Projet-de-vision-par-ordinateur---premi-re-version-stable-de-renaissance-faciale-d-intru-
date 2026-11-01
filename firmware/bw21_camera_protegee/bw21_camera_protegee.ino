/*
  BioGate : camera BW21-CBV-Kit, flux MJPEG protege.
  La partie Wi-Fi vient de wifi_et_camera_test_for_ai_thinker, qui fonctionne.

  Premier demarrage : le moniteur serie (115200, fin de ligne "Newline") demande le reseau Wi-Fi,
  son mot de passe, puis une cle pour le flux. Tout est garde dans la memoire de la carte.
  Ensuite la carte se reconnecte toute seule au dernier reseau. Pour changer de reseau ou de cle :
  envoyer une touche dans les 5 secondes qui suivent le demarrage.

  Le flux est sur http://biogate:CLE@ADRESSE_IP/stream (la cle que vous avez choisie).
  Ce que la carte verifie : une seule adresse (/stream), l'identifiant et la cle, une requete
  courte et rapide, et un blocage de 30 s apres 5 refus de suite.
  Ce qu'elle ne peut pas faire avec la bibliotheque Ameba : HTTPS, filtrage par adresse IP.
  Le choix "Erase All Flash Memory" du menu Outils efface aussi le reseau et la cle memorises.
*/

#include <WiFi.h>
#include <FlashMemory.h>
#include "VideoStream.h"

#define CHANNEL 0
#define IDENTIFIANT "biogate"

#define MARQUE 0xB10C6A7E           // prouve que la memoire contient bien nos reglages
#define TAILLE_MEMOIRE 0x1000

#define DELAI_REQUETE_MS 3000       // temps maximal pour recevoir la requete
#define TAILLE_MAX_REQUETE 1024
#define ECHECS_MAX 5                // refus de suite avant blocage
#define BLOCAGE_MS 30000

// 640x480 : la taille que BioGate analyse
VideoSetting config(VIDEO_VGA, CAM_FPS, VIDEO_JPEG, 1);
WiFiServer server(80);

uint32_t img_addr = 0;
uint32_t img_len = 0;
#define PART_BOUNDARY "123456789000000000000987654321"
char* DEBUT_FLUX = "--" PART_BOUNDARY "\r\n";
char* STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
char* IMG_HEADER = "Content-Type: image/jpeg\r\nContent-Length: %lu\r\n\r\n";

// Ce qui est garde dans la memoire de la carte
struct Reglages {
    uint32_t marque;
    char ssid[33];
    char motDePasse[65];
    char cle[33];
};
Reglages reglages;
String jetonAttendu;                // "biogate:cle" en base64, compare a l'en-tete Authorization

int echecs = 0;
bool bloque = false;
unsigned long debutBlocage = 0;

// ---------- Memoire de la carte ----------

void chargerReglages()
{
    FlashMemory.begin(FLASH_MEMORY_APP_BASE, TAILLE_MEMOIRE);
    FlashMemory.read();
    memcpy(&reglages, FlashMemory.buf, sizeof(reglages));
}

void sauverReglages()
{
    reglages.marque = MARQUE;
    memcpy(FlashMemory.buf, &reglages, sizeof(reglages));
    FlashMemory.write();
}

// ---------- Saisie au moniteur serie ----------

String lireLigne()
{
    while (Serial.available() == 0) {
        delay(10);
    }
    String ligne = Serial.readStringUntil('\n');
    ligne.trim();
    return ligne;
}

bool cleValable(const String& cle)
{
    if (cle.length() < 12 || cle.length() > 32) {
        return false;
    }
    for (unsigned int i = 0; i < cle.length(); i++) {
        if (!isalnum(cle[i])) {
            return false;
        }
    }
    return true;
}

void afficherChiffrement(int type)
{
    switch (type) {
        case ENC_TYPE_WEP:  Serial.print("WEP"); break;
        case ENC_TYPE_WPA:  Serial.print("WPA"); break;
        case ENC_TYPE_WPA2: Serial.print("WPA2"); break;
        case ENC_TYPE_WPA3: Serial.print("WPA3"); break;
        case ENC_TYPE_NONE: Serial.print("Aucun (ouvert)"); break;
        default:            Serial.print("Inconnu"); break;
    }
}

// Montre les reseaux, demande le choix, le mot de passe et la cle du flux, puis memorise.
void configurer()
{
    WiFi.status();    // active l'interface avant de scanner

    int nombre = -1;
    for (int essai = 0; nombre == -1 && essai < 20; essai++) {
        nombre = WiFi.scanNetworks();
        if (nombre == -1) {
            delay(1000);
        }
    }
    if (nombre <= 0) {
        Serial.println("Aucun reseau trouve. Redemarrez la carte (bouton EN) et recommencez.");
        while (true) {
            delay(1000);
        }
    }

    Serial.println();
    Serial.println("=== Reseaux Wi-Fi ===");
    for (int i = 0; i < nombre; i++) {
        Serial.print(i);
        Serial.print(") ");
        Serial.print(WiFi.SSID(i));
        Serial.print("   (signal ");
        Serial.print(WiFi.RSSI(i));
        Serial.print(" dBm, ");
        afficherChiffrement(WiFi.encryptionType(i));
        Serial.println(")");
    }

    Serial.println("Numero du reseau, puis Entree :");
    int choix = lireLigne().toInt();
    if (choix < 0 || choix >= nombre) {
        Serial.println("Numero invalide. Redemarrez la carte et recommencez.");
        while (true) {
            delay(1000);
        }
    }
    memset(&reglages, 0, sizeof(reglages));
    strncpy(reglages.ssid, WiFi.SSID(choix), sizeof(reglages.ssid) - 1);

    Serial.println("Mot de passe du reseau, puis Entree :");
    lireLigne().toCharArray(reglages.motDePasse, sizeof(reglages.motDePasse));

    String cle = "";
    while (!cleValable(cle)) {
        Serial.println("Cle du flux (12 a 32 lettres ou chiffres, sans espace), puis Entree :");
        cle = lireLigne();
    }
    cle.toCharArray(reglages.cle, sizeof(reglages.cle));

    sauverReglages();
    Serial.println("Reseau et cle memorises.");
}

// Laisse 5 secondes pour reconfigurer : n'importe quelle touche suffit.
bool veutReconfigurer()
{
    Serial.print("Reseau memorise : ");
    Serial.println(reglages.ssid);
    Serial.println("Envoyez une touche dans les 5 secondes pour changer de reseau ou de cle.");
    for (int i = 0; i < 50; i++) {
        if (Serial.available() > 0) {
            while (Serial.available() > 0) {
                Serial.read();
            }
            return true;
        }
        delay(100);
    }
    return false;
}

// ---------- Wi-Fi ----------

// Reessaie sans fin : apres une coupure de courant, le routeur peut demarrer plus lentement que la carte.
void connecterWiFi()
{
    int etat = WL_IDLE_STATUS;
    while (etat != WL_CONNECTED) {
        Serial.print("Connexion a ");
        Serial.println(reglages.ssid);
        etat = WiFi.begin(reglages.ssid, reglages.motDePasse);
        if (etat != WL_CONNECTED) {
            delay(5000);
        }
    }
    // Sans cette ligne la carte s'endort entre deux paquets et met 7 a 30 s a repondre a une
    // premiere demande : OpenCV (BioGate) abandonne apres 30 s.
    WiFi.disablePowerSave();

    Serial.print("Connecte. Adresse IP : ");
    Serial.println(WiFi.localIP());

    // Pour reserver cette adresse dans le routeur : l'IP ne changera plus
    uint8_t mac[6];
    WiFi.macAddress(mac);
    Serial.print("Adresse MAC : ");
    for (int i = 0; i < 6; i++) {
        if (mac[i] < 16) {
            Serial.print("0");
        }
        Serial.print(mac[i], HEX);
        Serial.print(i < 5 ? ":" : "\n");
    }
}

// Si le Wi-Fi tombe en marche, on se reconnecte au reseau memorise.
void reconnecterSiPerdu()
{
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("Wi-Fi perdu, reconnexion...");
        connecterWiFi();
    }
}

// ---------- Protection du flux ----------

String base64(const String& texte)
{
    const char* table = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    String sortie = "";
    int n = texte.length();
    for (int i = 0; i < n; i += 3) {
        uint32_t bloc = (uint8_t)texte[i] << 16;
        if (i + 1 < n) bloc |= (uint8_t)texte[i + 1] << 8;
        if (i + 2 < n) bloc |= (uint8_t)texte[i + 2];
        sortie += table[(bloc >> 18) & 63];
        sortie += table[(bloc >> 12) & 63];
        sortie += (i + 1 < n) ? table[(bloc >> 6) & 63] : '=';
        sortie += (i + 2 < n) ? table[bloc & 63] : '=';
    }
    return sortie;
}

// Comparaison en temps constant : la duree ne revele pas ou la cle differe.
bool memeTexte(const String& recu, const String& attendu)
{
    uint8_t difference = (recu.length() != attendu.length()) ? 1 : 0;
    for (unsigned int i = 0; i < attendu.length(); i++) {
        char c = (i < recu.length()) ? recu[i] : 0;
        difference |= (uint8_t)(c ^ attendu[i]);
    }
    return difference == 0;
}

// Lit la requete avec une taille et un delai maximaux.
// Dit si elle demande bien GET /stream et si l'identifiant et la cle sont bons.
bool lireRequete(WiFiClient& client, bool& demandeLeFlux, bool& autorise)
{
    unsigned long debut = millis();
    String ligne = "";
    int recus = 0;
    bool premiereLigne = true;
    demandeLeFlux = false;
    autorise = false;

    // Lecture courte : client.available() attend sans fin un client qui ne dit rien,
    // ce qui bloquait la carte et rendait inutile le delai ci-dessous.
    client.setRecvTimeout(20);
    while (client.connected() && (millis() - debut) < DELAI_REQUETE_MS) {
        int lu = client.read();
        if (lu <= 0) {
            continue;             // rien recu pour l'instant
        }
        char c = lu;
        if (++recus > TAILLE_MAX_REQUETE) {
            return false;
        }
        if (c == '\n') {
            if (ligne.length() == 0) {
                return !premiereLigne;    // ligne vide : fin des en-tetes
            }
            if (premiereLigne) {
                demandeLeFlux = ligne.startsWith("GET /stream ");
                premiereLigne = false;
            } else {
                String minuscules = ligne;
                minuscules.toLowerCase();
                if (minuscules.startsWith("authorization: basic ")) {
                    String jeton = ligne.substring(21);
                    jeton.trim();
                    autorise = memeTexte(jeton, jetonAttendu);
                }
            }
            ligne = "";
        } else if (c != '\r') {
            if (ligne.length() >= 300) {
                return false;
            }
            ligne += c;
        }
    }
    return false;
}

void repondre(WiFiClient& client, const char* statut, const char* entete = "")
{
    client.print("HTTP/1.1 ");
    client.print(statut);
    client.print("\r\nConnection: close\r\nContent-Length: 0\r\n");
    client.print(entete);
    client.print("\r\n");
}

// ---------- Flux video ----------

void envoyerEntete(WiFiClient& client)
{
    client.print("HTTP/1.1 200 OK\r\nContent-type: multipart/x-mixed-replace; boundary=");
    client.println(PART_BOUNDARY);
    client.print("Transfer-Encoding: chunked\r\n");
    client.print("\r\n");
}

void envoyerMorceau(WiFiClient& client, uint8_t* buf, uint32_t len)
{
    uint8_t taille[64] = {0};
    uint8_t n = snprintf((char*)taille, 64, "%lX\r\n", len);
    client.write(taille, n);
    client.write(buf, len);
    client.print("\r\n");
}

void diffuserLeFlux(WiFiClient& client)
{
    envoyerEntete(client);
    // Ligne de separation avant la premiere image : un navigateur s'en passe, pas OpenCV (BioGate)
    envoyerMorceau(client, (uint8_t*)DEBUT_FLUX, strlen(DEBUT_FLUX));
    // La bibliotheque ne signale jamais un echec d'ecriture : sans la lecture ci-dessous, la boucle
    // ne saurait pas que le client est parti et la carte resterait bloquee sur lui.
    client.setRecvTimeout(20);
    while (client.connected()) {
        client.read();            // le client n'envoie plus rien : lire sert a voir s'il est parti
        Camera.getImage(CHANNEL, &img_addr, &img_len);
        uint8_t entete[64] = {0};
        uint8_t n = snprintf((char*)entete, 64, IMG_HEADER, img_len);
        envoyerMorceau(client, entete, n);
        envoyerMorceau(client, (uint8_t*)img_addr, img_len);
        envoyerMorceau(client, (uint8_t*)STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
        delay(5);
    }
}

// ---------- Programme ----------

void setup()
{
    Serial.begin(115200);
    delay(1000);

    chargerReglages();
    if (reglages.marque != MARQUE || veutReconfigurer()) {
        configurer();
    }
    jetonAttendu = base64(String(IDENTIFIANT) + ":" + reglages.cle);

    connecterWiFi();

    Camera.configVideoChannel(CHANNEL, config);
    Camera.videoInit();
    Camera.channelBegin(CHANNEL);
    server.begin();
    Serial.println("Camera prete. Flux sur /stream, identifiant biogate et votre cle.");
}

void loop()
{
    reconnecterSiPerdu();

    WiFiClient client = server.available();
    if (!client) {
        delay(20);
        return;
    }

    if (bloque && (millis() - debutBlocage) < BLOCAGE_MS) {
        repondre(client, "429 Too Many Requests");
        client.stop();
        return;
    }
    bloque = false;

    bool demandeLeFlux = false;
    bool autorise = false;
    bool complete = lireRequete(client, demandeLeFlux, autorise);

    if (!complete) {
        repondre(client, "400 Bad Request");
    } else if (!demandeLeFlux) {
        repondre(client, "404 Not Found");
    } else if (!autorise) {
        echecs++;
        Serial.print("Acces refuse (");
        Serial.print(echecs);
        Serial.println(").");
        repondre(client, "401 Unauthorized", "WWW-Authenticate: Basic realm=\"BioGate\"\r\n");
        delay(1000);
        if (echecs >= ECHECS_MAX) {
            bloque = true;
            debutBlocage = millis();
            echecs = 0;
            Serial.println("Trop d'echecs : blocage de 30 secondes.");
        }
    } else {
        echecs = 0;
        Serial.println("Acces autorise : flux demarre.");
        diffuserLeFlux(client);
        Serial.println("Client deconnecte.");
    }
    client.stop();
}
