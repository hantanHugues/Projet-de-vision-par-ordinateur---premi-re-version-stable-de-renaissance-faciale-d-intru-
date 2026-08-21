import asyncio
import queue
import time
import cv2
import numpy as np
import os
import re
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

if not os.path.exists("database/snapshots"):
    os.makedirs("database/snapshots")
from fastapi import FastAPI, File, UploadFile, Form, Query, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.logger import VisualLogger
from core.yolo_detector import YoloDetector
from core.centroid_tracker import CentroidTracker
from core.face_recognizer import FaceRecognizer
from core.trust_score import TrustScoreManager, STATE_LIVENESS_PENDING
from core.iot_controller import IoTController
from core.liveness_detector import LivenessDetector, LIVENESS_SUCCESS, LIVENESS_TIMEOUT, LIVENESS_FAILED
from core.camera_manager import CameraManager
from database.db_manager import DatabaseManager


# ── Lifespan (FastAPI ≥ 0.93 — remplace @app.on_event) ───────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ─────────────────────────────────────────────────────
    # Worker pipeline dans son propre thread daemon
    _worker = threading.Thread(
        target=_pipeline_worker, daemon=True, name="pipeline-worker"
    )
    _worker.start()

    # Charger les caméras persistées
    rows = face_recognizer.db.get_cameras(active_only=True)
    for row in rows:
        cam_mgr.add(row["cam_id"], {
            "name":      row["name"],
            "type":      row["type"],
            "url":       row["url"],
            "usb_index": row["usb_index"],
            "zone":      row["zone"],
        })
    logger.info(
        f"[STARTUP] Worker pipeline démarré · {len(rows)} caméra(s) chargée(s)."
    )

    yield  # ← application tourne ici

    # ── SHUTDOWN ─────────────────────────────────────────────────────
    cam_mgr.stop_all()
    logger.info("[SHUTDOWN] Sources vidéo arrêtées proprement.")


app = FastAPI(title="BioGate API", version="7.0", lifespan=lifespan)

# CORS — restreint aux origines réelles du dashboard Electron.
# "null" couvre l'origin envoyé par Electron en production (file://).
# http://localhost:517x couvre electron-vite en mode dev.
# allow_methods limité aux verbes effectivement utilisés par l'API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "null",          # Electron file:// → Origin: null
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# --- INITIALISATION GLOBALE ---
logger = VisualLogger()
logger.info("Démarrage BioGate v7...")

# Callback déclenché quand un intrus dépasse la fenêtre de grâce
def _on_intruder_confirmed(object_id, snapshot_path):
    name = face_recognizer.tracking_states.get(object_id, {}).get("final_name", "Intrus_???")
    logger.error(f"[ALERTE CONFIRMÉE] Intrus ID={object_id} ({name}) — alerte déclenchée.")
    face_recognizer.db.log_event(
        name, 0.0,
        event_type=DatabaseManager.EVENT_INTRUDER_CONFIRMED,
        snapshot_path=snapshot_path,
    )
    iot.set_light_alert()

trust_mgr = TrustScoreManager(on_intruder_confirmed=_on_intruder_confirmed)
iot        = IoTController(logger=logger)

yolo               = YoloDetector(logger=logger)
tracker            = CentroidTracker()
known_snapshot_ids = set()
face_recognizer    = FaceRecognizer(logger=logger, trust_mgr=trust_mgr)

# Set des object_ids dont la porte a déjà été ouverte (évite de rouvrir à chaque frame)
_door_triggered_ids: set = set()

# Sessions liveness actives — {object_id: LivenessDetector}
_liveness_sessions: dict = {}

# Dernier frame reçu — servi en MJPEG via GET /stream (compat. rétrograde)
_latest_frame_jpg: Optional[bytes] = None

# ── Couleurs BGR par état Trust ───────────────────────────────────────
_STATE_BGR = {
    "GRANTED":             ( 94, 197,  34),
    "DENIED":              ( 68,  68, 239),
    "FINGERPRINT_PENDING": ( 35, 166, 245),
    "LIVENESS_PENDING":    ( 35, 166, 245),
    "INTRUDER_CONFIRMED":  ( 59,  59, 255),
    "ANALYZING":           (250, 165,  96),
}

