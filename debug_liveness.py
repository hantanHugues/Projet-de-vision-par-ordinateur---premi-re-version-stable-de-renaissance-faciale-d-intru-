"""
debug_liveness.py — Visualise en temps réel les blendshapes ET sauvegarde les logs.

Génère deux fichiers dans debug_logs/ :
  - blendshapes_raw.jsonl  : un enregistrement par seconde (valeurs brutes)
  - blendshapes_events.json: uniquement les instants où un seuil est franchi

Appuie sur Q pour quitter et finaliser les fichiers.
"""

import cv2
import json
import os
import time
from datetime import datetime
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

MODEL_PATH  = "models/face_landmarker.task"
LOG_DIR     = "tests/liveness_debug"
RAW_FILE    = os.path.join(LOG_DIR, "blendshapes_raw.jsonl")
EVENTS_FILE = os.path.join(LOG_DIR, "blendshapes_events.json")

# Seuils identiques à liveness_detector.py — modifie ici pour tester
BLINK_THRESHOLD = 0.35
SMILE_THRESHOLD = 0.40   # aligné sur liveness_detector.py (abaissé de 0.45 — pics réels 0.60-0.75)

os.makedirs(LOG_DIR, exist_ok=True)


def ts():
    return datetime.now().isoformat(timespec="milliseconds")


