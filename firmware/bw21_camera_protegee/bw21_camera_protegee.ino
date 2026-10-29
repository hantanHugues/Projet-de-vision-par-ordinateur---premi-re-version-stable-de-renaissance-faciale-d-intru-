/*
  BioGate : caméra BW21-CBV (Ai-Thinker, RTL8735B) en flux MJPEG protégé.

  Reprend le sketch qui fonctionnait (WiFi + MJPEG de l'exemple HTTPDisplayJPEGContinuous) et
  ajoute le contrôle d'accès qui lui manquait : n'importe qui sur le réseau pouvait voir l'image.

  Ce que le programme fait :
    - une seule adresse sert l'image : GET /stream ; tout le reste reçoit 404 ou 405 ;
    - l'accès exige un identifiant et une clé aléatoire (HTTP Basic), comparés en temps constant ;
    - la requête est lue avec une taille maximale et un délai maximal : un client qui se connecte
      sans rien envoyer ne bloque plus la caméra (le sketch d'origine attendait indéfiniment) ;
    - après MAX_FAILS refus de suite, la caméra refuse tout pendant LOCKOUT_MS (freine la force brute) ;
    - la clé n'est jamais écrite sur le port série ; le journal ne montre que le verdict.

  Ce qu'il ne fait pas, par limite de la bibliothèque Ameba (version 4.1.0) :
    - pas de HTTPS : la clé circule en clair sur le Wi-Fi (chiffré en WPA2, voir ci-dessous) ;
    - pas de filtrage par adresse IP : WiFiClient n'expose pas l'adresse du client.
  La protection repose donc sur trois choses ensemble : réseau Wi-Fi WPA2/WPA3 isolé, clé longue
  et aléatoire, limites ci-dessus.

  Mise en place :
    1. python generer_secrets.py   (crée secrets.h avec une clé aléatoire et cle_flux.txt)
    2. ouvrir secrets.h et remplacer WIFI_SSID et WIFI_PASS par ceux de votre réseau
    3. carte : AMB82-MINI (même puce RTL8735B), téléverser, ouvrir le moniteur série à 115200
    4. l'adresse IP s'affiche ; l'URL à donner à BioGate est dans cle_flux.txt
*/

#include <WiFi.h>
#include "VideoStream.h"
#include "secrets.h"

#define CHANNEL 0
#define MAX_HEADER_BYTES   1024     // taille maximale de la requête
#define MAX_LINE_BYTES     300      // taille maximale d'une ligne d'en-tête
#define REQUEST_TIMEOUT_MS 3000     // délai maximal pour recevoir la requête
#define MAX_FAILS          5        // refus de suite avant verrouillage
#define LOCKOUT_MS         30000    // durée du verrouillage
#define FAIL_PENALTY_MS    1000     // attente imposée après un refus

// 640x480 : taille analysée par BioGate, plus légère pour le Wi-Fi que 1024x576
VideoSetting config(VIDEO_VGA, CAM_FPS, VIDEO_JPEG, 1);

char ssid[] = WIFI_SSID;
char pass[] = WIFI_PASS;
int status = WL_IDLE_STATUS;
WiFiServer server(80);

uint32_t img_addr = 0;
uint32_t img_len = 0;

#define PART_BOUNDARY "123456789000000000000987654321"
char* STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
char* IMG_HEADER = "Content-Type: image/jpeg\r\nContent-Length: %lu\r\n\r\n";

int failCount = 0;
bool lockedOut = false;
unsigned long lockStart = 0;

void sendHeader(WiFiClient& client)
{
    client.print("HTTP/1.1 200 OK\r\nContent-type: multipart/x-mixed-replace; boundary=");
    client.println(PART_BOUNDARY);
    client.print("Cache-Control: no-store\r\n");
    client.print("Transfer-Encoding: chunked\r\n");
    client.print("\r\n");
}

void sendChunk(WiFiClient& client, uint8_t* buf, uint32_t len)
{
    uint8_t chunk_buf[64] = {0};
    uint8_t chunk_len = snprintf((char*)chunk_buf, 64, "%lX\r\n", len);
    client.write(chunk_buf, chunk_len);
    client.write(buf, len);
    client.print("\r\n");
}

// Réponse courte sans corps ; la connexion est fermée juste après.
void reply(WiFiClient& client, const char* statusLine, const char* extraHeader = "")
{
    client.print("HTTP/1.1 ");
    client.print(statusLine);
    client.print("\r\nConnection: close\r\nContent-Length: 0\r\nCache-Control: no-store\r\n");
    client.print(extraHeader);
    client.print("\r\n");
}

