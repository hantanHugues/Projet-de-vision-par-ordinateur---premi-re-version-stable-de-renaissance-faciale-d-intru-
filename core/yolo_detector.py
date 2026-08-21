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
        # imgsz=320 force le downscaling INTÉGRÉ dans YOLO pour économiser drastiquement le bus CPU (Optimisation Edge)
        results = self._model(
            frame,
            conf=config.YOLO_CONFIDENCE_THRESHOLD,
            classes=classes,
            verbose=False,
            imgsz=config.YOLO_IMAGE_SIZE,
            iou=config.YOLO_IOU
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
                
        # --- NMS MANUEL (Non-Maximum Suppression) ---
        # YOLO peut produire plusieurs boîtes pour la même personne :
        #   - tête + corps entier  → cas "contenement"
        #   - haut du corps + bas du corps → cas "adjacents" (non géré par un filtre de containment simple)
        # Solution : NMS standard par IoU. On garde la boîte la plus confiante et on supprime
        # toutes celles qui chevauchent à plus de POST_NMS_IOU_THRESHOLD.
        detections = self._nms(detections, iou_threshold=0.30)

        # --- Logique anti-spam ---
        current_count = len(detections)
        # La discussion "YOLO <-> MediaPipe" est gérée par main.py
        # On garde ici uniquement la fin d'alerte.
        if current_count == 0 and self._last_human_count > 0:
            self.logger.info("YOLO: Fin de détection, zone dégagée.")
            
        self._last_human_count = current_count
                
        return detections

    def _iou(self, box1, box2):
        """Calcule l'Intersection sur Union entre deux boîtes [x1,y1,x2,y2]."""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        if inter == 0:
            return 0.0
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        return inter / (area1 + area2 - inter)

    def _nms(self, detections, iou_threshold=0.30):
        """
        NMS manuel — trie par confiance (desc), garde la meilleure boîte,
        supprime toutes celles qui chevauchent à plus de iou_threshold.
        Couvre les cas "boîte dans boîte" ET "boîtes adjacentes" (angle mort du filtre containment).
        """
        if len(detections) <= 1:
            return detections
        detections = sorted(detections, key=lambda d: d["confidence"], reverse=True)
        kept = []
        while detections:
            best = detections.pop(0)
            kept.append(best)
            detections = [
                d for d in detections
                if self._iou(best["box"], d["box"]) < iou_threshold
            ]
        return kept

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