# ── Pipeline IA — architecture correcte ──────────────────────────────
#
#  Problèmes corrigés (audit F1, F5, F7) :
#
#  F7 CRITIQUE : un CentroidTracker PAR caméra (pull mode).
#     Le tracker global `tracker` reste réservé au push mode (analyze_frame).
#     Sans ça, Camera A et Camera B partagent le même state de tracking →
#     les IDs se contaminent.
#
#  F1 : queue.Queue(maxsize=4) remplace le Lock global.
#     Le thread de capture fait put_nowait() — non bloquant, frame dropped
#     si le pipeline est occupé. Backpressure naturelle, pas de gel.
#
#  F5 : time.monotonic() pour les comparaisons de durée.
#     Garanti croissant (insensible aux ajustements NTP).

_inference_lock  = threading.Lock()         # protège yolo + face_recognizer
_pipeline_queue: "queue.Queue[tuple]" = queue.Queue(maxsize=4)
_cam_trackers:   dict = {}                  # {cam_id: CentroidTracker}
_cam_door_ids:   dict = {}                  # {cam_id: set[oid]}


def _get_cam_tracker(cam_id: str) -> CentroidTracker:
    """Retourne le tracker dédié à cette caméra, le crée si nécessaire."""
    if cam_id not in _cam_trackers:
        _cam_trackers[cam_id]  = CentroidTracker()
        _cam_door_ids[cam_id]  = set()
    return _cam_trackers[cam_id]