// Comparaison en temps constant : la durée ne révèle pas à partir de quel caractère la clé diffère.
bool constantTimeEquals(const String& given, const char* expected)
{
    size_t expectedLen = strlen(expected);
    uint8_t diff = (given.length() != expectedLen) ? 1 : 0;
    for (size_t i = 0; i < expectedLen; i++) {
        char g = (i < given.length()) ? given[i] : 0;
        diff |= (uint8_t)(g ^ expected[i]);
    }
    return diff == 0;
}

// Lit la requête (ligne de requête + en-têtes) avec taille et délai bornés.
// Retourne false si la requête est incomplète, trop grosse ou trop lente.
bool readRequest(WiFiClient& client, bool& isStreamRequest, bool& authorized)
{
    unsigned long start = millis();
    String line = "";
    size_t total = 0;
    bool firstLine = true;
    isStreamRequest = false;
    authorized = false;

    while (client.connected() && (millis() - start) < REQUEST_TIMEOUT_MS) {
        if (!client.available()) {
            delay(2);
            continue;
        }
        char c = client.read();
        if (++total > MAX_HEADER_BYTES) {
            return false;
        }
        if (c == '\n') {
            if (line.length() == 0) {
                return !firstLine;    // ligne vide = fin des en-têtes
            }
            if (firstLine) {
                isStreamRequest = line.startsWith("GET /stream ") || line.equals("GET /stream");
                firstLine = false;
            } else {
                String lower = line;
                lower.toLowerCase();
                if (lower.startsWith("authorization:")) {
                    String value = line.substring(14);
                    value.trim();
                    String valueLower = value;
                    valueLower.toLowerCase();
                    if (valueLower.startsWith("basic ")) {
                        String token = value.substring(6);
                        token.trim();
                        authorized = constantTimeEquals(token, STREAM_AUTH_B64);
                    }
                }
            }
            line = "";
        } else if (c != '\r') {
            if (line.length() >= MAX_LINE_BYTES) {
                return false;
            }
            line += c;
        }
    }
    return false;
}

void connectWiFi()
{
    status = WL_IDLE_STATUS;
    while (status != WL_CONNECTED) {
        Serial.print("Connexion au reseau ");
        Serial.println(ssid);
        status = WiFi.begin(ssid, pass);
        delay(5000);
    }
    Serial.print("Connecte. Adresse IP : ");
    Serial.println(WiFi.localIP());
}

void setup()
{
    Serial.begin(115200);
    delay(1000);

    connectWiFi();

    Camera.configVideoChannel(CHANNEL, config);
    Camera.videoInit();
    Camera.channelBegin(CHANNEL);
    server.begin();
    Serial.println("Camera prete. Flux protege sur /stream (identifiant et cle requis).");
}

void serveStream(WiFiClient& client)
{
    sendHeader(client);
    while (client.connected()) {
        Camera.getImage(CHANNEL, &img_addr, &img_len);
        uint8_t chunk_buf[64] = {0};
        uint8_t chunk_len = snprintf((char*)chunk_buf, 64, IMG_HEADER, img_len);
        sendChunk(client, chunk_buf, chunk_len);
        sendChunk(client, (uint8_t*)img_addr, img_len);
        sendChunk(client, (uint8_t*)STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
        delay(5);
    }
}

void loop()
{
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("Wi-Fi perdu, reconnexion...");
        connectWiFi();
    }

    WiFiClient client = server.available();
    if (!client) {
        delay(20);
        return;
    }

    if (lockedOut) {
        if ((millis() - lockStart) < LOCKOUT_MS) {
            reply(client, "429 Too Many Requests", "Retry-After: 30\r\n");
            client.stop();
            return;
        }
        lockedOut = false;
        failCount = 0;
    }

    bool isStreamRequest = false;
    bool authorized = false;
    bool complete = readRequest(client, isStreamRequest, authorized);

    if (!complete) {
        reply(client, "400 Bad Request");
        Serial.println("Requete incomplete ou trop grosse : refusee.");
    } else if (!isStreamRequest) {
        reply(client, "404 Not Found");
        Serial.println("Chemin inconnu : refuse.");
    } else if (!authorized) {
        failCount++;
        Serial.print("Acces refuse (");
        Serial.print(failCount);
        Serial.print("/");
        Serial.print(MAX_FAILS);
        Serial.println(").");
        reply(client, "401 Unauthorized", "WWW-Authenticate: Basic realm=\"BioGate\"\r\n");
        delay(FAIL_PENALTY_MS);
        if (failCount >= MAX_FAILS) {
            lockedOut = true;
            lockStart = millis();
            Serial.println("Trop d'echecs : verrouillage temporaire.");
        }
    } else {
        failCount = 0;
        Serial.println("Acces autorise : flux demarre.");
        serveStream(client);
        Serial.println("Client deconnecte.");
    }
    client.stop();
}
