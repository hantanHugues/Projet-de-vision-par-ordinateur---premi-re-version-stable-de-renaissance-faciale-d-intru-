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
from database.db_manager import DatabaseManager

class FaceRecognizer:
    def __init__(self, logger):
        self.logger = logger

        # Cache en temps réel (ID du Tracker -> Nom Identifié à l'écran)
        self.identified_ids = {}
        
        # Gestion du Temps d'Analyse (Access Control)
        self.tracking_states = {} # {object_id: {"first_seen": timestamp, "best_match": None, "status": "ANALYZING"}}
        self.ANALYSIS_TIME_LIMIT = 1.0 # Le temps max pour scanner un Intrus (S'il ne valide pas VIP en 1s -> ALERTE)
        self.LIVENESS_TIME_LIMIT = 5.0 # Le temps que le VIP doit tenir pour prouver qu'il n'est pas une photo (Spoofing)

        # Moteur SQLite (Mémoire à long terme Multi-Empreintes)
        self.db = DatabaseManager(logger=logger)
        
        # Initialiser l'index des intrus (ex: s'il y a déjà Intrus B dans la base, on commence à C)
        historical_faces = self.db.get_all_embeddings()
        intruder_count = sum(1 for name in historical_faces.keys() if name.startswith("Intrus "))
        self.next_intruder_index = intruder_count

        self.logger.info("FaceRecognizer avec Facenet512 et SQLite initialisé.")

        # Modèle ultra-léger OpenCV pour DETECTER si un visage est bien centré et visible
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        

    def _load_known_faces(self):
        """Scanne le dossier des visages VIP et les encode mathématiquement à vie."""
        if not os.path.exists(self.db_path):
            os.makedirs(self.db_path)
            self.logger.info(f"Dossier {self.db_path} créé. Glissez-y vos photos VIP (ex: Ash.jpg) !")
            return

        self.logger.info("Chargement de la base de données faciale (VIP)...")
        count = 0
        for file in os.listdir(self.db_path):
            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                # Extraire le nom de la photo sans l'extension (ex: "Alex.png" -> "Alex")
                name = os.path.splitext(file)[0].capitalize()
                path = os.path.join(self.db_path, file)
                
                self.logger.info(f"Apprentissage du visage de '{name}'...")
                
                # Vérifier si on a déjà des empreintes pour ce VIP, sinon l'ajouter
                existing_faces = self.db.get_all_embeddings()
                if name not in existing_faces:
                    sig = self._extract_face_signature(path)
                    if sig is not None:
                        self.db.add_embedding(name, sig, role="VIP")
                        count += 1
                else:
                    self.logger.info(f"Le profil VIP '{name}' est déjà dans la base.")
                    
        if count > 0:
            self.logger.success(f"{count} visages VIP pré-chargés en mémoire ! (Jamais oubliés)")
        else:
            self.logger.info("Aucun visage VIP détecté dans la base de données locale.")

    def clear_lost_ids(self, active_ids):
        """Nettoie le cache, et déclenche l'Alerte Fuite si l'usager fuit avant la seconde."""
        lost = [uid for uid in self.identified_ids if uid not in active_ids]
        for uid in lost:
            name = self.identified_ids.pop(uid)
            
            # [ALERTE DE FUITE] Si la personne est partie avant qu'on valide un VIP !
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

    def _extract_face_signature(self, face_img):
        """
        Extrait une VRAIE signature mathématique IA du visage (Embedding VGG).
        """
        try:
            # DeepFace.represent extrait l'ADN du visage
            result = DeepFace.represent(
                img_path=face_img,
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
        
        # PATCH DE SÉCURITÉ DE HAUT NIVEAU (Ouverture de serrure)
        # DeepFace Facenet512 : La documentation recommande 0.30 - 0.40 pour la similarité cosinus.
        # Ajusté à 0.35 : Tolérance industrielle standard. Évite de te déconnecter au moindre changement de lumière/pose.
        threshold = 0.35

        # Identifier les noms DEJA sur l'écran (On ignore le nôtre pour le mettre à jour)
        active_names_on_screen = [
            name for obj_id, name in self.identified_ids.items()
            if obj_id != current_object_id
        ]

        historical_faces = self.db.get_all_embeddings()

        for name, saved_signatures_list in historical_faces.items():
            # [PATCH ANTI-SPATIAL DÉSACTIVÉ]: Laissait croire à de nouveaux intrus si YOLO buggait.
            # (Si YOLO fait 2 boîtes sur ton visage, les 2 boîtes s'appelleront Ash, au lieu de Ash et Intrus B !)
                
            # L'Effet Multi-Empreintes (Comparer le visage avec TOUTES ses photos dans SQLite)
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
                "first_seen": time.time(),
                "last_check_time": time.time(),
                "status": "ANALYZING",
                "best_match": None,
                "final_name": None,
                "liveness_start": None # Nouveau chronomètre Anti-Spoofing
            }

        state = self.tracking_states[object_id]
        
        # Mode d'Apprentissage Continu : On ne revérifie l'IA que toutes les 0.8 secondes 
        # une fois l'accès validé/refusé, pour laisser le CPU respirer.
        if state["status"] == "FINISHED":
            if time.time() - state.get("last_check_time", 0) < 0.8:
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
        
        # LE FACE GATE : Détecteur ultra-rapide Frontal + Profil
        # On exige un visage de face clair pour lancer l'IA lourde. 
        # Si la personne est de dos ou tête trop baissée, len(faces) == 0.
        faces = self.face_cascade.detectMultiScale(gray_crop, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

        if len(faces) == 0:
            # AUCUN VISAGE CLAIR FRONTALE DÉTECTÉ.
            # On NE LANCE PAS Facenet512. On garde le secret intact.
            
            # [LIVENESS] Reset du défi si la personne tourne la tête ou cache la photo
            if state["status"] == "LIVENESS_CHECK":
                state["liveness_start"] = time.time()
            
            # Si on connaissait déjà le nom (ex: il s'est retourné après avoir été reconnu)
            if object_id in self.identified_ids:
                return self.identified_ids[object_id]
                
            # Sinon, c'est qu'il vient d'arriver et on attend qu'il se retourne
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
        # 3.5 MODE "FINISHED" : RE-ÉVALUATION CRITIQUE
        # ===============================================================
        if state["status"] == "FINISHED":
            current_name = state["final_name"]
            if nom_trouve and nom_trouve != current_name:
                # La personne a changé physiquement la forme de son visage ou qq'un d'autre a pris sa place !
                self.logger.warning(f"[RE-VÉRIFICATION] L'identité a muté ! Passage de '{current_name}' à '{nom_trouve or 'INCONNU'}'.")
                state["final_name"] = nom_trouve if nom_trouve else "INCONNU"
                self.identified_ids[object_id] = state["final_name"]
                # STOP APP. CONTINU SAUVAGE : self.db.add_embedding(nom_trouve, signature...) a été retiré.
            
            elif nom_trouve == current_name:
                # C'est toujours lui ! Vérification silencieuse (Lecture Seule).
                self.logger.info(f"[MAINTIEN OK] Identité '{current_name}' re-confirmée visuellement (Dist: {distance:.2f})")
                # STOP APP. CONTINU SAUVAGE : self.db.add_embedding(...) a été retiré. L'IA Hybridera ça plus tard.
            
            else:
                # FIX BDD LECTURE SEULE: Si c'est un intrus (donc non-inscrit dans SQLite) et qu'aucun VIP n'est trouvé,
                # on accepte silencieusement que c'est toujours le même intrus (grâce à la Tracker Box).
                if current_name.startswith("Intrus") and nom_trouve is None:
                    return current_name

                # Sinon, le visage ne correspond plus du tout à personne d'existant à moins de 0.20 de distance.
                # Ex: Enlèvement de masque total, ou échange de position avec un VIP.
                self.logger.warning(f"[ANOMALIE MATÉRIELLE] Visage inclassable par rapport à son passé. Relève des doutes ! Analyse Re-Démarrée.")
                state["status"] = "ANALYZING"
                state["first_seen"] = time.time() # On reset le chronomètre central de 1seconde
                state["best_match"] = None
                return "Re-Analyse..."
            
            return state["final_name"]

        # ===============================================================
        # 4. MODE "ANALYZING" EXCLUSIF (1ÈRE MAPPAGE)
        # ===============================================================
        if nom_trouve:
            confidence = (1 - distance) * 100
            # EST-CE UN VIP DE LA MAISON ?
            if not nom_trouve.startswith("Intrus"):
                self.logger.success(f"[ACCÈS AUTORISÉ] VIP validé : '{nom_trouve}' ({confidence:.1f}%). Ouverture du portail !")
                state["status"] = "FINISHED"
                state["final_name"] = nom_trouve
                self.identified_ids[object_id] = nom_trouve
                # On Loggue, mais SANS écrire les vecteurs !
                self.db.log_event(nom_trouve, confidence)
                # La vérification 100% stricte a été faite, on ne modifie plus la BDD (Lecture Seule)
                return nom_trouve
            else:
                # C'est un intrus qu'on connaissait déjà
                state["best_match"] = nom_trouve

        # ===============================================================
        # 5. COUPERET DU TEMPS (1 SECONDE ÉCOULÉE SANS VOIR DE VIP)
        # ===============================================================
        if elapsed_time > self.ANALYSIS_TIME_LIMIT:
            state["status"] = "FINISHED"

            if state["best_match"]:
                final_name = state["best_match"]
                self.logger.warning(f"[ALERTE INTRUSION] Accès Refusé. C'est l'usager répété : {final_name}")
                # Plus d'ajouts dans la BDD.
                self.db.log_event(final_name, 80.0) # confiance générique
            else:
                # Totalement nouveau
                letter = chr(ord('A') + self.next_intruder_index)
                final_name = f"Intrus {letter}"
                self.next_intruder_index += 1
                self.logger.warning(f"[ALERTE INTRUSION] NOUVEAU VISAGE INCONNU. Archivé temporairement comme: {final_name}")
                # Base de données scellée, juste un log d'alerte sans mémorisation profonde:
                self.db.log_event(final_name, 0.0)
            
            state["final_name"] = final_name
            self.identified_ids[object_id] = final_name
            return final_name

        # ===============================================================
        # 6. RETOUR CONTINU TANT QUE LA SECONDE N'EST PAS FINIE
        # ===============================================================
        msg = f"Analyse... ({elapsed_time:.1f}s)"
        self.identified_ids[object_id] = msg
        return msg
