"""
Banc d'essai du Face Gate : coût avant / après le correctif « Haar en double ».

Rejoue la VRAIE route /analyze_frame (décodage JPEG, tracker, identify, Trust Score)
dans deux configurations :
  - AVANT : api.py relançait Haar à chaque image pour chaque personne (encadré de l'UI),
            en plus de celui d'identify() ;
  - APRÈS : l'encadré réutilise la position mémorisée par identify() (get_face_box).

YOLO (détection) et FaceNet512 (embedding) sont remplacés par des doubles de coût nul :
on isole ainsi le coût du Face Gate et du reste de la route, pas celui de l'IA lourde.
Base SQLite temporaire : la vraie base biométrique n'est pas touchée.

    .venv-deepface\\Scripts\\python.exe tests\\bench_face_gate.py --report tests\\rapport_face_gate.md
"""

import argparse
import asyncio
import io
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from datetime import datetime
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import cv2
import numpy as np

import config

config.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="biogate-bench-"), "visages.db")

import api
from starlette.datastructures import UploadFile

PHOTO = os.path.join(ROOT, "tests", "photos_test_apprentissage_continu", "apres1_2019_Chris_Evans_barbe.jpg")
CLIENT_FPS = 5          # cadence réelle du client multithreadé (voir lab_journal)
PACED_FRAMES = 25       # 5 s de flux à 5 images/s
BURST_FRAMES = 40
CANVAS_W, CANVAS_H = 640, 480

fr = api.face_recognizer


class SilentLogger:
    def __getattr__(self, _name):
        return lambda *a, **k: None


class CountingCascade:
    def __init__(self, real):
        self.real = real
        self.calls = 0

    def detectMultiScale(self, *args, **kwargs):
        self.calls += 1
        return self.real.detectMultiScale(*args, **kwargs)


def portrait(max_w, max_h):
    img = cv2.imread(PHOTO)
    h, w = img.shape[:2]
    s = min(max_w / w, max_h / h)
    return cv2.resize(img, (int(w * s), int(h * s)))


def build_scene(n_people):
    """Une image 640x480 avec n_people portraits côte à côte ; retourne (image, [bbox...])."""
    slot = CANVAS_W // n_people
    pic = portrait(min(300, slot - 20), 380)
    canvas = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)
    boxes = []
    for i in range(n_people):
        x, y = i * slot + (slot - pic.shape[1]) // 2, 40
        canvas[y:y + pic.shape[0], x:x + pic.shape[1]] = pic
        boxes.append([x, y, x + pic.shape[1], y + pic.shape[0]])
    return canvas, boxes


def haar_unit_cost_ms(frame, box, repeats=200):
    x1, y1, x2, y2 = box
    gray = cv2.equalizeHist(cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY))
    real = fr.face_cascade.real if isinstance(fr.face_cascade, CountingCascade) else fr.face_cascade
    times = []
    for _ in range(repeats):
        t = time.perf_counter()
        real.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        times.append((time.perf_counter() - t) * 1000)
    return statistics.median(times)


def reset_state():
    fr.tracking_states.clear()
    fr.identified_ids.clear()
    api.tracker = type(api.tracker)()
    for oid in range(10):
        api.trust_mgr.remove(oid)