def _run_pipeline_and_annotate(frame_bgr: np.ndarray, cam_id: str = "") -> np.ndarray:
    """
    YOLO → tracker dédié par cam_id → FaceNet512 → TrustScore → annotation.

    _inference_lock protège uniquement les appels non thread-safe (yolo, face_recognizer).
    Le dessin est fait HORS du lock sur une copie locale → contention minimale.
    """
    cam_tracker  = _get_cam_tracker(cam_id)
    cam_door_set = _cam_door_ids.setdefault(cam_id, set())
    annotations  = []

    try:
        with _inference_lock:
            # 1 — YOLO
            detections = yolo.detect_humans(frame_bgr)
            rects      = [d["box"] for d in detections]

            # 2 — Tracker dédié à cette caméra (F7 corrigé)
            objects, bboxes = cam_tracker.update(rects, frame_bgr)
            active_ids      = list(objects.keys())
            cam_door_set.intersection_update(active_ids)
            face_recognizer.clear_lost_ids(active_ids)

            # 3 — Identification + Trust (toujours sous lock car face_recognizer non thread-safe)
            for oid in objects:
                bbox_xyxy = bboxes[oid]
                identity  = face_recognizer.identify(frame_bgr, bbox_xyxy, oid)
                ts_obj    = trust_mgr.get(oid)

                if ts_obj:
                    ts_obj.check_mfa_timeout()
                    ts_state = ts_obj.get_state()
                    if ts_obj.is_access_granted() and oid not in cam_door_set:
                        cam_door_set.add(oid)
                        iot.open_door()
                        iot.set_light_welcome()
                        logger.info(f"[ACCÈS] Porte ouverte · {ts_obj.vip_name} · cam={cam_id}")
                else:
                    ts_state = None

                x1, y1, x2, y2 = [int(v) for v in bbox_xyxy]
                state = (ts_state or {}).get("state", "ANALYZING")
                score = (ts_state or {}).get("score", 0) or 0
                name  = (ts_state or {}).get("vip_name") or identity.get("name", "?")
                annotations.append((oid, x1, y1, x2, y2, name, score, state))

    except Exception as exc:
        logger.warning(f"[PIPELINE] {cam_id}: {exc}")

    # ── Dessin hors du lock (cv2 local sur une copie) ─────────────────
    out = frame_bgr.copy()
    for oid, x1, y1, x2, y2, name, score, state in annotations:
        color = _STATE_BGR.get(state, (250, 165, 96))
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 1)
        sz = 14
        for px, py, dx, dy in [(x1,y1,1,1),(x2,y1,-1,1),(x1,y2,1,-1),(x2,y2,-1,-1)]:
            cv2.line(out, (px, py), (px + dx*sz, py), color, 2)
            cv2.line(out, (px, py), (px, py + dy*sz), color, 2)
        label = f"{name}  {score:.0f}%" if score > 0 else name
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
        cv2.rectangle(out, (x1, y1 - th - 10), (x1 + tw + 8, y1), color, -1)
        cv2.putText(out, label, (x1+4, y1-5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (10, 10, 10), 1, cv2.LINE_AA)
        cv2.putText(out, f"ID#{oid}", (x1+4, y2-6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)

    # Overlay teal
    ts_str = datetime.now().strftime("%H:%M:%S")
    h, w   = out.shape[:2]
    cv2.putText(out, ts_str, (w-95, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 200, 150), 1, cv2.LINE_AA)
    if cam_id:
        src = cam_mgr.get(cam_id) if "cam_mgr" in dir() else None
        cv2.putText(out, src.name if src else cam_id, (8, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 200, 150), 1, cv2.LINE_AA)
    return out


def _pipeline_worker() -> None:
    """
    Thread daemon unique qui consomme la queue frame par frame.
    Un seul consommateur → pas de concurrence sur yolo/face_recognizer.
    """
    while True:
        try:
            cam_id, frame = _pipeline_queue.get(timeout=1.0)
            annotated = _run_pipeline_and_annotate(frame, cam_id)
            cam_mgr.store_annotated(cam_id, annotated)
        except queue.Empty:
            continue
        except Exception as exc:
            logger.warning(f"[PIPELINE WORKER] {exc}")


def _cam_on_frame(cam_id: str, frame_bgr: np.ndarray) -> None:
    """
    Callback CameraManager → pousse le frame dans la queue (non-bloquant).
    Si la queue est pleine, le frame est silencieusement abandonné :
    c'est le mécanisme de backpressure naturel (F1 corrigé).
    frame.copy() AVANT put_nowait pour éviter que le thread caméra écrase
    le buffer pendant le traitement.
    """
    try:
        _pipeline_queue.put_nowait((cam_id, frame_bgr.copy()))
    except queue.Full:
        pass


cam_mgr = CameraManager(on_frame=_cam_on_frame)

# ── Auth dashboard (token opaque, 30 jours) ──────────────────────────
_dashboard_token:   Optional[str] = None
_pair_pin:          Optional[str] = None
_pair_pin_expires:  float = 0.0
_pair_pin_attempts: int   = 0
_PAIR_TTL      = 300   # 5 minutes
_PAIR_MAX_TRIES = 5

def _check_token(authorization: Optional[str]):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token manquant")
    if authorization.split(" ", 1)[1] != _dashboard_token:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")

@app.post("/analyze_frame")
async def analyze_frame(
    file: UploadFile = File(...),
    liveness_blink: float = Form(0.0),
    liveness_smile: float = Form(0.0),
):
    """
    Reçoit une image du client, la traite avec l'IA et renvoie les boîtes et identités.
    """
    global _latest_frame_jpg
    start_time = time.time()

    # 1. Décoder l'image reçue du réseau
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Stocker le frame pour le flux MJPEG dashboard
    _latest_frame_jpg = contents

    if frame is None:
        return JSONResponse(status_code=400, content={"success": False, "message": "Image corrompue ou vide reçue."})

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
    known_snapshot_ids.intersection_update(active_ids)
    _door_triggered_ids.intersection_update(active_ids)
    for lost_id in [oid for oid in _liveness_sessions if oid not in active_ids]:
        _liveness_sessions.pop(lost_id).release()
    
    results = []
    
    # 4. ANALYSE INDIVIDUELLE (Pose & Visage)
    for object_id in objects.keys():
        centroid = objects[object_id]
        bbox_xyxy = bboxes[object_id]

        # --- FORENSIC SNAPSHOT (RGPD COMPLIANT) ---
        if object_id not in known_snapshot_ids:
            known_snapshot_ids.add(object_id)
            sx1, sy1, sx2, sy2 = [int(v) for v in bbox_xyxy]
            corp_crop = frame[max(0, sy1):min(frame.shape[0], sy2), max(0, sx1):min(frame.shape[1], sx2)]
            if corp_crop.size > 0:
                timestamp = datetime.now().strftime("%Y-%m-%d_%Hh%Mm%Ss")
                snap_path = f"database/snapshots/{timestamp}_TrackID_{object_id}.jpg"
                cv2.imwrite(snap_path, corp_crop)
                logger.info(f"[FORENSIC] Silhouette sauvegardee: {snap_path}")
        # ------------------------------------------

        x1, y1, x2, y2 = bbox_xyxy
        
        # Visuel : Trouver la tête en temps réel (pour l'UI du client UNIQUEMENT)
        # Indépendant de la sécurité, c'est juste pour rassurer l'utilisateur en dessinant un encadré !
        face_box_ui = None
        crop = frame[max(0, int(y1)):min(frame.shape[0], int(y2)), max(0, int(x1)):min(frame.shape[1], int(x2))]
        if crop.size > 0:
            gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            gray_crop = cv2.equalizeHist(gray_crop)  # Identique au FaceGate sécuritaire
            # Détection ultra-légère (HaarCascade existant du recognizer)
            faces = face_recognizer.face_cascade.detectMultiScale(gray_crop, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
            if len(faces) > 0:
                fx, fy, fw, fh = faces[0]
                # Re-conversion en coordonnées globales
                face_box_ui = [int(x1) + int(fx), int(y1) + int(fy), int(fw), int(fh)]

        # Identité et Accès (Facenet512)
        identity = face_recognizer.identify(frame, bbox_xyxy, object_id)

        # Trust Score de cet individu (None si pas encore créé)
        ts_state = None
        ts_obj = trust_mgr.get(object_id)
        if ts_obj:
            ts_state = ts_obj.get_state()
            current_state = ts_state.get("state", "")

            # ── Timeout FINGERPRINT_PENDING ──────────────────────────────
            if ts_obj.check_mfa_timeout():
                logger.warning(f"[MFA] Timeout dépassé pour ID={object_id} → DENIED")
                ts_state = ts_obj.get_state()
                current_state = ts_state.get("state", "")
            # ────────────────────────────────────────────────────────────

            # ── LIVENESS : analyse frame par frame ──────────────────────
            if current_state == STATE_LIVENESS_PENDING:
                if object_id not in _liveness_sessions:
                    _liveness_sessions[object_id] = LivenessDetector()
                    logger.info(f"[LIVENESS] Challenge démarré pour ID={object_id}")

                det = _liveness_sessions[object_id]
                # Si le client envoie des scores (MediaPipe local 30fps), on les utilise.
                # Sinon fallback sur l'analyse côté serveur (5fps).
                if liveness_blink > 0.0 or liveness_smile > 0.0:
                    liveness_result = det.check_values(liveness_blink, liveness_smile)
                else:
                    liveness_result = det.check(crop if crop.size > 0 else frame)

                if liveness_result == LIVENESS_SUCCESS:
                    ts_obj.liveness_success()
                    _liveness_sessions.pop(object_id).release()
                    face_recognizer.db.log_event(
                        ts_obj.vip_name or "VIP", 85.0,
                        event_type=DatabaseManager.EVENT_LIVENESS_SUCCESS, role="VIP"
                    )
                    logger.info(f"[LIVENESS] ✓ Challenge réussi pour {ts_obj.vip_name}")

                elif liveness_result in (LIVENESS_TIMEOUT, LIVENESS_FAILED):
                    ts_obj.liveness_failed()
                    _liveness_sessions.pop(object_id).release()
                    logger.warning(f"[LIVENESS] ✗ Timeout/échec pour ID={object_id}")

                # Enrichir ts_state avec la progression du challenge
                ts_state = ts_obj.get_state()
                ts_state["liveness_progress"] = det.get_progress() \
                    if object_id in _liveness_sessions else None
            # ────────────────────────────────────────────────────────────

            # Ouvrir la porte une seule fois quand GRANTED
            if ts_obj.is_access_granted() and object_id not in _door_triggered_ids:
                _door_triggered_ids.add(object_id)
                iot.open_door()
                iot.set_light_welcome()
                logger.info(f"[ACCÈS] Porte ouverte pour {ts_obj.vip_name} ({ts_state.get('score', 0):.1f}%)")

        results.append({
            "object_id": object_id,
            "bbox":      [int(x1), int(y1), int(x2-x1), int(y2-y1)],
            "face_box":  face_box_ui,
            "centroid":  [int(centroid[0]), int(centroid[1])],
            "identity":  identity,
            "trust":     ts_state,
        })

    process_time = time.time() - start_time

    return JSONResponse({
        "success":        True,
        "process_time_ms": int(process_time * 1000),
        "detections":     results,
        "iot":            iot.get_status(),
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

    # Invalider et recharger le cache RAM pour que la prochaine analyse voit ce nouveau VIP
    face_recognizer.reload_cache()

    # Trace de monitoring
    process_time = time.time() - start_time
    logger.success(f"[Étape 5] NOUVEAU VIP INSCRIT OFFICIELLEMENT: {vip_name} en {process_time:.2f}s !")
    
    return {
        "success": True,
        "message": f"Le profil VIP '{vip_name}' a été enregistré avec succès.",
        "process_time_ms": int(process_time * 1000)
    }


# ================================================================
# CONFIGURATION SYSTÈME
# ================================================================

@app.get("/config")
async def get_config():
    """Retourne la configuration effective (DB en priorité, fallback config.py)."""
    return face_recognizer.db.get_effective_config()


@app.put("/config")
async def update_config(updates: dict, authorization: Optional[str] = Header(None)):
    """
    Met à jour un ou plusieurs paramètres de configuration.
    Body JSON : {"ALERT_GRACE_PERIOD": 90, "MFA_REQUIRED": true}
    Les clés inconnues sont ignorées silencieusement.
    """
    _check_token(authorization)
    allowed = set(face_recognizer.db.get_effective_config().keys())
    applied = {}
    for key, value in updates.items():
        if key in allowed:
            face_recognizer.db.set_config(key, value)
            applied[key] = value
    return {"success": True, "applied": applied}


@app.get("/config/templates")
async def get_templates():
    """Retourne les 4 templates disponibles avec leurs valeurs."""
    return face_recognizer.db.get_templates()


@app.post("/config/apply_template")
async def apply_template(template: str = Form(...)):
    """
    Applique un template comme configuration de base.
    Valeurs : PORTAIL, DOMICILE, BUREAU, HAUTE_SECURITE.
    L'utilisateur peut ensuite personnaliser via PUT /config.
    """
    ok = face_recognizer.db.apply_template(template)
    if not ok:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": f"Template '{template}' inconnu."}
        )
    return {"success": True, "message": f"Template '{template.upper()}' appliqué."}


# ================================================================
# LOGS & STATISTIQUES
# ================================================================

@app.get("/logs")
async def get_logs(
    limit:      int            = Query(50, ge=1, le=500),
    offset:     int            = Query(0, ge=0),
    event_type: Optional[str]  = Query(None),
    name:       Optional[str]  = Query(None),
    date_from:  Optional[str]  = Query(None),
    date_to:    Optional[str]  = Query(None),
):
    """
    Retourne les logs paginés et filtrés.
    Paramètres optionnels : event_type, name, date_from (ISO), date_to (ISO).
    """
    logs = face_recognizer.db.get_logs(
        limit=limit, offset=offset,
        event_type=event_type, name=name,
        date_from=date_from, date_to=date_to,
    )
    return {"success": True, "count": len(logs), "logs": logs}


@app.get("/logs/stats")
async def get_log_stats():
    """Résumé statistique pour le dashboard (entrées VIP, intrus, alertes du jour)."""
    return {"success": True, "stats": face_recognizer.db.get_log_stats()}


@app.delete("/logs/purge")
async def purge_logs(retention_hours: Optional[int] = Query(None)):
    """
    Purge les logs et snapshots antérieurs à retention_hours.
    Si non précisé, utilise RGPD_SNAPSHOT_RETENTION_HOURS depuis la config.
    IMPORTANT : doit être déclaré AVANT /logs/{log_id} sinon FastAPI parse "purge" comme int → 422.
    """
    deleted = face_recognizer.db.purge_old_snapshots(retention_hours)
    return {"success": True, "deleted": deleted}


@app.delete("/logs/{log_id}")
async def delete_log(log_id: int):
    """Supprime un log individuel et son snapshot associé (droit à l'oubli RGPD)."""
    face_recognizer.db.delete_log(log_id)
    return {"success": True, "message": f"Log #{log_id} supprimé."}


# ================================================================
# ACTIONS IoT & MFA (testables depuis le terminal client)
# ================================================================

@app.get("/access_status")
async def access_status():
    """
    Retourne l'état de tous les objets trackés (Trust Score) + actionneurs IoT.
    Utile pour le dashboard et pour l'UI de test clavier.
    """
    return {
        "success":    True,
        "iot":        iot.get_status(),
        "trust_scores": {
            str(oid): state
            for oid, state in trust_mgr.get_all_states().items()
        },
    }


@app.post("/fingerprint_result")
async def fingerprint_result(
    object_id: int  = Form(...),
    success:   bool = Form(...),
):
    """
    Reçoit le résultat du lecteur d'empreinte (depuis l'ESP32 ou la simulation clavier).
    success=True  → accès GRANTED (100%)
    success=False → accès DENIED
    """
    ts = trust_mgr.get(object_id)
    if ts is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": f"Aucun individu tracké avec ID={object_id}."}
        )

    iot.fingerprint_result(success)

    if success:
        ts.fingerprint_confirmed()
        iot.open_door()
        iot.set_light_welcome()
        face_recognizer.db.log_event(
            ts.vip_name or "VIP", 100.0,
            event_type=DatabaseManager.EVENT_FINGERPRINT_OK, role="VIP"
        )
        # Ground Truth Learning : apprendre le visage actuel confirmé par empreinte
        face_recognizer.learn_from_confirmation(object_id, ts.vip_name or "VIP")
        logger.info(f"[MFA] Empreinte OK pour ID={object_id} → porte ouverte.")
    else:
        ts.fingerprint_failed()
        face_recognizer.db.log_event(
            ts.vip_name or "VIP", 0.0,
            event_type=DatabaseManager.EVENT_FINGERPRINT_FAIL, role="VIP"
        )
        logger.warning(f"[MFA] Empreinte REFUSÉE pour ID={object_id}.")

    return {"success": True, "state": ts.get_state()}


@app.post("/request_liveness")
async def request_liveness(object_id: int = Form(...)):
    """
    Bascule un VIP de FINGERPRINT_PENDING vers LIVENESS_PENDING
    (l'utilisateur choisit le challenge sourire/clignement comme alternative).
    """
    ts = trust_mgr.get(object_id)
    if ts is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": f"Aucun individu tracké avec ID={object_id}."}
        )
    ts.request_liveness()
    logger.info(f"[MFA] Liveness challenge démarré pour ID={object_id}.")
    return {"success": True, "state": ts.get_state()}


@app.post("/liveness_result")
async def liveness_result(
    object_id: int  = Form(...),
    success:   bool = Form(...),
):
    """
    Reçoit le résultat du challenge liveness (depuis /analyze_frame ou simulation).
    success=True  → accès GRANTED (85%)
    success=False → accès DENIED
    """
    ts = trust_mgr.get(object_id)
    if ts is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": f"Aucun individu tracké avec ID={object_id}."}
        )

    if success:
        ts.liveness_success()
        iot.open_door()
        iot.set_light_welcome()
        face_recognizer.db.log_event(
            ts.vip_name or "VIP", 85.0,
            event_type=DatabaseManager.EVENT_LIVENESS_SUCCESS, role="VIP"
        )
        logger.info(f"[MFA] Liveness OK pour ID={object_id} → porte ouverte.")
    else:
        ts.liveness_failed()
        logger.warning(f"[MFA] Liveness REFUSÉE pour ID={object_id}.")

    return {"success": True, "state": ts.get_state()}


@app.post("/iot/door")
async def iot_door(action: str = Form(...), authorization: Optional[str] = Header(None)):
    """
    Contrôle manuel de la porte (simulation clavier).
    action = 'open' | 'close' | 'toggle'
    """
    _check_token(authorization)
    if action == "open":
        iot.open_door()
    elif action == "close":
        iot.close_door()
    elif action == "toggle":
        iot.toggle_door()
    else:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": f"Action inconnue : '{action}'."}
        )
    return {"success": True, "door": iot.door_state}


