"""
Module logger — Affichage de terminaux virtuels 
et centralisation des impressions système (console + interface vidéo).

Phase 2.5 : Visual Logger pour le Hub de Décision.
"""

import cv2
import numpy as np
import collections
from datetime import datetime
import config

class VisualLogger:
    """Consigne les événements et les affiche sur l'image vidéo et dans la console."""
    
    def __init__(self, max_lines=config.VISUAL_LOG_LINES):
        self.max_lines = max_lines
        # File d'attente circulaire (si pleine, le plus ancien est écrasé)
        self.logs = collections.deque(maxlen=max_lines)

    def _print_virtual(self, level, message):
        """Formate le message, l'affiche dans le terminal, et l'enregistre en mémoire."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {message}"
        
        # Ajout à la mémoire tampon pour la vidéo
        self.logs.append(log_line)
        
        # Affichage classique dans la ligne de commande (Terminal)
        # On pourrait ajouter de la couleur ANSI : \033[92m pour vert, etc.
        print(log_line)

    def info(self, message):
        self._print_virtual("INFO", message)

    def success(self, message):
        self._print_virtual("SUCCESS", message)

    def warning(self, message):
        self._print_virtual("WARNING", message)

    def error(self, message):
        self._print_virtual("ERROR", message)

    def overlay_logs(self, frame):
        """
        Allonge la frame vidéo OpenCV pour ajouter une console noire en bas.
        """
        # Obtenir les dimensions de l'image (frame)
        height, width, channels = frame.shape
        
        # On calcule la hauteur totale du panneau noir : env 20 pixels par ligne de log
        panel_height = self.max_lines * 20 + 10
        
        # Création du canvas noir (la matrice Numpy vide)
        log_panel = np.zeros((panel_height, width, 3), dtype=np.uint8)
        
        # Un léger fond gris foncé (RGB inverse dans OpenCV : BGR)
        log_panel[:] = (20, 20, 20)
        
        # Écriture des lignes de texte dans le panneau
        y_offset = 20
        for log_text in self.logs:
            # Couleurs selon le type de log (format BGR pour OpenCV)
            color = (200, 200, 200) # Blanc cassé par défaut
            if "[SUCCESS]" in log_text:
                color = (0, 255, 0) # Vert
            elif "[WARNING]" in log_text:
                color = (0, 200, 255) # Jaune
            elif "[ERROR]" in log_text:
                color = (0, 0, 255) # Rouge
            elif "[INFO]" in log_text:
                color = (255, 255, 0) # Cyan/Bleu ciel
                
            # OpenCV utilise text, position (x, y), police, taille, couleur, épaisseur
            cv2.putText(
                log_panel, 
                log_text, 
                (10, y_offset), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.45, 
                color, 
                1
            )
            y_offset += 20
            
        # On attache (empile) l'image de la caméra Haut, et le panneau Bas
        combined_frame = np.vstack((frame, log_panel))
        
        return combined_frame
