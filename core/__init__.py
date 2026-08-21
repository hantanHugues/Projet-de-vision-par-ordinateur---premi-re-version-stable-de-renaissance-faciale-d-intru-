"""
Module core — Moteurs d'Intelligence Artificielle (BioGate v7).

Pipeline actif :
- camera_manager.py  : Capture multi-sources (USB/MJPEG/RTSP), threads par caméra
- yolo_detector.py   : Détection humains (YOLOv8)
- centroid_tracker.py: Suivi par centroïde (un tracker par caméra)
- face_recognizer.py : Reconnaissance faciale FaceNet512 + embeddings SQLite
- liveness_detector.py: Anti-spoofing (clignement + sourire MediaPipe)
- trust_score.py     : Score de confiance MFA + machine à états d'accès
- iot_controller.py  : Contrôle porte / empreinte / éclairage (simulation)
"""
