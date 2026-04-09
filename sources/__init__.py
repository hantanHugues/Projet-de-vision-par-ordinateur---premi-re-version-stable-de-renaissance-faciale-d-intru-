"""
Module sources — Abstraction des sources vidéo.

Ce module fournit une interface commune pour toutes les sources
vidéo possibles (webcam, ESP32-CAM, fichier, RTSP).
L'objectif est que le reste du code ne sache JAMAIS d'où vient
l'image : il appelle simplement source.read_frame().

Phase 0 : WebcamSource uniquement.
"""

from sources.base import VideoSource
from sources.webcam import WebcamSource

__all__ = ["VideoSource", "WebcamSource"]
