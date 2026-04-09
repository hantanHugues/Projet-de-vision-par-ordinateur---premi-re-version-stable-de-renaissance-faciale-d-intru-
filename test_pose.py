class L:
    def info(self, m): print('[I]', m)
    def success(self, m): print('[S]', m)
    def error(self, m): print('[E]', m)
from core.pose_analyzer import PoseAnalyzer
import numpy as np
p = PoseAnalyzer(L())
frame = np.zeros((480, 640, 3), dtype=np.uint8)
out, res = p.analyze_and_draw(frame)
print('READY:', p.is_ready)
print('RESULT:', res)
