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
                
        # --- PATCH ANTI-CLONAGE (Exclusivité Spatiale Absolue) ---
        # Parfois, YOLO sort 2 boîtes sur la même personne : une pour la tête, une pour le corps entier.
        # Le paramètre iou=0.35 ne suffit pas à les fusionner si la tête est trop petite (Intersection sur Union faible).
        # On va supprimer manuellement les boîtes qui sont "incluses" dans une autre image plus grande.
        filtered_detections = []
        for i, d1 in enumerate(detections):
            is_contained = False
            box1 = d1["box"]
            area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
            
            for j, d2 in enumerate(detections):
                if i == j: continue
                box2 = d2["box"]
                area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
                
                # Calcul de l'aire d'intersection
                x_left = max(box1[0], box2[0])
                y_top = max(box1[1], box2[1])
                x_right = min(box1[2], box2[2])
                y_bottom = min(box1[3], box2[3])
                
                if x_right > x_left and y_bottom > y_top:
                    intersection = (x_right - x_left) * (y_bottom - y_top)
                    # Si plus de 50% de la boîte 1 est dans la boîte 2 ET que la boîte 2 est plus grande
                    if intersection / area1 > 0.5 and area2 > area1:
                        is_contained = True
                        break
                        
            if not is_contained:
                filtered_detections.append(d1)
                
        detections = filtered_detections

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