@app.post("/iot/fingerprint")
async def iot_fingerprint(action: str = Form(...), authorization: Optional[str] = Header(None)):
    """
    Contrôle manuel du lecteur d'empreinte (simulation clavier).
    action = 'wake' | 'sleep'
    """
    _check_token(authorization)
    if action == "wake":
        iot.wake_fingerprint()
    elif action == "sleep":
        iot.sleep_fingerprint()
    else:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": f"Action inconnue : '{action}'."}
        )
    return {"success": True, "fingerprint": iot.fingerprint_state}


@app.post("/iot/light")
async def iot_light(action: str = Form(...), authorization: Optional[str] = Header(None)):
    """
    Contrôle manuel de l'éclairage (simulation clavier).
    action = 'welcome' | 'alert' | 'off'
    """
    _check_token(authorization)
    if action == "welcome":
        iot.set_light_welcome()
    elif action == "alert":
        iot.set_light_alert()
    elif action == "off":
        iot.set_light_off()
    else:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": f"Action inconnue : '{action}'."}
        )
    return {"success": True, "light": iot.light_state}


# ================================================================
# DASHBOARD — HEALTH · PROFILES · STREAM · PAIRING · AUTH
# ================================================================

@app.get("/health")
async def health():
    """Ping rapide pour l'indicateur de connexion du dashboard."""
    return {"ok": True, "version": "7.0"}


