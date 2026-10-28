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

# Temps maximum pour identifier un inconnu avant de le classer Intrus (secondes)
FACE_ANALYSIS_TIME_LIMIT = 1.0

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
# Les photos forensiques (snapshots/) sont purgées automatiquement après ce délai
RGPD_SNAPSHOT_RETENTION_HOURS = 72

# ============================================
# PROFIL DE SÉCURITÉ
# ============================================
# Nom du template actuellement actif (pour référence et affichage dashboard)
# Valeurs possibles : "PORTAIL", "DOMICILE", "BUREAU", "HAUTE_SECURITE"
# Ce nom est mis à jour automatiquement par POST /config/apply_template
SECURITY_PROFILE_NAME = "DOMICILE"
