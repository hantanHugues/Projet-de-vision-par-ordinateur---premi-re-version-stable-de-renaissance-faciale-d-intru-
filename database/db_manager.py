import sqlite3
import json
import numpy as np
from datetime import datetime
import os

class DatabaseManager:
    def __init__(self, db_path="database/visages.db", logger=None):
        self.db_path = db_path
        self.logger = logger
        
        # S'assurer que le dossier existe
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Créer les tables de manière robuste si elles n'existent pas."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Table 1 : Les profils uniques (Intrus A, Ash, etc.)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL,          -- "VIP" ou "INTRUS"
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Table 2 : Les multiples vecteurs 512D pour un même profil (L'Effet Multi-Empreintes)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                vector_json TEXT NOT NULL,   -- L'ADN mathématique 512D stocké en texte
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(profile_id) REFERENCES profiles(id)
            )
        ''')

        # Table 3 : Les logs de détection (Historique de passage devant la caméra)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS event_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                confidence REAL NOT NULL,    -- Le pourcentage de ressemblance (ex: 85%)
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(profile_id) REFERENCES profiles(id)
            )
        ''')

        conn.commit()
        conn.close()
        if self.logger:
            self.logger.info("Base de données SQLite (visages.db) initialisée avec succès.")

    def add_profile_if_not_exists(self, name, role="INTRUS"):
        """Vérifie si la personne existe, sinon la crée et retourne son ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM profiles WHERE name=?", (name,))
        result = cursor.fetchone()
        
        if result:
            profile_id = result[0]
        else:
            cursor.execute("INSERT INTO profiles (name, role) VALUES (?, ?)", (name, role))
            conn.commit()
            profile_id = cursor.lastrowid
            
        conn.close()
        return profile_id

    def add_embedding(self, name, embedding_array, role="INTRUS"):
        """Sauvegarde un nouveau vecteur 512D pour une personne (Limite à 30 max par personne)."""
        profile_id = self.add_profile_if_not_exists(name, role)
        
        # Convertir le numpy array 512D en texte JSON pour stockage
        vector_list = embedding_array.tolist()
        vector_json = json.dumps(vector_list)

        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 1. Insérer le nouveau vecteur
        cursor.execute("INSERT INTO embeddings (profile_id, vector_json) VALUES (?, ?)", (profile_id, vector_json))
        
        # 2. Nettoyer les vecteurs excédentaires (Garder uniquement les 30 plus récents)
        cursor.execute('''
            DELETE FROM embeddings 
            WHERE profile_id = ? AND id NOT IN (
                SELECT id FROM embeddings 
                WHERE profile_id = ? 
                ORDER BY created_at DESC 
                LIMIT 30
            )
        ''', (profile_id, profile_id))
        
        conn.commit()
        conn.close()

    def log_event(self, name, confidence):
        """Enregistre le passage de la personne avec un pourcentage de confiance."""
        profile_id = self.add_profile_if_not_exists(name)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO event_logs (profile_id, confidence) VALUES (?, ?)", (profile_id, confidence))
        conn.commit()
        conn.close()

    def get_all_embeddings(self):
        """
        Récupère TOUS les visages enregistrés pour l'algorithme de reconnaissance.
        Retourne un dictionnaire : { "Intrus A": [vecteur1, vecteur2...], "Ash": [vecteur1] }
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # On joint les tables pour avoir les Noms + Vecteurs associés
        cursor.execute('''
            SELECT p.name, e.vector_json 
            FROM profiles p
            JOIN embeddings e ON p.id = e.profile_id
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        historical_faces = {}
        for name, vector_json in results:
            vector_array = np.array(json.loads(vector_json), dtype=np.float32)
            if name not in historical_faces:
                historical_faces[name] = []
            historical_faces[name].append(vector_array)
            
        return historical_faces
