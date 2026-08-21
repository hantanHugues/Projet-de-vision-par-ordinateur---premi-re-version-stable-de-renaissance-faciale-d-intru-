"""
Client Caméra BioGate — v7
Flux vidéo local → serveur IA → affichage enrichi avec Trust Score + panneau IoT.

Commandes clavier (terminal vide uniquement) :
  o  → Ouvrir la porte
  c  → Fermer la porte
  e  → Simuler empreinte OK   (pour le premier objet suivi)
  r  → Simuler empreinte FAIL (pour le premier objet suivi)
  l  → Basculer en Liveness challenge
  w  → Éclairage ACCUEIL (vert)
  a  → Éclairage ALERTE  (rouge)
  x  → Éclairage ÉTEINT
  s  → Afficher /access_status dans le terminal
  Esc → Quitter

Commandes terminal (tapez puis Entrée) :
  enroll [Prénom]  → Inscrire un VIP
  quit / exit      → Quitter
"""

import cv2
import requests
import time
import numpy as np
import threading
import json
import os
from datetime import datetime
import config

# ------------------------------------------------------------------ #
#  URLs API                                                            #
# ------------------------------------------------------------------ #
BASE_URL   = f"http://{config.SERVER_HOST}:{config.SERVER_PORT}"
SERVER_URL = config.SERVER_ANALYZE_URL
ENROLL_URL = config.SERVER_ENROLL_URL

# ------------------------------------------------------------------ #
#  Variables globales (multithreading safe)                           #
# ------------------------------------------------------------------ #

# Seuils debug (identiques à liveness_detector.py)
_DBG_BLINK = 0.35
_DBG_SMILE = 0.45
_DBG_LOG_DIR = os.path.join("tests", "liveness_debug")

# État du mode debug blendshapes (T = start, Y = stop+save)
_dbg = {
    "active":       False,
    "landmarker":   None,
    "mp":           None,
    "raw_buffer":   [],
    "events":       [],
    "last_sample":  0.0,
    "was_blinking": False,
    "was_smiling":  False,
    "frame_count":  0,
    "session_start": None,
}


def _debug_start():
    """Charge MediaPipe et démarre la capture blendshapes."""
    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision
        model = "models/face_landmarker.task"
        if not os.path.exists(model):
            return False, "Modele face_landmarker.task absent."
        opts = mp_vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model),
            output_face_blendshapes=True,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        _dbg["landmarker"]   = mp_vision.FaceLandmarker.create_from_options(opts)
        _dbg["mp"]           = mp
        _dbg["active"]       = True
        _dbg["raw_buffer"]   = []
        _dbg["events"]       = []
        _dbg["last_sample"]  = time.time()
        _dbg["was_blinking"] = False
        _dbg["was_smiling"]  = False
        _dbg["frame_count"]  = 0
        _dbg["session_start"] = datetime.now().isoformat(timespec="milliseconds")
        return True, "[DBG] Enregistrement blendshapes DEMARRE — appuie Y pour stopper."
    except Exception as e:
        return False, f"[DBG] Erreur init: {e}"


