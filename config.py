"""
Configuration centralisée du système de surveillance IA.

Modifier ce fichier pour ajuster les paramètres — ne jamais hardcoder
de valeurs directement dans le code métier.
"""

# ============================================
# SOURCE VIDÉO
# ============================================
VIDEO_SOURCE_TYPE = "webcam"
WEBCAM_INDEX = 0
ESP32_URL = "http://192.168.1.100:81/stream"
VIDEO_FILE_PATH = ""
RTSP_URL = ""

# ============================================
# PARAMÈTRES D'AFFICHAGE
# ============================================
PROCESSING_WIDTH = 640
PROCESSING_HEIGHT = 480
WINDOW_NAME = "BioGate - Hub de Décision"

# ============================================
# LOGGING
# ============================================
LOG_LEVEL = "INFO"
VISUAL_LOG_LINES = 8

# ============================================
# IA - DÉTECTION YOLO (Phase 2)
# ============================================
YOLO_MODEL_PATH = "yolov8n.pt"
YOLO_CONFIDENCE_THRESHOLD = 0.5
YOLO_IOU = 0.35          # NMS : fusionner les boîtes qui se superposent à >35%
YOLO_IMAGE_SIZE = 320    # Downscaling intégré — optimisation CPU Edge
DETECT_ONLY_PERSONS = True

# ============================================
# IA - RECONNAISSANCE FACIALE (Phase 5)
# ============================================
# Seuil de distance cosinus FaceNet512 : 0.35 = équilibre robustesse/sécurité
# En dessous = même personne. Au dessus = intrus.
# Calibré empiriquement : 0.20 trop strict (faux négatifs), 0.60 trop laxiste (faux positifs)
FACE_RECOGNITION_THRESHOLD = 0.35

# Délai de re-vérification pour les identités déjà validées (secondes)
FACE_RECHECK_INTERVAL = 0.8

# Temps maximum pour identifier un inconnu avant de le classer Intrus (secondes).
# Il démarre à l'apparition du visage de face, pas à l'arrivée de la silhouette.
FACE_ANALYSIS_TIME_LIMIT = 1.0

# Même fenêtre quand un VIP déjà reconnu retombe en analyse (ANOMALIE après RECHECK ratés) :
# plus patiente, pour qu'une image de travers ne le classe pas intrus (secondes).
REANALYSIS_TIME_LIMIT = 5.0

# Un intrus provisoire reconnu comme un VIP à une distance inférieure à ceci est reclassé
# VIP tout de suite, sans attendre RECHECK_FAILURE_TOLERANCE résultats concordants.
FACE_STRONG_MATCH_DISTANCE = 0.25

# Image du dashboard remise à l'endroit pour les webcams locales (type usb), qui renvoient
# souvent un miroir. Affichage seulement : le pipeline IA reçoit l'image de la caméra, sans
# retournement. Les caméras IP (mjpeg, rtsp) ne sont jamais retournées.
DISPLAY_FLIP_HORIZONTAL_USB = True

# Second avis sur le visage trouvé par Haar (MediaPipe) : écarte les faux visages sur les
# vêtements. Faux = le détecteur Haar décide seul.
FACE_VALIDATION_ENABLED = True

# Un « intrus » est un visage inconnu, pas une silhouette sans visage : YOLO prend parfois une
# main pour une personne (84 % mesuré), et un torse trop près ou un passant de dos n'ont pas de
# visage de face. 0 (défaut) = une silhouette sans visage n'est JAMAIS classée intrus, elle reste
# en « Attente visage » (pas de photo, pas d'événement, pas d'alerte).
# > 0 = au bout de ce nombre de secondes sans visage, elle devient intrus provisoire (photo
# prise, alerte armée) : pour qu'un masque ou une capuche ne passe pas inaperçu.
FACE_ABSENT_LIMIT = 0.0

# Une silhouette qui n'a JAMAIS montré de visage et qui disparaît après avoir été présente au
# moins ce nombre de secondes laisse une trace discrète au journal (événement « passage sans
# visage » : ni photo, ni alerte à distance). Les détections plus brèves, typiques des
# clignotements de YOLO, sont ignorées. 0 = désactivé.
FACELESS_PASSAGE_MIN_SECONDS = 3.0

# ============================================
# BASE DE DONNÉES SQLite (Phase 5)
# ============================================
DB_PATH = "database/visages.db"

