"""
YOLOv8 Detector — Moteur de détection d'objets.

Phase 2 : Utilise ultralytics/YOLOv8n pour détecter les humains.
Conçu pour être optimisé et utilisé comme composant dans le Hub de Décision.
"""

import cv2
import config
from ultralytics import YOLO


class YoloDetector:
    """Classe enveloppant YOLOv8 pour la détection d'objets spécifiques (Humains)."""

    def __init__(self, logger):
        self.logger = logger
        self.logger.info("Initialisation de l'IA (YOLO)...")
        # Le paramètre verbose=False évite de spammer la console à chaque itération
        self._model = YOLO(config.YOLO_MODEL_PATH)
        self.logger.success(f"Modèle {config.YOLO_MODEL_PATH} prêt à l'emploi.")
        
        # État précédent (pour ne pas spammer les logs)
        self._last_human_count = 0

    def detect_humans(self, frame):
        """
        Analyse une image pour y trouver des humains.
        
        Args:
            frame: Image capturée retournée par OpenCV (Numpy array).
            
        Returns:
            Une liste de détections, format : [{'box': [x1, y1, x2, y2], 'confidence': 0.95}, ...]
        """
        # Limiter à la classe 0 (Personne) si demandé dans la config
        classes = [0] if config.DETECT_ONLY_PERSONS else None
        
        # Inférence avec stream=False pour traiter une image fixe à la fois.
        # conf permet d'omettre les "bruits" où l'IA n'est pas certaine.
        # iou=0.4 force YOLO à fusionner les boîtes qui se superposent (Anti double-détection)
        results = self._model(
            frame, 
            conf=config.YOLO_CONFIDENCE_THRESHOLD, 
            classes=classes, 
            verbose=False,
            iou=0.35 
        )

        detections = []
        # Parcourir les boîtes englobantes (boxes) du résultat
        for result in results:
            boxes = result.boxes
            for box in boxes:
                # x1, y1 = coin supérieur gauche | x2, y2 = coin inférieur droit
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                conf = float(box.conf[0])
                
                detections.append({
                    "box": [x1, y1, x2, y2],
                    "confidence": conf
                })
                
        # --- Logique anti-spam ---
        current_count = len(detections)
        # La discussion "YOLO <-> MediaPipe" est gérée par main.py
        # On garde ici uniquement la fin d'alerte.
        if current_count == 0 and self._last_human_count > 0:
            self.logger.info("YOLO: Fin de détection, zone dégagée.")
            
        self._last_human_count = current_count
                
        return detections

    def draw_boxes(self, frame, detections):
        """
        Superpose les boîtes de détection sur l'image d'origine.
        
        Args:
            frame: L'image source.
            detections: Liste retournée par detect_humans().
            
        Returns:
            L'image modifiée avec les annotations visuelles.
        """
        annotated_frame = frame.copy()
        
        for det in detections:
            x1, y1, x2, y2 = det["box"]
            conf = det["confidence"]
            
            # Dessin de la boîte (en vert)
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            
            # Ajout du texte de probabilité au-dessus de la boîte
            label = f"Humain: {conf:.2f}"
            cv2.putText(
                annotated_frame,
                label,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2
            )
            
        return annotated_frame
