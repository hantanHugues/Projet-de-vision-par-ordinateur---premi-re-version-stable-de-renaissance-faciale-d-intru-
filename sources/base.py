"""
Classe abstraite VideoSource.

Toute source vidéo (webcam, ESP32, fichier, RTSP) DOIT hériter
de cette classe et implémenter ses méthodes.

Cela garantit que le pipeline principal (main.py) fonctionne
de manière identique quelle que soit la source.
"""

from abc import ABC, abstractmethod
import numpy as np


class VideoSource(ABC):
    """Interface abstraite pour une source vidéo."""

    @abstractmethod
    def open(self) -> bool:
        """
        Ouvre la connexion à la source vidéo.
        
        Returns:
            True si la connexion a réussi, False sinon.
        """
        pass

    @abstractmethod
    def read_frame(self) -> tuple[bool, np.ndarray | None]:
        """
        Lit une frame depuis la source.
        
        Returns:
            Un tuple (success: bool, frame: np.ndarray ou None).
            - success = True et frame = image si lecture réussie
            - success = False et frame = None si échec
        """
        pass

    @abstractmethod
    def release(self) -> None:
        """Libère les ressources de la source vidéo."""
        pass

    @abstractmethod
    def is_opened(self) -> bool:
        """Retourne True si la source est actuellement ouverte."""
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Retourne un nom lisible de la source (pour les logs)."""
        pass
