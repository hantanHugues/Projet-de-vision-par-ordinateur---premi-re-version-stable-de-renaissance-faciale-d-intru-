"""
Centroid Tracker — Suivi d'objets (Tracking).

Phase 4 : Assigne un ID unique à chaque détection humaine.
Basé sur la distance Euclidienne entre les centres des boîtes au fil du temps.
Extrêmement léger et adapté au traitement Edge (Raspberry Pi).
"""

import numpy as np
import cv2
from collections import OrderedDict

class CentroidTracker:
    def __init__(self, max_disappeared=60, max_distance=150):
        """
        Initialise le tracker corporel avec une longue mémoire et une limite de distance.
        
        Args:
            max_disappeared: (60 frames = 2 secondes à 30fps) Le temps de mémorisation fantôme si caché.
            max_distance: (150 pixels) Distance MAX en pixels. Si un corps sort de derrière le tableau 
                          mais qu'il apparaît trop loin de là où on a perdu l'ancien ID,
                          c'est forcément une NOUVELLE personne (ID X+1).
        """
        self.next_object_id = 1
        self.objects = OrderedDict()
        self.bboxes = OrderedDict() 
        self.signatures = OrderedDict() # NOUVEAU: Histogramme de l'apparence des vêtements
        self.disappeared = OrderedDict()
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance # NOUVEAU: Le verrou spatial Anti-Téléportation

    def _compute_color_histogram(self, frame, bbox):
        """
        Calcule la signature vestimentaire (Histogramme de couleurs) de la zone détectée.
        Extrêmement léger (environ 0.001s).
        """
        x1, y1, x2, y2 = bbox
        # Recadrer le corps
        crop = frame[max(0, y1):min(frame.shape[0], y2), max(0, x1):min(frame.shape[1], x2)]
        if crop.size == 0:
            return None
            
        # Conversion en espace HSV (Très robuste aux variations de lumière)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        
        # Ignorer le fond (les pixels trop sombres ou trop faibles en couleur)
        mask = cv2.inRange(hsv, np.array((0., 60., 32.)), np.array((180., 255., 255.)))
        
        # Calculer un Histogramme 1D sur la Teinte (Hue) (16 bins)
        hist = cv2.calcHist([hsv], [0], mask, [16], [0, 180])
        # Normaliser pour ne pas être impacté par la taille du corps (lointain vs proche)
        cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        
        return hist

    def _compare_histograms(self, hist1, hist2):
        """ Compare la ressemblance entre deux vêtements (Renvoie une similarité entre 0.0 et 1.0) """
        if hist1 is None or hist2 is None:
            return 0.0
        # Méthode d'intersection, ou de Corrélation
        return cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)

    def register(self, centroid, bbox, signature):
        """Enregistre un nouvel objet et génère son ID associé."""
        self.objects[self.next_object_id] = centroid
        self.bboxes[self.next_object_id] = bbox
        self.signatures[self.next_object_id] = signature
        self.disappeared[self.next_object_id] = 0
        self.next_object_id += 1

    def deregister(self, object_id):
        """Supprime un objet dont la trace est définitivement perdue."""
        del self.objects[object_id]
        del self.bboxes[object_id]
        if object_id in self.signatures:
            del self.signatures[object_id]
        del self.disappeared[object_id]

    def update(self, rects, frame=None):
        """
        Met à jour le tracker à partir des nouvelles bounding boxes de YOLO.
        
        Args:
            rects: Liste des boîtes temporelles [x1, y1, x2, y2]
            frame: Image d'origine (facultatif, utilisé pour extraire la signature des vêtements)
        """
        # Calculer en amont la signature vestimentaire de chaque nouvelle boîte
        input_signatures = []
        if frame is not None and len(rects) > 0:
            for (startX, startY, endX, endY) in rects:
                sig = self._compute_color_histogram(frame, [startX, startY, endX, endY])
                input_signatures.append(sig)
        else:
            input_signatures = [None] * len(rects)

        # Si la liste des boîtes entrantes est vide
        if len(rects) == 0:
            for object_id in list(self.disappeared.keys()):
                self.disappeared[object_id] += 1

                # Si le temps d'absence max est atteint, on désenregistre
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)
            return self.objects, self.bboxes

        # Tableau Numpy des centres de gravité
        input_centroids = np.zeros((len(rects), 2), dtype="int")

        for (i, (startX, startY, endX, endY)) in enumerate(rects):
            cX = int((startX + endX) / 2.0)
            cY = int((startY + endY) / 2.0)
            input_centroids[i] = (cX, cY)

        # Si nous n'assurons pas de suivi actuellement
        if len(self.objects) == 0:
            for i in range(0, len(input_centroids)):
                self.register(input_centroids[i], rects[i], input_signatures[i])

        # Sinon, on associe...
        else:
            object_ids = list(self.objects.keys())
            object_centroids = list(self.objects.values())

            # Calcul des distances Euclidiennes entre les anciens centres et les nouveaux
            # Distance matricielle utilisant np.linalg.norm
            D = np.linalg.norm(np.array(object_centroids)[:, np.newaxis] - input_centroids, axis=2)

            # Trouver le plus petit index ligne, puis colonne par correspondances.
            rows = D.min(axis=1).argsort()
            cols = D.argmin(axis=1)[rows]

            used_rows = set()
            used_cols = set()

            for (row, col) in zip(rows, cols):
                # Si examiné avant, on ignore
                if row in used_rows or col in used_cols:
                    continue

                object_id = object_ids[row]

                # PATCH ANTI-TÉLÉPORTATION (Ex: Sortie de derrière un tableau)
                # Si la personne ré-apparaît beaucoup trop loin de là où on l'a vue pour
                # la dernière fois, ce n'est pas elle (elle ne s'est pas téléportée). 
                
                bypass_distance = False
                # S'il est trop loin
                if D[row, col] > self.max_distance:
                    # ---> RE-ID PAR LES VÊTEMENTS <---
                    # Avant de dire "C'est un inconnu, distance dépassée", on regarde son t-shirt !
                    if self.signatures[object_id] is not None and input_signatures[col] is not None:
                        sim_score = self._compare_histograms(self.signatures[object_id], input_signatures[col])
                        # S'ils sont habillés à 90% (0.90) pareil, c'est le même mec qui a couru hors caméra !
                        if sim_score > 0.85:
                            bypass_distance = True

                    if not bypass_distance:
                        continue

                # Associer l'ancien ID à la nouvelle coordonnée et nouvelle boîte
                self.objects[object_id] = input_centroids[col]
                self.bboxes[object_id] = rects[col]
                if input_signatures[col] is not None:
                    # Apprentissage très léger mais continu du vêtement (au cas où il change de pièce/lumière)
                    self.signatures[object_id] = input_signatures[col]
                self.disappeared[object_id] = 0

                used_rows.add(row)
                used_cols.add(col)

            # Calcul des index restants pour les row et col non utilisés
            unused_rows = set(range(0, D.shape[0])).difference(used_rows)
            unused_cols = set(range(0, D.shape[1])).difference(used_cols)

            # Si on a "perdu" un objet (YOLO l'a manqué ce tour ci ou il est derrière un tableau)
            # D.shape[0] (nombre d'anciens centres) vs D.shape[1] (nombre de nouvelles boîtes)
            if D.shape[0] >= D.shape[1]:
                for row in unused_rows:
                    object_id = object_ids[row]
                    self.disappeared[object_id] += 1
                    
                    # C'est ICI qu'on déclenche l'oubli définitif
                    if self.disappeared[object_id] > self.max_disappeared:
                        self.deregister(object_id)
            # Si un NOUVEL objet arrive OU si la distance était TROP grande
            # (L'objet est sorti du tableau, on crée ID X+1 direct)
            # Note: il faut itérer sur TOUS les "unused_cols", peu importe si D.shape[0] >= D.shape[1].
            for col in unused_cols:
                self.register(input_centroids[col], rects[col], input_signatures[col])
                        
        return self.objects, self.bboxes