# ============================================
# SERVEUR FASTAPI (Phase 6)
# ============================================
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000
SERVER_ANALYZE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}/analyze_frame"
SERVER_ENROLL_URL  = f"http://{SERVER_HOST}:{SERVER_PORT}/enroll"

# ============================================
# MFA — Multi-Factor Authentication
# ============================================
# False = visage seul suffit pour ouvrir. True = empreinte OU liveness obligatoire.
MFA_REQUIRED = False

# Active le mode "mains libres" : sourire ou clignement comme alternative à l'empreinte
LIVENESS_ENABLED = True

# Seuils Trust Score (%)
TRUST_FACE_THRESHOLD        = 60   # Visage reconnu → déclenche MFA
TRUST_LIVENESS_THRESHOLD    = 85   # Liveness réussie → accès
TRUST_FINGERPRINT_THRESHOLD = 100  # Empreinte validée → accès maximum

# Temps accordé pour poser le doigt après reconnaissance du visage (secondes)
FINGERPRINT_TIMEOUT = 15.0

# Temps accordé pour réussir le challenge sourire/clignement (secondes)
LIVENESS_CHALLENGE_TIMEOUT = 10.0

# Nombre de RECHECK consécutifs ratés avant de remettre un VIP en analyse
# Évite les faux intrus sur changement d'expression ou variation de lumière
RECHECK_FAILURE_TOLERANCE = 3

# ============================================
# ALERTES & NOTIFICATIONS
# ============================================
# Fenêtre de grâce après détection d'un intrus (secondes).
# Si un VIP est reconnu dans ce délai, l'alerte est annulée silencieusement.
# (Couvre le cas : VIP non encore identifié au moment de la détection)
ALERT_GRACE_PERIOD = 60

# Canaux de notification d'une intrusion confirmée (photo jointe).
# Les identifiants se saisissent depuis le dashboard (onglet Alertes) : ils sont
# stockés dans la base locale, hors dépôt Git, et jamais renvoyés en clair par l'API.
ALERT_TELEGRAM_ENABLED = False
TELEGRAM_BOT_TOKEN     = ""   # Jeton donné par @BotFather
TELEGRAM_CHAT_ID       = ""   # Identifiant de la conversation avec le bot

ALERT_EMAIL_ENABLED = False
SMTP_HOST      = "smtp.gmail.com"
SMTP_PORT      = 587          # 587 = STARTTLS, 465 = SSL
SMTP_USER      = ""
SMTP_PASSWORD  = ""           # Gmail : mot de passe d'application (validation en 2 étapes requise)
ALERT_EMAIL_TO = ""           # Un ou plusieurs destinataires, séparés par des virgules

# Délai minimal entre deux alertes envoyées (secondes) : évite l'avalanche quand
# le tracker attribue plusieurs identités à la même personne.
ALERT_COOLDOWN_SECONDS = 30

# ============================================
# IOT — Actionneurs ESP32
# ============================================
# False = mode mock/test : commandes simulées dans l'UI, rien n'est envoyé au réseau
# True  = signaux HTTP réels envoyés aux ESP32 sur le LAN
IOT_ENABLED = False

FINGERPRINT_ESP32_IP = "192.168.1.101"   # Module lecteur d'empreinte
DOOR_ESP32_IP        = "192.168.1.102"   # Relais gâche électrique
LIGHT_ESP32_IP       = "192.168.1.103"   # Module éclairage d'accueil

# ============================================
# RGPD — Rétention des données
# ============================================
# Les photos forensiques (snapshots/) sont purgées automatiquement après ce délai.
# La purge automatique ne supprime que les PHOTOS : les lignes du journal restent
# (historique et statistiques), seul le chemin de la photo est effacé.
RGPD_SNAPSHOT_RETENTION_HOURS = 72

# Dossier des photos forensiques d'intrus
SNAPSHOT_DIR = "database/snapshots"

# Fréquence de la purge automatique (minutes). Elle tourne aussi une fois au démarrage
# du serveur, ce qui rattrape les coupures de courant et les arrêts prolongés.
RGPD_PURGE_INTERVAL_MINUTES = 60

# ============================================
# PROFIL DE SÉCURITÉ
# ============================================
# Nom du template actuellement actif (pour référence et affichage dashboard)
# Valeurs possibles : "PORTAIL", "DOMICILE", "BUREAU", "HAUTE_SECURITE"
# Ce nom est mis à jour automatiquement par POST /config/apply_template
SECURITY_PROFILE_NAME = "DOMICILE"
