import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
import config
import os

class PoseAnalyzer:
    def __init__(self, logger):
        self.logger = logger
        self.logger.info('Initialisation de MediaPipe Pose Tasks...')
        try:
            model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'models', 'pose_landmarker_lite.task'))
            base_options = mp_python.BaseOptions(model_asset_path=model_path)
            options = vision.PoseLandmarkerOptions(
                base_options=base_options,
                running_mode=vision.RunningMode.IMAGE,
                min_pose_detection_confidence=getattr(config, 'POSE_MIN_DETECTION_CONFIDENCE', 0.5),
                min_pose_presence_confidence=getattr(config, 'POSE_MIN_TRACKING_CONFIDENCE', 0.5),
                min_tracking_confidence=getattr(config, 'POSE_MIN_TRACKING_CONFIDENCE', 0.5)
            )
            self._detector = vision.PoseLandmarker.create_from_options(options)
            self.mp_drawing = vision.drawing_utils
            self.mp_drawing_styles = vision.drawing_styles
            self.POSE_CONNECTIONS = vision.PoseLandmarksConnections.POSE_LANDMARKS
            self.logger.success('Modele PoseLandmarker (MediaPipe) pret a l emploi.')
            self.is_ready = True
        except Exception as e:
            self.logger.error(f'Erreur MediaPipe: {e}')
            self.is_ready = False

    def analyze_and_draw(self, frame):
        if not getattr(self, 'is_ready', False):
            return frame, False, False, "Erreur Init"
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        try:
            detection_result = self._detector.detect(mp_image)
            annotated_frame = frame.copy()
            has_skeleton = False
            is_3d_real = False
            msg = "Aucun squelette détecté"
            
            if detection_result.pose_landmarks and len(detection_result.pose_landmarks) > 0:
                has_skeleton = True
                
                # --- LOGIQUE ANTI-SPOOFING ASSOUPLIE ---
                for pose_landmarks in detection_result.pose_landmarks:
                    # On extrait toutes les valeurs Z des articulations (même moyennement visibles)
                    z_values = [lm.z for lm in pose_landmarks if getattr(lm, 'visibility', 0) > 0.3]
                    
                    if len(z_values) >= 3:
                        z_variance = (max(z_values) - min(z_values)) * 100 
                        
                        if z_variance > 1.5:  # Seuil baissé pour éviter de rejeter à tort
                            is_3d_real = True
                            msg = f"Volume 3D validé (Var Z: {z_variance:.1f})"
                        else:
                            is_3d_real = False
                            msg = f"FAUSSE ALERTE Photo 2D (Var Z: {z_variance:.1f} < 1.5)"
                    else:
                        # Si on voit trop peu de points, on ne peut pas juger. On laisse passer avec un doute.
                        is_3d_real = True 
                        msg = "Partiel: 3D assumée par défaut"
                
            return annotated_frame, has_skeleton, is_3d_real, msg
        except Exception as e:
            self.logger.error(f'Erreur detect: {e}')
            return frame, False, False, str(e)