# ── Pairing & Auth ────────────────────────────────────────────────────

@app.post("/pair/request")
async def pair_request():
    """
    Génère un PIN 6 chiffres et l'affiche dans le terminal du serveur.
    Le dashboard Electron l'envoie ensuite via POST /auth/token pour obtenir un JWT.
    """
    global _pair_pin, _pair_pin_expires, _pair_pin_attempts
    _pair_pin          = str(secrets.randbelow(900_000) + 100_000)
    _pair_pin_expires  = time.time() + _PAIR_TTL
    _pair_pin_attempts = 0
    border = "=" * 52
    logger.info(f"[DASHBOARD] PIN de couplage : {_pair_pin} (valide 5 min)")
    print(f"\n{border}\n  BioGate Dashboard — PIN de couplage : {_pair_pin}\n{border}\n", flush=True)
    return {"success": True, "message": "PIN généré — consultez le terminal du serveur."}


class _PinBody(BaseModel):
    pin: str


@app.post("/auth/token")
async def auth_token(body: _PinBody):
    """Valide le PIN et retourne un token opaque (durée 30 jours en RAM)."""
    global _dashboard_token, _pair_pin, _pair_pin_attempts
    if not _pair_pin or time.time() > _pair_pin_expires:
        raise HTTPException(status_code=400, detail="Aucun PIN actif — relancez le couplage.")
    if _pair_pin_attempts >= _PAIR_MAX_TRIES:
        raise HTTPException(status_code=429, detail="Trop de tentatives — relancez le couplage.")
    _pair_pin_attempts += 1
    if body.pin.strip() != _pair_pin:
        left = _PAIR_MAX_TRIES - _pair_pin_attempts
        raise HTTPException(status_code=401, detail=f"PIN incorrect ({left} essai(s) restant(s)).")
    _dashboard_token = secrets.token_urlsafe(32)
    _pair_pin = None
    logger.success("[DASHBOARD] Dashboard couplé avec succès.")
    return {"access_token": _dashboard_token, "token_type": "bearer"}