def _debug_analyze(frame_bgr):
    """
    Analyse une frame avec MediaPipe, logue les valeurs et retourne
    un dict de valeurs à afficher (ou None si pas de visage).
    """
    if not _dbg["active"] or _dbg["landmarker"] is None:
        return None
    import cv2 as _cv2
    mp   = _dbg["mp"]
    now  = time.time()
    rgb  = _cv2.cvtColor(frame_bgr, _cv2.COLOR_BGR2RGB)
    img  = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    res  = _dbg["landmarker"].detect(img)
    _dbg["frame_count"] += 1

    if not res.face_blendshapes:
        return None

    bs      = {b.category_name: b.score for b in res.face_blendshapes[0]}
    bl_l    = float(bs.get("eyeBlinkLeft",    0))
    bl_r    = float(bs.get("eyeBlinkRight",   0))
    sm_l    = float(bs.get("mouthSmileLeft",  0))
    sm_r    = float(bs.get("mouthSmileRight", 0))
    blink   = (bl_l + bl_r) / 2
    smile   = (sm_l + sm_r) / 2
    is_bl   = blink > _DBG_BLINK
    is_sm   = smile > _DBG_SMILE

    # Enregistrement brut 1×/seconde
    if now - _dbg["last_sample"] >= 1.0:
        _dbg["raw_buffer"].append({
            "t":             datetime.now().isoformat(timespec="milliseconds"),
            "eyeBlinkLeft":  round(bl_l, 4),
            "eyeBlinkRight": round(bl_r, 4),
            "blink_avg":     round(blink, 4),
            "mouthSmileLeft":  round(sm_l, 4),
            "mouthSmileRight": round(sm_r, 4),
            "smile_avg":     round(smile, 4),
            "blinking":      is_bl,
            "smiling":       is_sm,
        })
        _dbg["last_sample"] = now

    # Événements (front montant/descendant)
    ts = datetime.now().isoformat(timespec="milliseconds")
    if is_bl and not _dbg["was_blinking"]:
        _dbg["events"].append({"t": ts, "event": "BLINK_START", "blink_avg": round(blink, 4)})
    if not is_bl and _dbg["was_blinking"]:
        _dbg["events"].append({"t": ts, "event": "BLINK_END",   "blink_avg": round(blink, 4)})
    if is_sm and not _dbg["was_smiling"]:
        _dbg["events"].append({"t": ts, "event": "SMILE_START", "smile_avg": round(smile, 4)})
    if not is_sm and _dbg["was_smiling"]:
        _dbg["events"].append({"t": ts, "event": "SMILE_END",   "smile_avg": round(smile, 4)})

    _dbg["was_blinking"] = is_bl
    _dbg["was_smiling"]  = is_sm

    return {"bl_l": bl_l, "bl_r": bl_r, "blink": blink, "is_bl": is_bl,
            "sm_l": sm_l, "sm_r": sm_r, "smile": smile, "is_sm": is_sm}


def _debug_save():
    """Arrête le mode debug et sauvegarde les deux fichiers de logs."""
    if not _dbg["active"]:
        return False, "[DBG] Aucun enregistrement actif."
    _dbg["active"] = False
    if _dbg["landmarker"]:
        _dbg["landmarker"].close()
        _dbg["landmarker"] = None

    os.makedirs(_DBG_LOG_DIR, exist_ok=True)
    now_str  = datetime.now().strftime("%Y%m%d_%Hh%Mm%Ss")
    raw_path = os.path.join(_DBG_LOG_DIR, f"raw_{now_str}.jsonl")
    evt_path = os.path.join(_DBG_LOG_DIR, f"events_{now_str}.json")

    with open(raw_path, "w", encoding="utf-8") as f:
        for entry in _dbg["raw_buffer"]:
            f.write(json.dumps(entry) + "\n")

    with open(evt_path, "w", encoding="utf-8") as f:
        json.dump({
            "session_start": _dbg["session_start"],
            "session_end":   datetime.now().isoformat(timespec="milliseconds"),
            "frames":        _dbg["frame_count"],
            "thresholds":    {"blink": _DBG_BLINK, "smile": _DBG_SMILE},
            "events":        _dbg["events"],
        }, f, indent=2, ensure_ascii=False)

    n_raw = len(_dbg["raw_buffer"])
    n_evt = len(_dbg["events"])
    return True, f"[DBG] Sauvegarde OK — {n_raw} mesures, {n_evt} evenements → tests/liveness_debug/"