def run(mode, scenario, n_people, cascade):
    """mode : 'avant' | 'apres' ; scenario : 'identification' | 'stable'. Retourne (ms/image, détections Haar/image)."""
    frame, boxes = build_scene(n_people)
    ok, jpg = cv2.imencode(".jpg", frame)
    payload = jpg.tobytes()
    detections = [{"box": b, "confidence": 0.9} for b in boxes]
    current = {"frame": frame}

    def legacy_get_face_box(object_id, bbox):
        # Réplique fidèle du bloc supprimé d'api.py : Haar relancé sur la silhouette, à chaque image.
        x1, y1, x2, y2 = bbox
        f = current["frame"]
        crop = f[max(0, int(y1)):min(f.shape[0], int(y2)), max(0, int(x1)):min(f.shape[1], int(x2))]
        if crop.size == 0:
            return None
        gray = cv2.equalizeHist(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY))
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        if len(faces) == 0:
            return None
        fx, fy, fw, fh = faces[0]
        return [int(x1) + int(fx), int(y1) + int(fy), int(fw), int(fh)]

    match = (None, 1.0) if scenario == "identification" else ("Hugues", 0.1)
    patches = [
        mock.patch.object(api.yolo, "detect_humans", return_value=detections),
        mock.patch.object(fr, "_extract_face_signature", return_value=np.ones(512, dtype=np.float32)),
        mock.patch.object(fr, "_find_in_memory", return_value=match),
        mock.patch.object(fr, "face_cascade", cascade),
        mock.patch.object(fr, "logger", SilentLogger()),
        mock.patch.object(api, "logger", SilentLogger()),
        mock.patch.object(api.cv2, "imwrite", return_value=True),
        mock.patch.object(fr, "ANALYSIS_TIME_LIMIT", 1e9),
    ]
    if mode == "avant":
        patches.append(mock.patch.object(fr, "get_face_box", legacy_get_face_box))
    for p in patches:
        p.start()
    try:
        reset_state()

        def call():
            upload = UploadFile(file=io.BytesIO(payload), filename="f.jpg")
            t = time.perf_counter()
            asyncio.run(api.analyze_frame(file=upload, liveness_blink=0.0, liveness_smile=0.0))
            return (time.perf_counter() - t) * 1000

        call()  # image d'amorçage : crée le suivi, hors mesure
        if scenario == "stable":
            for oid, state in fr.tracking_states.items():
                state.update(status="FINISHED", final_name="Hugues", last_check_time=time.time())
                fr.identified_ids[oid] = "Hugues"

        frames = PACED_FRAMES if scenario == "stable" else BURST_FRAMES
        cascade.calls = 0
        times = []
        for _ in range(frames):
            times.append(call())
            if scenario == "stable":
                time.sleep(1.0 / CLIENT_FPS)  # cadence réelle du client
        return statistics.mean(times), cascade.calls / frames
    finally:
        for p in reversed(patches):
            p.stop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    cascade = CountingCascade(fr.face_cascade)
    frame, boxes = build_scene(1)
    unit = haar_unit_cost_ms(frame, boxes[0])

    rows = []
    for scenario, label in (("identification", "Identification en cours (chaque image passe par le Face Gate)"),
                            ("stable", f"Personne identifiée, flux à {CLIENT_FPS} images/s (re-vérification toutes les {config.FACE_RECHECK_INTERVAL} s)")):
        for n in (1, 3):
            b_ms, b_calls = run("avant", scenario, n, cascade)
            a_ms, a_calls = run("apres", scenario, n, cascade)
            rows.append((label, n, b_ms, b_calls, a_ms, a_calls))
            print(f"{scenario:15s} {n} pers.  avant {b_ms:6.1f} ms/image {b_calls:4.2f} Haar/image | "
                  f"après {a_ms:6.1f} ms/image {a_calls:4.2f} Haar/image")

    if args.report:
        lines = [
            "# Rapport de mesure — Face Gate (détection Haar en double)",
            "",
            f"*Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}*",
            "",
            "## Méthodologie",
            "",
            "Banc d'essai `tests/bench_face_gate.py` : la vraie route `/analyze_frame` est rejouée "
            "(décodage JPEG, tracker, `identify()`, Trust Score) avec une photo de test, dans deux configurations.",
            "",
            "- **Avant** : `api.py` relançait la détection Haar à chaque image et pour chaque personne (encadré affiché "
            "par le client), en plus de celle d'`identify()`. Le bloc supprimé est rejoué à l'identique.",
            "- **Après** : l'encadré réutilise la position du visage mémorisée par `identify()` "
            "(`FaceRecognizer.get_face_box`) et la replace sur la silhouette courante.",
            "",
            "YOLO et FaceNet512 sont remplacés par des doubles de coût nul : la mesure isole le Face Gate et le reste de la "
            "route, pas l'IA lourde. Un seul appel Haar coûte, sur ce matériel, "
            f"**{unit:.2f} ms** en médiane (silhouette de {boxes[0][2] - boxes[0][0]}×{boxes[0][3] - boxes[0][1]} px).",
            "",
            "## Matériel",
            "",
            f"- Processeur : {platform.processor() or platform.machine()}",
            f"- Système : {platform.platform()}",
            f"- Python {platform.python_version()}, OpenCV {cv2.__version__}",
            "",
            "## Résultats",
            "",
            "| Situation | Personnes | Avant (ms/image) | Avant (Haar/image) | Après (ms/image) | Après (Haar/image) | Gain de temps |",
            "|---|---|---|---|---|---|---|",
        ]
        for label, n, b_ms, b_calls, a_ms, a_calls in rows:
            gain = (1 - a_ms / b_ms) * 100 if b_ms else 0.0
            lines.append(f"| {label} | {n} | {b_ms:.1f} | {b_calls:.2f} | {a_ms:.1f} | {a_calls:.2f} | {gain:+.0f} % |")
        lines += [
            "",
            "## Lecture",
            "",
            "Pendant l'identification, la détection d'`identify()` est indispensable (c'est le Face Gate de sécurité) : "
            "le correctif supprime seulement le doublon, soit un appel sur deux. Une fois la personne identifiée, "
            "`identify()` ne relance le Face Gate qu'à chaque re-vérification ; avant le correctif, l'encadré de l'interface "
            "continuait à déclencher une détection par image et par personne.",
            "",
            "Limites : mesure sur une seule photo et un seul processeur ; le gain absolu dépend de la taille des silhouettes "
            "et du nombre de personnes. Le gain relatif en nombre d'appels, lui, vient de la structure du code.",
            "",
            "## Reproductibilité",
            "",
            "```",
            r".venv-deepface\Scripts\python.exe tests\bench_face_gate.py --report tests\rapport_face_gate.md",
            "```",
        ]
        with open(args.report, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Rapport écrit : {args.report}")


if __name__ == "__main__":
    main()