# ── Profils VIP ───────────────────────────────────────────────────────

@app.get("/profiles")
async def get_profiles(authorization: Optional[str] = Header(None)):
    """Retourne la liste des VIP enrôlés avec leur nombre d'embeddings."""
    _check_token(authorization)
    cache    = face_recognizer._embeddings_cache
    profiles = [
        {"name": name, "embedding_count": len(sigs)}
        for name, sigs in cache.items()
    ]
    return {"success": True, "profiles": profiles}


@app.delete("/profiles/{name}")
async def delete_profile(name: str, authorization: Optional[str] = Header(None)):
    """Supprime tous les embeddings d'un VIP (droit à l'oubli RGPD)."""
    _check_token(authorization)
    face_recognizer.db.delete_profile(name)
    face_recognizer.reload_cache()
    logger.info(f"[DASHBOARD] Profil supprimé : {name}")
    return {"success": True, "message": f"Profil '{name}' supprimé."}


# ── Flux MJPEG ────────────────────────────────────────────────────────

async def _mjpeg_generator():
    """
    F6 corrigé : pas de try/except CancelledError.
    Quand le client se déconnecte, asyncio lève CancelledError à await asyncio.sleep().
    Python propage naturellement hors du générateur — Starlette gère le reste.
    Avaler CancelledError violerait le contrat de cancellation coopérative d'asyncio.
    """
    while True:
        if _latest_frame_jpg:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + _latest_frame_jpg
                + b"\r\n"
            )
        await asyncio.sleep(0.033)