def _draw_debug_overlay(frame, vals):
    """Dessine le panneau blendshapes en haut à droite de la frame."""
    if vals is None:
        return
    h, w = frame.shape[:2]
    px, py, pw, ph = w - 290, 10, 278, 160

    # Fond semi-transparent
    ov = frame.copy()
    cv2.rectangle(ov, (px, py), (px + pw, py + ph), (0, 0, 0), -1)
    cv2.addWeighted(ov, 0.6, frame, 0.4, 0, frame)

    def bar(y, val, threshold, label, clr):
        cv2.putText(frame, f"{label}: {val:.3f}", (px + 6, y), FONT, 0.42, clr, 1)
        bw = int(min(val, 1.0) * 200)
        cv2.rectangle(frame, (px + 6, y + 3),  (px + 206, y + 11), GREY, -1)
        cv2.rectangle(frame, (px + 6, y + 3),  (px + 6 + bw, y + 11), clr, -1)
        tx = px + 6 + int(threshold * 200)
        cv2.line(frame, (tx, y + 1), (tx, y + 13), YELLOW, 2)

    y0 = py + 16
    cv2.putText(frame, "DBG BLENDSHAPES [Y=stop]", (px + 4, y0), FONT, 0.38, YELLOW, 1)

    y0 += 18
    clr = GREEN if vals["is_bl"] else RED
    bar(y0, vals["blink"], _DBG_BLINK, "BLINK", clr)

    y0 += 30
    clr = GREEN if vals["is_sm"] else RED
    bar(y0, vals["smile"], _DBG_SMILE, "SMILE", clr)

    y0 += 30
    cv2.putText(frame, f"  bl_L={vals['bl_l']:.3f}  bl_R={vals['bl_r']:.3f}",
                (px + 4, y0), FONT, 0.38, GREY, 1)
    y0 += 16
    cv2.putText(frame, f"  sm_L={vals['sm_l']:.3f}  sm_R={vals['sm_r']:.3f}",
                (px + 4, y0), FONT, 0.38, GREY, 1)

    y0 += 18
    status = "BLINK !" if vals["is_bl"] else ("SMILE !" if vals["is_sm"] else "neutre")
    clr    = GREEN if (vals["is_bl"] or vals["is_sm"]) else GREY
    cv2.putText(frame, f"  >> {status}  [{len(_dbg['events'])} evt]",
                (px + 4, y0), FONT, 0.42, clr, 1)


# ------------------------------------------------------------------ #
#  MediaPipe local pour liveness (actif automatiquement en LIVENESS_PENDING)
# ------------------------------------------------------------------ #
_live = {
    "active":      False,
    "landmarker":  None,
    "mp":          None,
    "blink_score": 0.0,
    "smile_score": 0.0,
}


def _live_start():
    """Charge MediaPipe et active la détection liveness locale à 30fps."""
    if _live["active"]:
        return True
    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision
        model = "models/face_landmarker.task"
        if not os.path.exists(model):
            return False
        opts = mp_vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model),
            output_face_blendshapes=True,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        _live["landmarker"] = mp_vision.FaceLandmarker.create_from_options(opts)
        _live["mp"]         = mp
        _live["active"]     = True
        return True
    except Exception:
        return False


def _live_stop():
    """Arrête la détection liveness locale et remet les scores à zéro."""
    _live["active"]      = False
    _live["blink_score"] = 0.0
    _live["smile_score"] = 0.0
    if _live["landmarker"]:
        _live["landmarker"].close()
        _live["landmarker"] = None


def _live_analyze(frame_bgr):
    """Analyse une frame BGR et met à jour blink_score / smile_score dans _live."""
    if not _live["active"] or _live["landmarker"] is None:
        return
    import cv2 as _cv2
    rgb = _cv2.cvtColor(frame_bgr, _cv2.COLOR_BGR2RGB)
    img = _live["mp"].Image(image_format=_live["mp"].ImageFormat.SRGB, data=rgb)
    res = _live["landmarker"].detect(img)
    if not res.face_blendshapes:
        return
    bs = {b.category_name: b.score for b in res.face_blendshapes[0]}
    _live["blink_score"] = (bs.get("eyeBlinkLeft", 0) + bs.get("eyeBlinkRight", 0)) / 2
    _live["smile_score"] = (bs.get("mouthSmileLeft", 0) + bs.get("mouthSmileRight", 0)) / 2


latest_frame = None
latest_data  = {
    "detections": [],
    "server_ping": 0,
    "fps_net": 0,
    "status": "Démarrage...",
    "iot": {"door": "LOCKED", "fingerprint": "IDLE", "light": "OFF", "iot_enabled": False},
}
is_running = True


