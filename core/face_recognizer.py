"""
Reconnaissance Faciale — Phase 5

S'appuie sur les IDs générés par le tracker (CentroidTracker).
Objectif : Ne faire l'analyse lourde du visage qu'UNE SEULE FOIS par ID.
Si l'ID 1 est reconnu comme "Ash" à la frame T, alors à la frame T+n, 
et tant que l'ID 1 est présent, le système sait que c'est "Ash" sans recalculer. 
C'est indispensable pour ne pas surcharger le Raspberry Pi.
"""

import os
import cv2
import time
import numpy as np
from deepface import DeepFace
import config
from database.db_manager import DatabaseManager

class FaceRecognizer:
    def __init__(self, logger, trust_mgr=None):
        self.logger    = logger
        self.trust_mgr = trust_mgr  # TrustScoreManager — optionnel, injecté par api.py

        # Cache en temps réel (ID du Tracker -> Nom Identifié à l'écran)
        self.identified_ids = {}

        # Gestion du Temps d'Analyse (Access Control) — valeurs depuis config.py
        self.tracking_states = {}
        self.ANALYSIS_TIME_LIMIT = config.FACE_ANALYSIS_TIME_LIMIT
        self.RECHECK_INTERVAL    = config.FACE_RECHECK_INTERVAL

        # Moteur SQLite (Mémoire à long terme Multi-Empreintes)
        self.db = DatabaseManager(logger=logger)

        # Cache RAM : chargé UNE SEULE FOIS au démarrage, jamais relu sauf sur /enroll
        # Évite d'ouvrir SQLite + SELECT * + json.loads à chaque frame analysée
        self._embeddings_cache = self.db.get_all_embeddings()
        self.logger.info(f"[DEBUG CACHE] Cache biométrique initialisé : {len(self._embeddings_cache)} profil(s) chargé(s) en RAM.")

        # Ground Truth Learning — embedding mis en attente pendant FINGERPRINT_PENDING
        # Sauvegardé en DB uniquement quand l'empreinte confirme (certitude matérielle absolue)
        self._pending_embeddings = {}   # {object_id: np.array embedding}

        # Initialiser l'index des intrus depuis le cache (pas besoin de réouvrir SQLite)
        intruder_count = sum(1 for name in self._embeddings_cache.keys() if name.startswith("Intrus"))
        self.next_intruder_index = intruder_count

        self.logger.info("FaceRecognizer avec Facenet512 et SQLite initialisé.")

        # Modèle ultra-léger OpenCV pour DETECTER si un visage est bien centré et visible
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml') 

        # --- PIPELINE INDUSTRIEL DE PRÉ-TRAITEMENT ---
        # Initialisation du nettoyeur de contraste local (Évite de le recréer à chaque image)
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        self.logger.info("Pipeline CLAHE (Contrast-Limiting) initialisé pour corriger les contre-jours.")

    def clear_lost_ids(self, active_ids):
        """Nettoie le cache, et déclenche l'Alerte Fuite si l'usager fuit avant la seconde."""
        lost = [uid for uid in self.identified_ids if uid not in active_ids]
        for uid in lost:
            name = self.identified_ids.pop(uid)

            if uid in self.tracking_states and self.tracking_states[uid]["status"] == "ANALYZING":
                self.logger.error(f"[ALERTE FUITE !] L'individu a fui la caméra avant la fin de l'analyse (1 sec) !")

            self.logger.info(f"Oubli du tracking ID {uid}. La signature reste vivante en mémoire.")

            if uid in self.tracking_states:
                del self.tracking_states[uid]

        # Purger également tracking_states pour d'éventuels IDs disparus
        lost_tracking = [uid for uid in self.tracking_states if uid not in active_ids]
        for uid in lost_tracking:
            if self.tracking_states[uid]["status"] == "ANALYZING":
                self.logger.error(f"[ALERTE FUITE !] Un individu furtif (non-identifié) a disparu de l'écran !")
            del self.tracking_states[uid]

        # Nettoyer les embeddings en attente pour les IDs disparus
        for uid in list(self._pending_embeddings.keys()):
            if uid not in active_ids:
                del self._pending_embeddings[uid]

        # Nettoie aussi les TrustScores associés
        if self.trust_mgr:
            self.trust_mgr.remove_lost(active_ids)

    def reload_cache(self):
        """Recharge le cache RAM depuis SQLite. À appeler uniquement après un /enroll réussi."""
        self._embeddings_cache = self.db.get_all_embeddings()
        intruder_count = sum(1 for name in self._embeddings_cache.keys() if name.startswith("Intrus"))
        self.next_intruder_index = intruder_count
        self.logger.info(f"[DEBUG CACHE] Cache rechargé : {len(self._embeddings_cache)} profil(s) en RAM.")

    def learn_from_confirmation(self, object_id, vip_name):
        """
        Ground Truth Learning — appelé quand l'empreinte digitale confirme l'identité.
        Sauvegarde l'embedding du visage actuel comme nouvel échantillon pour ce VIP.
        Améliore la reconnaissance future (casquette, barbe, lunettes, éclairage différent).
        """
        embedding = self._pending_embeddings.pop(object_id, None)
        if embedding is None:
            self.logger.warning(f"[GROUND TRUTH] Pas d'embedding en attente pour ID={object_id}.")
            return False
        self.db.add_embedding(vip_name, embedding, role="VIP")
        self.reload_cache()
        self.logger.success(f"[GROUND TRUTH] Nouvel échantillon appris pour '{vip_name}' — "
                            f"{len(self._embeddings_cache.get(vip_name, []))} embedding(s) total.")
        return True

    def _apply_clahe_bgr(self, face_bgr):
        """Applique le filtre LAB-CLAHE pour déboucher les ombres sur un visage BGR."""
        lab = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        cl = self.clahe.apply(l)
        limg = cv2.merge((cl, a, b))
        return cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

    def _extract_face_signature(self, face_img):
        """
        Extrait une signature mathématique du visage (Embedding FaceNet512).
        """
        try:
            # PRE-PROCESSING: Filtre CLAHE pour parfaire le visage avant de le donner à l'IA Mathématique
            face_img_clean = self._apply_clahe_bgr(face_img)

            # DeepFace.represent extrait l'ADN du visage
            result = DeepFace.represent(
                img_path=face_img_clean,
                model_name="Facenet512", # CHANGEMENT DE CERVEAU: Beaucoup plus robuste que VGG-Face pour les webcams.
                enforce_detection=False, # On gère déjà la détection cascade
                align=True,              # ALIGNEMENT : Redresse le nez/yeux (Crucial pour la précision géométrique)
                detector_backend="opencv" # OPENCV : Ultra-léger en CPU, garantit la survie du Raspberry Pi
            )
            if len(result) > 0:
                # Retourne un vecteur Numpy (ex: 4096 ou 512 nombres)
                return np.array(result[0]["embedding"], dtype=np.float32)
        except Exception as e:
            self.logger.error(f"Erreur d'extraction IA: {e}")
        return None

    def _find_in_memory(self, new_signature, current_object_id):
        """Interroge SQLite pour le meilleur Match (Anti-Superposition Spatiale)"""
        best_match = None
        min_dist = float('inf')
        
        threshold = config.FACE_RECOGNITION_THRESHOLD

        # Lecture du cache RAM (instantané, pas d'I/O disque)
        historical_faces = self._embeddings_cache

        for name, saved_signatures_list in historical_faces.items():
            # Multi-embeddings : distance min sur toutes les photos enregistrées
            for saved_signature in saved_signatures_list:
                dist = 1 - np.dot(saved_signature, new_signature) / (np.linalg.norm(saved_signature) * np.linalg.norm(new_signature))
                if dist < min_dist:
                    min_dist = dist
                    best_match = name

        if best_match and min_dist < threshold:
            return best_match, min_dist
        return None, min_dist

    def identify(self, frame, bbox, object_id):
        """
        Protocole Temporisé avec Apprentissage Continu et Tolérance aux Changements d'Identité.
        """
        # ===============================================================
        # 1. MACHINE À ÉTATS TEMPORELLE
        # ===============================================================
        if object_id not in self.tracking_states:
            self.tracking_states[object_id] = {
                "first_seen":        time.time(),
                "last_check_time":   time.time(),
                "status":            "ANALYZING",
                "best_match":        None,
                "final_name":        None,
                "recheck_fail_count": 0,   # hysterèse : nb d'échecs RECHECK consécutifs
            }
            if self.trust_mgr:
                self.trust_mgr.get_or_create(object_id).start_analyzing()

        state = self.tracking_states[object_id]
        
        # Re-vérification périodique : laisser le CPU respirer entre deux analyses
        if state["status"] == "FINISHED":
            if time.time() - state.get("last_check_time", 0) < self.RECHECK_INTERVAL:
                return self.identified_ids.get(object_id, state["final_name"])
            state["last_check_time"] = time.time()

        # Sinon, l'usager est en "Salle d'Attente Visuelle" ou c'est l'heure d'un re-check periodic.
        elapsed_time = time.time() - state["first_seen"]

        # ===============================================================
        # 2. CAPTURE DE FRAME POUR L'ANALYSE EN COURS (FILTRE MÉTÉO / FACE GATE)
        # ===============================================================
        x1, y1, x2, y2 = bbox
        h_img, w_img = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w_img, x2), min(h_img, y2)
        crop = frame[y1:y2, x1:x2]

        if crop.size == 0:
            return self.identified_ids.get(object_id, f"Attente visage... ({elapsed_time:.1f}s)")

        gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        # PRE-PROCESSING RAPIDE : Booster OpenCV en forçant le contraste des Niveaux de Gris
        gray_crop = cv2.equalizeHist(gray_crop)

        # LE FACE GATE : Détecteur ultra-rapide Frontal + Profil
        # On exige un visage de face clair pour lancer l'IA lourde. 
        # Si la personne est de dos ou tête trop baissée, len(faces) == 0.
        faces = self.face_cascade.detectMultiScale(gray_crop, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

        if len(faces) == 0:
            # AUCUN VISAGE CLAIR FRONTALE DÉTECTÉ.
            # On NE LANCE PAS Facenet512. On garde le secret intact.

            # Si on connaissait déjà le nom (ex: il s'est retourné après avoir été reconnu)
            if object_id in self.identified_ids:
                return self.identified_ids[object_id]

            # COUPERET ANTI-BLOCAGE : si la personne refuse de montrer son visage pendant
            # toute la fenêtre d'analyse, elle est automatiquement classée intrus.
            # Sans ce check, "Attente visage..." durerait à l'infini (le timeout ligne 272 est
            # inatteignable si on n'a jamais de face).
            if elapsed_time > self.ANALYSIS_TIME_LIMIT:
                state["status"] = "FINISHED"
                self.next_intruder_index += 1
                final_name = f"Intrus_{self.next_intruder_index:03d}"
                self.logger.warning(
                    f"[ALERTE] Individu non-identifiable (visage absent après {elapsed_time:.1f}s) → {final_name}"
                )
                self.db.log_event(
                    final_name, 0.0,
                    event_type=self.db.EVENT_INTRUDER_PENDING
                )
                state["final_name"] = final_name
                self.identified_ids[object_id] = final_name
                if self.trust_mgr:
                    self.trust_mgr.get_or_create(object_id).intruder_detected()
                return final_name

            # Sinon, on attend qu'il se retourne (dans la fenêtre de 1 seconde)
            return f"Attente visage... ({elapsed_time:.1f}s)"

        (fx, fy, fw, fh) = faces[0]
        face_roi = crop[fy:fy+fh, fx:fx+fw]

        # Calculer une photo IA
        signature = self._extract_face_signature(face_roi)
        if signature is None:
             return self.identified_ids.get(object_id, f"Attente visage... ({elapsed_time:.1f}s)")

        # ===============================================================
        # 3. INTERROGER LA MÉMOIRE NEURONALE (SQLite) EN LECTURE SEULE
        # ===============================================================
        nom_trouve, distance = self._find_in_memory(signature, object_id)

        # ===============================================================
        # 3.5 MODE "FINISHED" : RE-ÉVALUATION CRITIQUE (avec hysterèse)
        # ===============================================================
        if state["status"] == "FINISHED":
            current_name   = state["final_name"]
            tolerance      = config.RECHECK_FAILURE_TOLERANCE

            if nom_trouve == current_name:
                # Identité confirmée → on remet le compteur d'échecs à zéro
                state["recheck_fail_count"] = 0
                confidence_live = (1 - distance) * 100
                self.logger.info(f"[MAINTIEN OK] Identité '{current_name}' re-confirmée (Dist: {distance:.2f} | {confidence_live:.1f}%)")
                # Mise à jour du score en direct — le chiffre varie selon l'angle, la lumière, etc.
                if self.trust_mgr:
                    ts_obj = self.trust_mgr.get(object_id)
                    if ts_obj:
                        ts_obj.update_score(confidence_live)
                        # Ground Truth : mémoriser l'embedding actuel pendant FINGERPRINT_PENDING
                        # Il sera sauvegardé en DB uniquement si l'empreinte confirme
                        if ts_obj.get_state().get("state") == "FINGERPRINT_PENDING":
                            self._pending_embeddings[object_id] = signature

            elif nom_trouve and nom_trouve != current_name:
                # Discordance → hysterèse avant de déclencher une transition
                state["recheck_fail_count"] += 1
                self.logger.warning(
                    f"[RE-CHECK] Discordance {state['recheck_fail_count']}/{tolerance} "
                    f"'{current_name}' → '{nom_trouve}'"
                )
                if state["recheck_fail_count"] >= tolerance:
                    self.logger.warning(
                        f"[RE-VÉRIFICATION] Tolérance dépassée — passage de '{current_name}' à '{nom_trouve}'."
                    )
                    state["final_name"]        = nom_trouve
                    state["recheck_fail_count"] = 0
                    self.identified_ids[object_id] = nom_trouve

                    # Intrus → VIP : annuler immédiatement la fenêtre de grâce
                    if not nom_trouve.startswith("Intrus") and self.trust_mgr:
                        ts_obj = self.trust_mgr.get(object_id)
                        if ts_obj and ts_obj.cancel_intruder_alert():
                            self.logger.info(
                                f"[GRÂCE ANNULÉE] Alerte provisoire annulée — "
                                f"'{current_name}' reclassifié VIP '{nom_trouve}'."
                            )
                        self.trust_mgr.cancel_intruder_if_vip_nearby()
                        self.trust_mgr.get_or_create(object_id).face_matched(
                            nom_trouve, (1 - distance) * 100
                        )

            else:
                # Intrus confirmé dont le visage n'est plus reconnu → on l'accepte silencieusement
                if current_name.startswith("Intrus") and nom_trouve is None:
                    return current_name

                # Anomalie : visage sans correspondance sur un profil VIP
                state["recheck_fail_count"] += 1
                if state["recheck_fail_count"] >= tolerance:
                    self.logger.warning(
                        f"[ANOMALIE] Visage inclassable après {tolerance} RECHECK — re-analyse forcée."
                    )
                    state["status"]            = "ANALYZING"
                    state["first_seen"]        = time.time()
                    state["best_match"]        = None
                    state["recheck_fail_count"] = 0
                    return "Re-Analyse..."

            return state["final_name"]

        # ===============================================================
        # 4. MODE "ANALYZING" EXCLUSIF (1ÈRE MAPPAGE)
        # ===============================================================
        if nom_trouve:
            confidence = (1 - distance) * 100
            # EST-CE UN VIP DE LA MAISON ?
            if not nom_trouve.startswith("Intrus"):
                self.logger.success(
                    f"[ACCÈS AUTORISÉ] VIP validé : '{nom_trouve}' ({confidence:.1f}%). Ouverture du portail !"
                )
                state["status"]    = "FINISHED"
                state["final_name"] = nom_trouve
                self.identified_ids[object_id] = nom_trouve

                self.db.log_event(
                    nom_trouve, confidence,
                    event_type=self.db.EVENT_VIP_ENTRY, role="VIP"
                )

                # Notifier le moteur MFA et annuler les alertes d'intrus en cours
                if self.trust_mgr:
                    self.trust_mgr.get_or_create(object_id).face_matched(nom_trouve, confidence)
                    self.trust_mgr.cancel_intruder_if_vip_nearby()

                return nom_trouve
            else:
                # Intrus déjà connu
                state["best_match"] = nom_trouve

        # ===============================================================
        # 5. COUPERET DU TEMPS (1 SECONDE ÉCOULÉE SANS VOIR DE VIP)
        # ===============================================================
        if elapsed_time > self.ANALYSIS_TIME_LIMIT:
            state["status"] = "FINISHED"

            if state["best_match"]:
                final_name = state["best_match"]
                self.logger.warning(f"[ALERTE INTRUSION] Accès Refusé. Individu récidiviste : {final_name}")
                self.db.log_event(
                    final_name, 80.0,
                    event_type=self.db.EVENT_INTRUDER_PENDING
                )
            else:
                self.next_intruder_index += 1
                final_name = f"Intrus_{self.next_intruder_index:03d}"
                self.logger.warning(f"[ALERTE INTRUSION] NOUVEAU VISAGE INCONNU → {final_name}")
                self.db.log_event(
                    final_name, 0.0,
                    event_type=self.db.EVENT_INTRUDER_PENDING
                )

            state["final_name"] = final_name
            self.identified_ids[object_id] = final_name

            # Démarre la fenêtre de grâce (alerte différée)
            if self.trust_mgr:
                self.trust_mgr.get_or_create(object_id).intruder_detected()

            return final_name

        # ===============================================================
        # 6. RETOUR CONTINU TANT QUE LA SECONDE N'EST PAS FINIE
        # ===============================================================
        msg = f"Analyse... ({elapsed_time:.1f}s)"
        self.identified_ids[object_id] = msg
        return msg
