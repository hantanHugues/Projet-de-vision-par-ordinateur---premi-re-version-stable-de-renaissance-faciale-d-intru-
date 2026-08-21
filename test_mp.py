"""
Diagnostic MediaPipe — vérifie que la version installée supporte bien
l'API Tasks (PoseLandmarker) utilisée dans pose_analyzer.py.
"""
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

print(f"mediapipe version : {mp.__version__}")
print(f"PoseLandmarker    : {hasattr(vision, 'PoseLandmarker')}")
print(f"PoseLandmarkerOptions : {hasattr(vision, 'PoseLandmarkerOptions')}")
print(f"RunningMode       : {hasattr(vision, 'RunningMode')}")
print("test_mp.py : OK")