@app.get("/stream")
async def stream(token: str = Query(...)):
    """Flux vidéo MJPEG pour le dashboard. Token passé en query param."""
    if token != _dashboard_token:
        raise HTTPException(status_code=401, detail="Token invalide")
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ── IoT raccourcis dashboard ──────────────────────────────────────────

@app.post("/iot/door/open")
async def iot_door_open(authorization: Optional[str] = Header(None)):
    _check_token(authorization)
    iot.open_door()
    return {"success": True, "door": iot.door_state}


@app.post("/iot/door/lock")
async def iot_door_lock(authorization: Optional[str] = Header(None)):
    _check_token(authorization)
    iot.close_door()
    return {"success": True, "door": iot.door_state}


# ================================================================
# CAMÉRAS — CRUD + STREAM PAR SOURCE
# ================================================================

class _CameraBody(BaseModel):
    name:      str
    type:      str = "usb"
    url:       str = ""
    usb_index: int = 0
    zone:      str = ""


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


@app.get("/cameras")
async def list_cameras(authorization: Optional[str] = Header(None)):
    """Retourne toutes les sources vidéo enregistrées avec leur statut temps-réel."""
    _check_token(authorization)
    db_rows  = face_recognizer.db.get_cameras()
    live_map = {s["cam_id"]: s for s in cam_mgr.all_info()}
    cameras  = []
    for row in db_rows:
        cid  = row["cam_id"]
        live = live_map.get(cid, {})
        cameras.append({
            **row,
            "connected": live.get("connected", False),
            "fps":       live.get("fps", 0.0),
            "running":   cid in live_map,
        })
    return {"success": True, "cameras": cameras}