# ------------------------------------------------------------------ #
#  Thread réseau                                                       #
# ------------------------------------------------------------------ #
def network_worker():
    global latest_frame, latest_data, is_running

    while is_running:
        if latest_frame is None:
            time.sleep(0.01)
            continue

        start_net = time.time()
        frame_to_send = latest_frame.copy()

        _, img_encoded = cv2.imencode(
            '.jpg', frame_to_send, [cv2.IMWRITE_JPEG_QUALITY, 80]
        )

        try:
            live_data = {}
            if _live["active"]:
                live_data = {
                    "liveness_blink": str(round(_live["blink_score"], 4)),
                    "liveness_smile": str(round(_live["smile_score"], 4)),
                }
            response = requests.post(
                SERVER_URL,
                files={"file": ("frame.jpg", img_encoded.tobytes(), "image/jpeg")},
                data=live_data,
                timeout=5.0,  # 5s : couvre le 1er chargement DeepFace (~3-4s)
            )
            if response.status_code == 200:
                data = response.json()
                fps = 1.0 / max(time.time() - start_net, 0.001)
                if data.get("success"):
                    latest_data = {
                        "detections":  data.get("detections", []),
                        "server_ping": int(data.get("process_time_ms", 0)),
                        "fps_net":     fps,
                        "status":      "Connecte",
                        "iot":         data.get("iot", latest_data["iot"]),
                    }
            else:
                latest_data["status"] = f"ERREUR API: {response.status_code}"
                time.sleep(0.5)

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            latest_data["status"] = "Serveur IA INACCESSIBLE"
            time.sleep(1.0)

        except Exception as e:
            # Erreur inattendue (JSON malformé, etc.) — on ne crashe pas le thread
            latest_data["status"] = f"Erreur: {type(e).__name__}"
            time.sleep(0.5)


# ------------------------------------------------------------------ #
#  Helpers API (appels rapides depuis les touches clavier)            #
# ------------------------------------------------------------------ #
def _first_object_id():
    """Retourne l'object_id du premier individu visible, ou None."""
    dets = latest_data.get("detections", [])
    return dets[0]["object_id"] if dets else None


def api_post(path, data=None):
    """POST non-bloquant vers l'API. Retourne le JSON ou None."""
    try:
        r = requests.post(f"{BASE_URL}{path}", data=data, timeout=2.0)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def api_get(path):
    try:
        r = requests.get(f"{BASE_URL}{path}", timeout=2.0)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


# ------------------------------------------------------------------ #
#  Rendu UI                                                            #
# ------------------------------------------------------------------ #

# Couleurs (BGR)
GREEN   = (0, 220, 0)
RED     = (0, 0, 220)
ORANGE  = (0, 165, 255)
YELLOW  = (0, 220, 220)
CYAN    = (220, 220, 0)
WHITE   = (240, 240, 240)
GREY    = (160, 160, 160)
DARK    = (30, 30, 30)

FONT = cv2.FONT_HERSHEY_SIMPLEX


def _trust_label(trust):
    """Retourne (texte, couleur) selon l'état Trust Score."""
    if trust is None:
        return "", GREY
    state = trust.get("state", "")
    score = trust.get("score", 0)
    mapping = {
        "IDLE":                ("...", GREY),
        "ANALYZING":           ("Analyse…", YELLOW),
        "FACE_MATCHED":        (f"Visage {score:.0f}%", CYAN),
        "FINGERPRINT_PENDING": ("Empreinte…", ORANGE),
        "LIVENESS_PENDING":    ("Liveness…", ORANGE),
        "GRANTED":             (f"ACCÈS OK {score:.0f}%", GREEN),
        "DENIED":              ("REFUSÉ", RED),
        "INTRUDER_PENDING":    ("Intrus (grâce…)", ORANGE),
        "INTRUDER_CONFIRMED":  ("INTRUS CONFIRMÉ", RED),
    }
    return mapping.get(state, (state, GREY))


def _iot_color(state_map):
    door_clr  = GREEN if state_map.get("door") == "OPEN"     else RED
    fp_clr    = GREEN if state_map.get("fingerprint") == "OK" else \
                RED   if state_map.get("fingerprint") == "FAIL" else \
                ORANGE if state_map.get("fingerprint") == "WAITING" else GREY
    light_clr = GREEN  if state_map.get("light") == "WELCOME" else \
                RED    if state_map.get("light") == "ALERT"   else GREY
    return door_clr, fp_clr, light_clr


def draw_iot_panel(canvas, iot, w, y_start=5):
    """Dessine la barre de statut IoT en haut du panneau terminal."""
    door_clr, fp_clr, light_clr = _iot_color(iot)
    mock_str = "[MOCK]" if not iot.get("iot_enabled", False) else "[RÉEL]"

    cv2.putText(canvas, mock_str, (w - 80, y_start + 14),
                FONT, 0.45, ORANGE, 1)

    items = [
        (f"PORTE: {iot.get('door','?')}",           door_clr),
        (f"EMPRT: {iot.get('fingerprint','?')}",    fp_clr),
        (f"LUM: {iot.get('light','?')}",            light_clr),
    ]
    x = 10
    for label, clr in items:
        cv2.putText(canvas, label, (x, y_start + 14), FONT, 0.48, clr, 1)
        x += 185


