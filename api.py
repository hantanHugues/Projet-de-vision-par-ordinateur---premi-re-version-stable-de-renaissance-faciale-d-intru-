import time
import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

from core.logger import VisualLogger
from core.yolo_detector import YoloDetector
from core.pose_analyzer import PoseAnalyzer
from core.centroid_tracker import CentroidTracker
from core.face_recognizer import FaceRecognizer

app = FastAPI(title="IA Video Surveillance API", version="6.0")

# --- INITIALISATION GLOABLE DE L'IA ---
logger = VisualLogger()
logger.info("Démarrage du Serveur IA (FastAPI)...")

yolo = YoloDetector(logger=logger)
pose_analyzer = PoseAnalyzer(logger=logger)
tracker = CentroidTracker()
face_recognizer = FaceRecognizer(logger=logger)

@app.post("/analyze_frame")
async def analyze_frame(file: UploadFile = File(...)):
    """
    Reçoit une image du client, la traite avec l'IA et renvoie les boîtes et identités.
    """
    start_time = time.time()
    
    # 1. Décoder l'image reçue du réseau
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # 2. IA - DÉTECTION DE PERSONNES (YOLOv8)
    detections = yolo.detect_humans(frame)
    # yolo.detect_humans retourne {"box": [x1, y1, x2, y2], "confidence": conf}
    rects = []
    for d in detections:
        x1, y1, x2, y2 = d["box"]
        # Le tracker attend [x1, y1, x2, y2]
        rects.append([x1, y1, x2, y2])
    
    # 3. IA - SUIVI (TRACKING)
    objects, bboxes = tracker.update(rects)
    active_ids = list(objects.keys())
    
    # Nettoyage si quelqu'un fuit l'écran
    face_recognizer.clear_lost_ids(active_ids)
    
    results = []
    
    # 4. ANALYSE INDIVIDUELLE (Pose & Visage)
    for object_id in objects.keys():
        centroid = objects[object_id]
        bbox_xyxy = bboxes[object_id]
        x1, y1, x2, y2 = bbox_xyxy
        
        # Squelette (MediaPipe) - Désactivé localement car l'API est conçue pour être très rapide
        # Vous pouvez appeler pose_analyzer.analyze_and_draw(frame) si vous l'adaptez pour les API
        pose_data = "Non Analysé (Performance API)"
        
        # Identité et Accès (Facenet512)
        identity = face_recognizer.identify(frame, bbox_xyxy, object_id)
        
        results.append({
            "object_id": object_id,
            "bbox": [int(x1), int(y1), int(x2-x1), int(y2-y1)], # Retourne en x,y,w,h pour le client
            "centroid": [int(centroid[0]), int(centroid[1])],
            "identity": identity,
            "pose": pose_data
        })
        
    process_time = time.time() - start_time
    
    return JSONResponse({
        "success": True,
        "process_time_ms": int(process_time * 1000),
        "detections": results
    })
