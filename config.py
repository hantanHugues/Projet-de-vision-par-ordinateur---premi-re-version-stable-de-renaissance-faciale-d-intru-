"""
Configuration centralisée du système de surveillance IA.

Ce fichier contient tous les paramètres du système.
Chaque phase du projet ajoutera ses propres paramètres ici.
Modifier ce fichier plutôt que de hardcoder des valeurs dans le code.

Phase 0 : Configuration vidéo de base.
"""

# ============================================
# SOURCE VIDÉO
# ============================================
# Types supportés : "webcam", "esp32", "file", "rtsp"
VIDEO_SOURCE_TYPE = "webcam"

# --- Webcam ---
# Index de la webcam (0 = webcam par défaut du système)
WEBCAM_INDEX = 0

# --- ESP32-CAM (Phase 7) ---
ESP32_URL = "http://192.168.1.100:81/stream"

# --- Fichier vidéo ---
VIDEO_FILE_PATH = ""

# --- RTSP ---
RTSP_URL = ""

# ============================================
# PARAMÈTRES D'AFFICHAGE
# ============================================
# Résolution cible pour le traitement (largeur x hauteur)
PROCESSING_WIDTH = 640
PROCESSING_HEIGHT = 480

# Nom de la fenêtre d'affichage
WINDOW_NAME = "SurveilleIA - Hub de Decision"

# ============================================
# LOGGING & DOCUMENTATION (Phase 2.5)
# ============================================
# Niveau de log
LOG_LEVEL = "INFO"
# Nombre de lignes visibles sur la fenêtre vidéo OpenCV
VISUAL_LOG_LINES = 8

# ============================================
# IA - DÉTECTION (Phase 2)
# ============================================
# Modèle YOLOv8 (Laissera ultralytics le télécharger si absent)
YOLO_MODEL_PATH = "yolov8n.pt"

# Seuil de confiance minimum pour garder une détection
YOLO_CONFIDENCE_THRESHOLD = 0.5

# Ne détecter QUE la classe 0 (Personnes)
DETECT_ONLY_PERSONS = True

# ============================================
# IA - POSTURE (Phase 3)
# ============================================
# Confiance minimale pour que MediaPipe s'accroche initialement au premier humain trouvé
POSE_MIN_DETECTION_CONFIDENCE = 0.5
# Confiance minimale pour tracker le squelette (limite la perte de la cible)
POSE_MIN_TRACKING_CONFIDENCE = 0.5