def draw_shortcuts(canvas, w, y):
    hints = "o=ouvrir  c=fermer  e=OK empr  r=FAIL  l=live  w=accueil  a=alerte  x=lumoff  t=dbg-start  y=dbg-save"
    cv2.putText(canvas, hints, (10, y), FONT, 0.38, GREY, 1)


# ------------------------------------------------------------------ #
#  Boucle principale                                                   #
# ------------------------------------------------------------------ #
def start_client():
    global latest_frame, is_running, latest_data

    print("=== BioGate — Source Vidéo ===")
    print("1. Webcam locale (défaut)")
    print("2. IP Webcam (LAN)")
    choice = input("Choix [1] : ").strip()

    if choice == "2":
        url = input("URL flux (ex: http://192.168.1.95:8080/video) : ").strip()
        source = url or "http://192.168.1.95:8080/video"
        cap = cv2.VideoCapture(source)
        print(f"Connexion au flux : {source}")
    else:
        cap = cv2.VideoCapture(0)
        print("Webcam locale démarrée.")

    if not cap.isOpened():
        print("[ERREUR] Source vidéo inaccessible.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Terminal UI
    terminal_lines = [
        "=== BioGate v7 — Terminal ===",
        "Tapez 'enroll [Prénom]' pour inscrire un VIP.",
        "Raccourcis clavier : o=ouvrir c=fermer e=OK r=FAIL l=live s=status",
    ]
    terminal_input = ""
    mode           = "NORMAL"
    enroll_name    = ""
    enroll_start   = 0

    def log(msg):
        terminal_lines.append(msg)
        if len(terminal_lines) > 6:
            terminal_lines.pop(0)

    # Démarrage du thread réseau
    net_thread = threading.Thread(target=network_worker, daemon=True)
    net_thread.start()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        latest_frame = frame.copy()
        h_frame, w_frame = frame.shape[:2]
        data = latest_data.copy()

        # Auto-activation MediaPipe liveness local (30fps) quand LIVENESS_PENDING
        any_liveness = any(
            (obj.get("trust") or {}).get("state") == "LIVENESS_PENDING"
            for obj in data.get("detections", [])
        )
        if any_liveness and not _live["active"]:
            _live_start()
        elif not any_liveness and _live["active"]:
            _live_stop()
        if _live["active"]:
            _live_analyze(frame)

        # ----------------------------------------------------------
        # A. DESSIN DES DÉTECTIONS (mode normal)
        # ----------------------------------------------------------
        if mode == "NORMAL" and data["status"] == "Connecte":
            for obj in data["detections"]:
                x, y, w, h = obj["bbox"]
                identity   = obj.get("identity", "?")
                object_id  = obj["object_id"]
                trust      = obj.get("trust")

                is_vip     = identity and not identity.startswith("Intrus") \
                             and "Attente" not in identity \
                             and "Analyse" not in identity \
                             and "Re-" not in identity

                box_color = GREEN if is_vip else RED

                # Bounding box principale
                cv2.rectangle(frame, (x, y), (x + w, y + h), box_color, 2)

                # Face box cyan
                if obj.get("face_box"):
                    fx, fy, fw, fh = obj["face_box"]
                    cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), CYAN, 1)
                    cv2.putText(frame, "Visage", (fx, fy - 4), FONT, 0.35, CYAN, 1)

                # Label identité
                id_label = f"ID {object_id}: {identity}"
                cv2.putText(frame, id_label, (x, y - 22), FONT, 0.55, box_color, 2)

                # Label Trust Score
                ts_text, ts_color = _trust_label(trust)
                if ts_text:
                    cv2.putText(frame, ts_text, (x, y - 6), FONT, 0.48, ts_color, 1)

                # Challenge Liveness — affichage guidé par blendshapes
                if trust and trust.get("state") == "LIVENESS_PENDING":
                    prog = trust.get("liveness_progress") or {}
                    blinks    = prog.get("blinks", 0)
                    blinks_req = prog.get("blinks_required", 2)
                    smiling   = prog.get("smiling", False)
                    remaining = prog.get("remaining", 0)

                    # Fond semi-transparent sur la boîte
                    overlay = frame.copy()
                    cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 80, 160), -1)
                    frame = cv2.addWeighted(overlay, 0.25, frame, 0.75, 0)

                    cy = y + h // 2 - 25
                    cv2.putText(frame, "-- VERIFICATION --", (x + 4, cy),
                                FONT, 0.45, CYAN, 1)
                    cy += 20
                    blink_txt = f"Clignements : {blinks}/{blinks_req}"
                    blink_clr = GREEN if blinks >= blinks_req else ORANGE
                    cv2.putText(frame, blink_txt, (x + 4, cy), FONT, 0.44, blink_clr, 1)
                    cy += 18
                    smile_txt  = "Sourire detecte !" if smiling else "Souriez 1.5s..."
                    smile_clr  = GREEN if smiling else GREY
                    cv2.putText(frame, smile_txt, (x + 4, cy), FONT, 0.44, smile_clr, 1)
                    cy += 18
                    cv2.putText(frame, f"Temps: {remaining:.1f}s", (x + 4, cy),
                                FONT, 0.42, YELLOW, 1)

            # Infos réseau
            cv2.putText(
                frame,
                f"Ping: {data['server_ping']}ms | Net FPS: {data['fps_net']:.1f}",
                (10, 22), FONT, 0.55, YELLOW, 1,
            )

        # Debug blendshapes (actif si T pressé, indépendant du serveur)
        if _dbg["active"]:
            dbg_vals = _debug_analyze(frame)
            _draw_debug_overlay(frame, dbg_vals)

        elif data["status"] != "Connecte":
            cv2.putText(frame, data["status"], (20, 60), FONT, 1.0, RED, 2)

        # ----------------------------------------------------------
        # B. MODE ENROLLMENT
        # ----------------------------------------------------------
        if mode == "ENROLL_WAIT":
            elapsed   = time.time() - enroll_start
            remaining = 3.0 - elapsed

            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (w_frame, h_frame), (0, 0, 0), -1)
            frame = cv2.addWeighted(overlay, 0.4, frame, 0.6, 0)
            cv2.putText(frame, "Regardez droit devant",
                        (w_frame // 2 - 170, h_frame // 2 - 20),
                        FONT, 0.8, CYAN, 2)
            cv2.putText(frame, f"Capture dans {remaining:.1f}s",
                        (w_frame // 2 - 140, h_frame // 2 + 30),
                        FONT, 0.8, GREEN, 2)

            if remaining <= 0:
                mode = "ENROLL_SHOOT"

        elif mode == "ENROLL_SHOOT":
            flash = np.full((h_frame, w_frame, 3), 255, dtype=np.uint8)
            cv2.imshow("BioGate — Client Caméra", np.vstack(
                (flash, np.zeros((200, w_frame, 3), dtype=np.uint8))
            ))
            cv2.waitKey(60)

            log(f"Envoi photo VIP '{enroll_name}'…")
            _, enc = cv2.imencode('.jpg', latest_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            try:
                r = requests.post(
                    ENROLL_URL,
                    data={"name": enroll_name},
                    files={"file": ("frame.jpg", enc.tobytes(), "image/jpeg")},
                    timeout=5.0,
                )
                res = r.json()
                if res.get("success"):
                    log(f"[OK] {res.get('message', 'Inscrit.')}")
                else:
                    log(f"[ÉCHEC] {res.get('message', 'Erreur.')}")
            except Exception:
                log("[ERREUR] Serveur inaccessible.")

            mode        = "NORMAL"
            enroll_name = ""

        # ----------------------------------------------------------
        # C. PANNEAU TERMINAL BAS
        # ----------------------------------------------------------
        PANEL_H = 200
        panel   = np.full((PANEL_H, w_frame, 3), (15, 15, 15), dtype=np.uint8)

        # Barre IoT
        draw_iot_panel(panel, data["iot"], w_frame, y_start=4)

        # Séparateur
        cv2.line(panel, (0, 24), (w_frame, 24), (60, 60, 60), 1)

        # Logs
        y_txt = 44
        for line in terminal_lines[-6:]:
            cv2.putText(panel, line, (10, y_txt), FONT, 0.43, WHITE, 1)
            y_txt += 22

        # Raccourcis
        cv2.line(panel, (0, PANEL_H - 42), (w_frame, PANEL_H - 42), (60, 60, 60), 1)
        draw_shortcuts(panel, w_frame, PANEL_H - 28)

        # Ligne de saisie
        cv2.putText(panel, f"$ {terminal_input}_",
                    (10, PANEL_H - 10), FONT, 0.55, GREEN, 1)

        final = np.vstack((frame, panel))
        cv2.imshow("BioGate — Client Caméra", final)

        # ----------------------------------------------------------
        # D. CLAVIER
        # ----------------------------------------------------------
        key = cv2.waitKey(1) & 0xFF
        if key == 255:
            continue

        if key == 27:  # Esc
            is_running = False
            break

        if key == 8:   # Backspace
            terminal_input = terminal_input[:-1]
            continue

        if key in (13, 10):  # Entrée
            cmd = terminal_input.strip()
            terminal_input = ""
            if not cmd:
                continue
            log(f"$ {cmd}")
            parts    = cmd.split()
            cmd_name = parts[0].lower()

            if cmd_name == "enroll" and len(parts) > 1:
                enroll_name  = " ".join(parts[1:])
                mode         = "ENROLL_WAIT"
                enroll_start = time.time()
                log(f"Préparation enrôlement '{enroll_name}'…")
            elif cmd_name in ("quit", "exit"):
                is_running = False
                break
            else:
                log("Commandes: enroll [Nom] | quit")
            continue

        # Raccourcis mono-touche (seulement si terminal vide)
        if terminal_input == "":
            oid = _first_object_id()

            if key == ord('o'):
                r = api_post("/iot/door", {"action": "open"})
                log(f"[Porte] OUVERTE" if r else "[Porte] Erreur")

            elif key == ord('c'):
                r = api_post("/iot/door", {"action": "close"})
                log(f"[Porte] FERMÉE" if r else "[Porte] Erreur")

            elif key == ord('e'):
                if oid is None:
                    log("[EMPRT] Aucun individu visible.")
                else:
                    r = api_post("/fingerprint_result", {"object_id": oid, "success": True})
                    log(f"[EMPRT] OK simulé → ID {oid}" if r else "[EMPRT] Erreur")

            elif key == ord('r'):
                if oid is None:
                    log("[EMPRT] Aucun individu visible.")
                else:
                    r = api_post("/fingerprint_result", {"object_id": oid, "success": False})
                    log(f"[EMPRT] FAIL simulé → ID {oid}" if r else "[EMPRT] Erreur")

            elif key == ord('l'):
                if oid is None:
                    log("[LIVE] Aucun individu visible.")
                else:
                    r = api_post("/request_liveness", {"object_id": oid})
                    log(f"[LIVE] Challenge liveness → ID {oid}" if r else "[LIVE] Erreur")

            elif key == ord('w'):
                r = api_post("/iot/light", {"action": "welcome"})
                log("[LUM] Accueil (vert)" if r else "[LUM] Erreur")

            elif key == ord('a'):
                r = api_post("/iot/light", {"action": "alert"})
                log("[LUM] Alerte (rouge)" if r else "[LUM] Erreur")

            elif key == ord('x'):
                r = api_post("/iot/light", {"action": "off"})
                log("[LUM] Éteinte" if r else "[LUM] Erreur")

            elif key == ord('s'):
                r = api_get("/access_status")
                if r:
                    iot_s = r.get("iot", {})
                    log(f"[STATUS] Porte:{iot_s.get('door')} "
                        f"FP:{iot_s.get('fingerprint')} "
                        f"Lum:{iot_s.get('light')}")
                    scores = r.get("trust_scores", {})
                    for oid_k, ts in scores.items():
                        log(f"  ID {oid_k}: {ts.get('state')} score={ts.get('score')}")
                else:
                    log("[STATUS] Serveur inaccessible.")

            elif key == ord('t'):
                if _dbg["active"]:
                    log("[DBG] Deja actif — Y pour stopper.")
                else:
                    ok, msg = _debug_start()
                    log(msg)

            elif key == ord('y'):
                ok, msg = _debug_save()
                log(msg)

            else:
                # Caractère normal → terminal
                if 32 <= key <= 126:
                    terminal_input += chr(key)
        else:
            # Terminal non vide → tout caractère va au terminal
            if 32 <= key <= 126:
                terminal_input += chr(key)

    cap.release()
    cv2.destroyAllWindows()
    print("BioGate client arrêté.")


if __name__ == "__main__":
    start_client()
