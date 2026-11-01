"""
Tests du réglage LIVENESS_ENABLED (interrupteur « vivacité activée » du tableau de bord).

Défaut corrigé : les deux pipelines de api.py lançaient le défi de vivacité pendant l'attente
du second facteur sans lire ce réglage (seule la demande manuelle request_liveness() le lisait).
L'interrupteur et le profil « haute sécurité » (qui le désactive) n'avaient donc aucun effet.

La règle est maintenant dans core.trust_score.liveness_channel_active(). Ces tests n'ont besoin
que de la bibliothèque standard et de config.py : ni OpenCV, ni DeepFace, ni FastAPI.

    python -m unittest tests.test_liveness_toggle -v
"""

import os
import re
import unittest

import config
from core.trust_score import (
    TrustScore, liveness_channel_active,
    STATE_ANALYZING, STATE_FINGERPRINT_PENDING, STATE_LIVENESS_PENDING,
    STATE_GRANTED, STATE_DENIED, STATE_INTRUDER_PENDING,
)

API_SOURCE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api.py")


class LivenessToggleTests(unittest.TestCase):
    def setUp(self):
        self._saved = {k: getattr(config, k) for k in ("LIVENESS_ENABLED", "MFA_REQUIRED")}

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(config, k, v)

    def test_active_in_second_factor_states_when_enabled(self):
        config.LIVENESS_ENABLED = True
        self.assertTrue(liveness_channel_active(STATE_FINGERPRINT_PENDING))
        self.assertTrue(liveness_channel_active(STATE_LIVENESS_PENDING))

    def test_never_active_outside_second_factor_states(self):
        config.LIVENESS_ENABLED = True
        for state in (STATE_ANALYZING, STATE_GRANTED, STATE_DENIED, STATE_INTRUDER_PENDING):
            self.assertFalse(liveness_channel_active(state), state)

    def test_disabled_means_never_active(self):
        config.LIVENESS_ENABLED = False
        for state in (STATE_FINGERPRINT_PENDING, STATE_LIVENESS_PENDING, STATE_ANALYZING):
            self.assertFalse(liveness_channel_active(state), state)

    def test_change_takes_effect_without_restart(self):
        config.LIVENESS_ENABLED = True
        self.assertTrue(liveness_channel_active(STATE_FINGERPRINT_PENDING))
        config.LIVENESS_ENABLED = False
        self.assertFalse(liveness_channel_active(STATE_FINGERPRINT_PENDING))

    def test_fingerprint_alone_still_grants_when_liveness_disabled(self):
        config.MFA_REQUIRED = True
        config.LIVENESS_ENABLED = False
        ts = TrustScore("t1")
        ts.start_analyzing()
        ts.face_matched("Ash", 80.0)
        self.assertEqual(ts.get_state()["state"], STATE_FINGERPRINT_PENDING)
        self.assertFalse(liveness_channel_active(ts.get_state()["state"]))
        ts.fingerprint_confirmed()
        self.assertEqual(ts.get_state()["state"], STATE_GRANTED)
        self.assertEqual(ts.get_state()["score"], config.TRUST_FINGERPRINT_THRESHOLD)

    def test_liveness_path_unchanged_when_enabled(self):
        config.MFA_REQUIRED = True
        config.LIVENESS_ENABLED = True
        ts = TrustScore("t2")
        ts.start_analyzing()
        ts.face_matched("Ash", 80.0)
        self.assertTrue(liveness_channel_active(ts.get_state()["state"]))
        ts.liveness_success()
        self.assertEqual(ts.get_state()["state"], STATE_GRANTED)
        self.assertEqual(ts.get_state()["score"], config.TRUST_LIVENESS_THRESHOLD)

    def test_manual_request_ignored_when_disabled(self):
        config.MFA_REQUIRED = True
        config.LIVENESS_ENABLED = False
        ts = TrustScore("t3")
        ts.start_analyzing()
        ts.face_matched("Ash", 80.0)
        ts.request_liveness()
        self.assertEqual(ts.get_state()["state"], STATE_FINGERPRINT_PENDING)

    def test_both_pipelines_in_api_use_the_rule(self):
        """Garde contre une régression : les deux appels doivent passer par la règle commune."""
        with open(API_SOURCE, encoding="utf-8") as f:
            source = f.read()
        self.assertEqual(len(re.findall(r"if liveness_channel_active\(current_state\):", source)), 2)
        self.assertNotIn("if current_state in (STATE_FINGERPRINT_PENDING, STATE_LIVENESS_PENDING):", source)


if __name__ == "__main__":
    unittest.main()
