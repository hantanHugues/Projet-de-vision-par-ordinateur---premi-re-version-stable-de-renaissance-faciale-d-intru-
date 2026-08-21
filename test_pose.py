"""
Diagnostic PoseAnalyzer — vérifie que le module s'initialise et que
analyze_and_draw() retourne bien le tuple attendu (frame, has_skeleton, is_3d_real, msg).
"""
import numpy as np
from core.logger import VisualLogger
from core.pose_analyzer import PoseAnalyzer

logger = VisualLogger()
p = PoseAnalyzer(logger)

print(f"PoseAnalyzer ready: {p.is_ready}")

frame = np.zeros((480, 640, 3), dtype=np.uint8)
result = p.analyze_and_draw(frame)

assert len(result) == 4, f"analyze_and_draw doit retourner 4 valeurs, reçu {len(result)}"
frame_out, has_skeleton, is_3d_real, msg = result

print(f"has_skeleton : {has_skeleton}")
print(f"is_3d_real   : {is_3d_real}")
print(f"msg          : {msg}")
print("test_pose.py : OK")
