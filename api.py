import time
import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, Form
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
    
    # 3. IA - SUIVI (TRACKING) + RE-IDENTIFICATION CORPORELLE
    objects, bboxes = tracker.update(rects, frame)
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
        pose_data = "Non Analysé (Performance API)"
        
        # Visuel : Trouver la tête en temps réel (pour l'UI du client UNIQUEMENT)
        # Indépendant de la sécurité, c'est juste pour rassurer l'utilisateur en dessinant un encadré !
        face_box_ui = None
        crop = frame[max(0, int(y1)):min(frame.shape[0], int(y2)), max(0, int(x1)):min(frame.shape[1], int(x2))]
        if crop.size > 0:
            gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            # Détection ultra-légère (HaarCascade existant du recognizer)
            faces = face_recognizer.face_cascade.detectMultiScale(gray_crop, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
            if len(faces) > 0:
                fx, fy, fw, fh = faces[0]
                # Re-conversion en coordonnées globales
                face_box_ui = [int(x1) + int(fx), int(y1) + int(fy), int(fw), int(fh)]

        # Identité et Accès (Facenet512)
        identity = face_recognizer.identify(frame, bbox_xyxy, object_id)
        
        results.append({
            "object_id": object_id,
            "bbox": [int(x1), int(y1), int(x2-x1), int(y2-y1)], # Retourne en x,y,w,h pour le client
            "face_box": face_box_ui,
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

# ===============================================================
# ÉTAPE 5 : ROUTE D'ENRÔLEMENT (INSCRIPTION OFFICIELLE VIP)
# ===============================================================
@app.post("/enroll")
async def enroll_vip(name: str = Form(...), file: UploadFile = File(...)):
    """
    Méthode d'inscription officielle pour la base de données SQLite.
    À terme, appelable depuis une belle interface React/Vue. 
    Pour l'instant, testable via /docs.
    """
    start_time = time.time()
    
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if frame is None:
        logger.error(f"[ENROLLMENT] L'image envoyée est corrompue.")
        return JSONResponse(status_code=400, content={"success": False, "message": "Image corrompue."})
        
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Face Gate: on s'assure que la photo est une belle photo d'identité
    # minSize grand (60,60) pour s'assurer d'une bonne définition
    faces = face_recognizer.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    
    if len(faces) == 0:
        return JSONResponse(status_code=400, content={"success": False, "message": "Aucun visage net trouvé de face sur la photo. L'inscription nécessite une photo claire."})
        
    if len(faces) > 1:
        return JSONResponse(status_code=400, content={"success": False, "message": "Plusieurs visages détectés. Veuillez envoyer une photo avec une seule personne."})
        
    # Recadrage strict de la zone du visage
    (x, y, w, h) = faces[0]
    face_roi = frame[y:y+h, x:x+w]
    
    # Extraction de l'ADN biométrique par Facenet512 (La magie de l'IA)
    signature = face_recognizer._extract_face_signature(face_roi)
    
    if signature is None:
        return JSONResponse(status_code=400, content={"success": False, "message": "L'IA a échoué à extraire le vecteur mathématique. Éclairage insuffisant ?"})
        
    # Formatage du nom et Mémorisation LÉGITIME dans SQLite
    vip_name = name.strip().capitalize()
    face_recognizer.db.add_embedding(vip_name, signature, role="VIP")
    
    # Trace de monitoring
    process_time = time.time() - start_time
    logger.success(f"[Étape 5] NOUVEAU VIP INSCRIT OFFICIELLEMENT: {vip_name} en {process_time:.2f}s !")
    
    return {
        "success": True, 
        "message": f"Le profil VIP '{vip_name}' a été enregistré avec succès.",
        "process_time_ms": int(process_time * 1000)
    }