def main():
    base_options = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
    options = mp_vision.FaceLandmarkerOptions(
        base_options=base_options,
        output_face_blendshapes=True,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = mp_vision.FaceLandmarker.create_from_options(options)

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    FONT  = cv2.FONT_HERSHEY_SIMPLEX
    GREEN  = (0, 220, 0)
    RED    = (0, 0, 220)
    YELLOW = (0, 220, 220)
    WHITE  = (240, 240, 240)
    GREY   = (160, 160, 160)
    BLACK  = (0, 0, 0)

    # ── Buffers de logs ─────────────────────────────────────────────
    events      = []          # événements (seuil franchi)
    raw_file    = open(RAW_FILE, "a", encoding="utf-8")
    last_sample = time.time()  # pour n'écrire qu'1 ligne/seconde dans raw
    frame_count = 0
    session_start = ts()

    print(f"[DEBUG] Logs -> {LOG_DIR}/")
    print("[DEBUG] Appuie sur Q pour quitter et sauvegarder.")

    # État précédent pour détecter les fronts montants
    was_blinking = False
    was_smiling  = False

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1
            now = time.time()

            rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = landmarker.detect(mp_img)

            # Fond panneau debug
            overlay = frame.copy()
            cv2.rectangle(overlay, (10, 10), (440, 270), BLACK, -1)
            frame = cv2.addWeighted(overlay, 0.6, frame, 0.4, 0)

            y = 38
            cv2.putText(frame, "=== DEBUG LIVENESS ===", (20, y), FONT, 0.65, YELLOW, 2)

            if not result.face_blendshapes:
                y += 35
                cv2.putText(frame, "Aucun visage detecte !", (20, y), FONT, 0.7, RED, 2)
                was_blinking = was_smiling = False
            else:
                bs = {b.category_name: b.score for b in result.face_blendshapes[0]}

                blink_l = float(bs.get("eyeBlinkLeft",    0.0))
                blink_r = float(bs.get("eyeBlinkRight",   0.0))
                blink   = (blink_l + blink_r) / 2

                smile_l = float(bs.get("mouthSmileLeft",  0.0))
                smile_r = float(bs.get("mouthSmileRight", 0.0))
                smile   = (smile_l + smile_r) / 2

                is_blinking = blink > BLINK_THRESHOLD
                is_smiling  = smile > SMILE_THRESHOLD

                # ── Enregistrement brut (1×/seconde) ────────────────
                if now - last_sample >= 1.0:
                    record = {
                        "t": ts(),
                        "eyeBlinkLeft":    round(blink_l, 4),
                        "eyeBlinkRight":   round(blink_r, 4),
                        "blink_avg":       round(blink,   4),
                        "mouthSmileLeft":  round(smile_l, 4),
                        "mouthSmileRight": round(smile_r, 4),
                        "smile_avg":       round(smile,   4),
                        "blinking":        is_blinking,
                        "smiling":         is_smiling,
                    }
                    raw_file.write(json.dumps(record) + "\n")
                    raw_file.flush()
                    last_sample = now

                # ── Événements : front montant seulement ────────────
                if is_blinking and not was_blinking:
                    evt = {"t": ts(), "event": "BLINK_START",
                           "blink_avg": round(blink, 4)}
                    events.append(evt)
                    print(f"[EVENT] BLINK_START  blink={blink:.3f}")

                if not is_blinking and was_blinking:
                    evt = {"t": ts(), "event": "BLINK_END",
                           "blink_avg": round(blink, 4)}
                    events.append(evt)
                    print(f"[EVENT] BLINK_END")

                if is_smiling and not was_smiling:
                    evt = {"t": ts(), "event": "SMILE_START",
                           "smile_avg": round(smile, 4)}
                    events.append(evt)
                    print(f"[EVENT] SMILE_START  smile={smile:.3f}")

                if not is_smiling and was_smiling:
                    evt = {"t": ts(), "event": "SMILE_END",
                           "smile_avg": round(smile, 4)}
                    events.append(evt)
                    print(f"[EVENT] SMILE_END")

                was_blinking = is_blinking
                was_smiling  = is_smiling

                # ── Affichage ────────────────────────────────────────
                y += 32
                cv2.putText(frame, "CLIGNEMENT", (20, y), FONT, 0.55, WHITE, 1)

                y += 24
                cv2.putText(frame, f"  eyeBlinkLeft  : {blink_l:.3f}",
                            (20, y), FONT, 0.52,
                            GREEN if blink_l > BLINK_THRESHOLD else GREY, 1)
                y += 22
                cv2.putText(frame, f"  eyeBlinkRight : {blink_r:.3f}",
                            (20, y), FONT, 0.52,
                            GREEN if blink_r > BLINK_THRESHOLD else GREY, 1)
                y += 22
                avg_clr = GREEN if is_blinking else RED
                cv2.putText(frame, f"  MOYENNE : {blink:.3f}  (seuil {BLINK_THRESHOLD})",
                            (20, y), FONT, 0.52, avg_clr, 2)
                y += 16
                bw = int(min(blink, 1.0) * 300)
                cv2.rectangle(frame, (20, y), (320, y + 10), GREY, -1)
                cv2.rectangle(frame, (20, y), (20 + bw, y + 10), avg_clr, -1)
                cv2.line(frame, (20 + int(BLINK_THRESHOLD * 300), y - 2),
                                (20 + int(BLINK_THRESHOLD * 300), y + 12), YELLOW, 2)

                y += 26
                cv2.putText(frame, "SOURIRE", (20, y), FONT, 0.55, WHITE, 1)

                y += 24
                cv2.putText(frame, f"  mouthSmileLeft : {smile_l:.3f}",
                            (20, y), FONT, 0.52,
                            GREEN if smile_l > SMILE_THRESHOLD else GREY, 1)
                y += 22
                cv2.putText(frame, f"  mouthSmileRight: {smile_r:.3f}",
                            (20, y), FONT, 0.52,
                            GREEN if smile_r > SMILE_THRESHOLD else GREY, 1)
                y += 22
                avg_clr = GREEN if is_smiling else RED
                cv2.putText(frame, f"  MOYENNE : {smile:.3f}  (seuil {SMILE_THRESHOLD})",
                            (20, y), FONT, 0.52, avg_clr, 2)
                y += 16
                sw = int(min(smile, 1.0) * 300)
                cv2.rectangle(frame, (20, y), (320, y + 10), GREY, -1)
                cv2.rectangle(frame, (20, y), (20 + sw, y + 10), avg_clr, -1)
                cv2.line(frame, (20 + int(SMILE_THRESHOLD * 300), y - 2),
                                (20 + int(SMILE_THRESHOLD * 300), y + 12), YELLOW, 2)

                y += 26
                if is_blinking:
                    cv2.putText(frame, ">> CLIGNEMENT DETECTE !", (20, y), FONT, 0.65, GREEN, 2)
                elif is_smiling:
                    cv2.putText(frame, ">> SOURIRE DETECTE !", (20, y), FONT, 0.65, GREEN, 2)
                else:
                    cv2.putText(frame, "   Neutre", (20, y), FONT, 0.6, GREY, 1)

            cv2.putText(frame, f"Frames: {frame_count}  |  Q = quitter",
                        (10, frame.shape[0] - 10), FONT, 0.42, GREY, 1)
            cv2.imshow("Debug Liveness Blendshapes", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        raw_file.close()
        cap.release()
        landmarker.close()
        cv2.destroyAllWindows()

        # Sauvegarde fichier événements
        summary = {
            "session_start": session_start,
            "session_end":   ts(),
            "total_frames":  frame_count,
            "thresholds": {
                "blink": BLINK_THRESHOLD,
                "smile": SMILE_THRESHOLD,
            },
            "events": events,
        }
        with open(EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        print(f"\n[DEBUG] Session terminee ({frame_count} frames)")
        print(f"  Valeurs brutes  -> {RAW_FILE}")
        print(f"  Evenements      -> {EVENTS_FILE}")
        print(f"  Total evenements: {len(events)}")


if __name__ == "__main__":
    main()
