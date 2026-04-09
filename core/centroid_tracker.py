"""
Centroid Tracker — Suivi d'objets (Tracking).

Phase 4 : Assigne un ID unique à chaque détection humaine.
Basé sur la distance Euclidienne entre les centres des boîtes au fil du temps.
Extrêmement léger et adapté au traitement Edge (Raspberry Pi).
"""

import numpy as np
from collections import OrderedDict

class CentroidTracker:
    def __init__(self, max_disappeared=20):
        """
        Initialise le tracker avec OrderedDict pour mémoriser l'ordre de création.
        
        Args:
            max_disappeared: Le nombre d'images (frames) consécutives pendant 
                             lesquelles un objet peut disparaître avant que 
                             son ID ne soit supprimé et réinitialisé.
        """
        self.next_object_id = 1
        self.objects = OrderedDict()
        self.bboxes = OrderedDict()  # <-- NOUVEAU: Stocker les bounding boxes
        self.disappeared = OrderedDict()
        self.max_disappeared = max_disappeared

    def register(self, centroid, bbox):
        """Enregistre un nouvel objet et génère son ID associé."""
        self.objects[self.next_object_id] = centroid
        self.bboxes[self.next_object_id] = bbox
        self.disappeared[self.next_object_id] = 0
        self.next_object_id += 1

    def deregister(self, object_id):
        """Supprime un objet dont la trace est définitivement perdue."""
        del self.objects[object_id]
        del self.bboxes[object_id]
        del self.disappeared[object_id]

    def update(self, rects):
        """
        Met à jour le tracker à partir des nouvelles bounding boxes de YOLO.

        Args:
            rects: Liste des boîtes au format [x1, y1, x2, y2]
                   (Ex: celles générées par YoloDetector.detect_humans)

        Returns:
            Tuple (objects, bboxes) contenant les dictionnaires ordonnés
            {object_id: (cX, cY)} et {object_id: (x1, y1, x2, y2)}
        """
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
                self.register(input_centroids[i], rects[i])

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

                # Associer l'ancien ID à la nouvelle coordonnée et nouvelle boîte
                object_id = object_ids[row]
                self.objects[object_id] = input_centroids[col]
                self.bboxes[object_id] = rects[col]
                self.disappeared[object_id] = 0

                used_rows.add(row)
                used_cols.add(col)

            # Calcul des index restants pour les row et col non utilisés
            unused_rows = set(range(0, D.shape[0])).difference(used_rows)
            unused_cols = set(range(0, D.shape[1])).difference(used_cols)

            # Si on a "perdu" un objet (YOLO l'a manqué ce tour ci)
            if D.shape[0] >= D.shape[1]:
                for row in unused_rows:
                    object_id = object_ids[row]
                    self.disappeared[object_id] += 1
                    if self.disappeared[object_id] > self.max_disappeared:
                        self.deregister(object_id)
            # Sinon, c'est qu'un nouvel humain vient d'entrer dans la scène
            else:
                for col in unused_cols:
                    self.register(input_centroids[col], rects[col])

        return self.objects, self.bboxes