@app.post("/cameras")
async def add_camera(body: _CameraBody, authorization: Optional[str] = Header(None)):
    """Ajoute une nouvelle source vidéo et la démarre immédiatement."""
    _check_token(authorization)
    cam_id = f"{_slug(body.name)}_{secrets.token_hex(3)}"
    cfg = {
        "name":      body.name,
        "type":      body.type,
        "url":       body.url,
        "usb_index": body.usb_index,
        "zone":      body.zone,
    }
    try:
        face_recognizer.db.add_camera(
            cam_id=cam_id, name=body.name, cam_type=body.type,
            url=body.url, usb_index=body.usb_index, zone=body.zone,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    cam_mgr.add(cam_id, cfg)
    logger.info(f"[CAM] Nouvelle source '{body.name}' ({body.type}) → {cam_id}")
    return {"success": True, "cam_id": cam_id}


@app.put("/cameras/{cam_id}")
async def update_camera(cam_id: str, body: _CameraBody, authorization: Optional[str] = Header(None)):
    """Met à jour une source vidéo et la redémarre."""
    _check_token(authorization)
    if not face_recognizer.db.get_camera(cam_id):
        raise HTTPException(status_code=404, detail=f"Caméra '{cam_id}' introuvable.")
    cfg = {
        "name":      body.name,
        "type":      body.type,
        "url":       body.url,
        "usb_index": body.usb_index,
        "zone":      body.zone,
    }
    face_recognizer.db.update_camera(cam_id, **cfg)
    cam_mgr.add(cam_id, cfg)   # redémarre la source
    logger.info(f"[CAM] Source '{cam_id}' mise à jour.")
    return {"success": True}


@app.delete("/cameras/{cam_id}")
async def delete_camera(cam_id: str, authorization: Optional[str] = Header(None)):
    """Arrête et supprime une source vidéo."""
    _check_token(authorization)
    if not face_recognizer.db.get_camera(cam_id):
        raise HTTPException(status_code=404, detail=f"Caméra '{cam_id}' introuvable.")
    cam_mgr.remove(cam_id)
    face_recognizer.db.delete_camera(cam_id)
    logger.info(f"[CAM] Source '{cam_id}' supprimée.")
    return {"success": True}


@app.get("/cameras/scan/usb")
def scan_usb_cameras(authorization: Optional[str] = Header(None)):
    """
    Détecte les webcams USB branchées.
    Déclaré en `def` (non async) → FastAPI l'exécute dans un thread pool,
    évitant de bloquer la boucle asyncio pendant le scan OpenCV.
    """
    _check_token(authorization)
    found = CameraManager.scan_usb(max_index=4)   # indices 0..3 suffisent dans 99% des cas
    return {"success": True, "devices": found}


async def _mjpeg_cam_generator(cam_id: str):
    """F6 corrigé : CancelledError propagé naturellement, pas avalé."""
    while True:
        src = cam_mgr.get(cam_id)
        if src:
            jpg = src.get_stream_jpg()
            if jpg:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + jpg
                    + b"\r\n"
                )
        await asyncio.sleep(0.033)


@app.get("/stream/{cam_id}")
async def stream_camera(cam_id: str, token: str = Query(...)):
    """Flux MJPEG d'une source vidéo identifiée par cam_id."""
    if token != _dashboard_token:
        raise HTTPException(status_code=401, detail="Token invalide")
    if cam_mgr.get(cam_id) is None:
        raise HTTPException(status_code=404, detail=f"Caméra '{cam_id}' non active")
    return StreamingResponse(
        _mjpeg_cam_generator(cam_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
