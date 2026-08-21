"""
main.py — Point d'entrée local du Hub de Décision (mode standalone).

Pipeline complet en local : YOLO + CentroidTracker (Color Re-ID) + FaceNet512.
Alternative à api.py + client_camera.py pour les tests sans réseau.

Usage :
    python main.py

Contrôles :
    q — Quitter le programme
"""

import sys
import time
import cv2
import config
from sources.webcam import WebcamSource
from core.yolo_detector import YoloDetector
from core.centroid_tracker import CentroidTracker
from core.face_recognizer import FaceRecognizer
from core.logger import VisualLogger


def create_video_source(logger=None):
    """
    Factory : crée la source vidéo selon la configuration.

    Args:
        logger: VisualLogger à injecter dans la source (optionnel).
    Returns:
        Une instance de VideoSource correspondant au type configuré.
    """
    source_type = config.VIDEO_SOURCE_TYPE

    if source_type == "webcam":
        return WebcamSource(camera_index=config.WEBCAM_INDEX, logger=logger)
    # --- Sources futures ---
    # elif source_type == "esp32":
    #     from sources.esp32 import ESP32Source
    #     return ESP32Source(url=config.ESP32_URL)
    # elif source_type == "file":
    #     from sources.file import FileSource
    #     return FileSource(path=config.VIDEO_FILE_PATH)
    # elif source_type == "rtsp":
    #     from sources.rtsp import RTSPSource
    #     return RTSPSource(url=config.RTSP_URL)
    else:
        print(f"[ERREUR] Type de source inconnu : '{source_type}'")
        print(f"  Types supportés : webcam")
        sys.exit(1)


def main():
    """Boucle principale du système."""
    logger = VisualLogger()
    
    logger.info("=" * 40)
    logger.info("SurveilleIA — Hub de Décision Démarré")
    logger.info("=" * 40)

    # 1. Créer et ouvrir la source vidéo
    source = create_video_source(logger)
    logger.info(f"Source initialisée : {source.source_name}")

    if not source.open():
        logger.error("Erreur Fatale : Impossible d'ouvrir la source vidéo.")
        sys.exit(1)

    # 1.5 Initialiser les cerveaux IA
    detector = YoloDetector(logger)
    tracker = CentroidTracker(max_disappeared=60)
    face_rec = FaceRecognizer(logger)
    
    logger.info("Tracker (CentroidTracker) initialisé (Phase 4).")
    logger.info("Reconnaissance Faciale + Cache initialisée (Phase 5).")

    logger.info(f"Affichage dans la fenêtre : '{config.WINDOW_NAME}'")
    logger.info("Pipeline IA complet. Prêt.")

    # 2. Compteur de FPS pour diagnostic
    frame_count = 0
    start_time = time.time()

    try:
        while True:
            # 2a. Lire une frame
            success, frame = source.read_frame()
            if not success:
                logger.warning("Frame perdue, tentative suivante...")
                continue

            # 2b. Redimensionner pour un traitement uniforme
            frame = cv2.resize(
                frame,
                (config.PROCESSING_WIDTH, config.PROCESSING_HEIGHT)
            )

            # 2c. Calculer et afficher les FPS
            frame_count += 1
            elapsed = time.time() - start_time
            if elapsed > 0:
                fps = frame_count / elapsed
                cv2.putText(
                    frame,
                    f"FPS: {fps:.1f}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2,
                )

            # 2d. Afficher le nom de la source
            cv2.putText(
                frame,
                f"Source: {source.source_name}",
                (10, config.PROCESSING_HEIGHT - 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (200, 200, 200),
                1,
            )

            # 2e. Phase 2 — Détection d'humains avec YOLOv8
            start_infer = time.time()
            detections = detector.detect_humans(frame)
            yolo_ms = (time.time() - start_infer) * 1000
            
            # Annoter l'image avec les bounding boxes
            frame = detector.draw_boxes(frame, detections)
            
            # --- PHASE 4: SUIVI D'OBJETS (TRACKING) ---
            rects = [det["box"] for det in detections]
            # frame passé pour activer la Color Re-ID HSV (signature vestimentaire)
            objects, bboxes = tracker.update(rects, frame)

            # --- PHASE 5: RECONNAISSANCE FACIALE AVEC CACHE ---
            face_rec.clear_lost_ids(list(objects.keys()))

            for (object_id, centroid) in objects.items():
                # On recupère la vraie bounding box enregistrée pour cet ID
                bbox = bboxes[object_id]
                
                # Identification / Lecture du Cache
                nom = face_rec.identify(frame, bbox, object_id)

                # Affichage de l'ID Tracker et du Nom sur la vidéo
                text = f"ID {object_id}: {nom}"
                cv2.putText(
                    frame, text, (bbox[0], bbox[1] - 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2
                )
                # Point central du tracking

            # Phase 3 DÉSACTIVÉE: La 3D était trop instable sur du matériel "Edge"
            pose_ms = 0.0
            
            # Afficher les temps de calcul IA
            total_ms = yolo_ms + pose_ms
            cv2.putText(
                frame,
                f"YOLO: {yolo_ms:.0f}ms | Pose: {pose_ms:.0f}ms | Total: {total_ms:.0f}ms",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 200, 255),
                2,
            )

            # 2f. Ajout du Visual Logger en bas de la vidéo
            frame = logger.overlay_logs(frame)

            # 3. Afficher la frame
            cv2.imshow(config.WINDOW_NAME, frame)

            # 4. Contrôles clavier
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                logger.info("Arrêt demandé par l'utilisateur (touche 'q').")
                break

    except KeyboardInterrupt:
        logger.warning("Arrêt forcé (Ctrl+C).")

    finally:
        # 5. Nettoyage propre
        source.release()
        cv2.destroyAllWindows()
        elapsed = time.time() - start_time
        
        logger.success(f"Système arrêté proprement.")
        logger.info(f"Rapport : {frame_count} frames analysées en {elapsed:.1f}s")
        if elapsed > 0:
            logger.info(f"FPS Global : {frame_count / elapsed:.1f}")


if __name__ == "__main__":
    main()
