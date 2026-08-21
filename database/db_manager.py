import sqlite3
import json
import numpy as np
from datetime import datetime, timedelta
import os
import config


class DatabaseManager:
    def __init__(self, db_path=None, logger=None):
        db_path = db_path or config.DB_PATH
        self.db_path = db_path
        self.logger = logger
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # accès par nom de colonne
        return conn

    def _init_db(self):
        """Crée toutes les tables si elles n'existent pas, et migre les colonnes manquantes."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Table 1 — Profils
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profiles (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT UNIQUE NOT NULL,
                role       TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Table 2 — Vecteurs biométriques 512D (multi-empreintes)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS embeddings (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                vector_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(profile_id) REFERENCES profiles(id)
            )
        ''')

        # Table 3 — Logs d'événements (boîte noire)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS event_logs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id    INTEGER NOT NULL,
                confidence    REAL NOT NULL,
                event_type    TEXT NOT NULL DEFAULT 'DETECTION',
                snapshot_path TEXT DEFAULT NULL,
                timestamp     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(profile_id) REFERENCES profiles(id)
            )
        ''')

        # Migration : ajouter les colonnes si la table existait déjà sans elles
        existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(event_logs)")}
        if "event_type" not in existing_cols:
            cursor.execute("ALTER TABLE event_logs ADD COLUMN event_type TEXT NOT NULL DEFAULT 'DETECTION'")
        if "snapshot_path" not in existing_cols:
            cursor.execute("ALTER TABLE event_logs ADD COLUMN snapshot_path TEXT DEFAULT NULL")

        # Table 4 — Configuration système persistée
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_config (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Table 5 — Sources vidéo (caméras)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cameras (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                cam_id     TEXT UNIQUE NOT NULL,
                name       TEXT NOT NULL,
                type       TEXT NOT NULL DEFAULT 'usb',
                url        TEXT DEFAULT '',
                usb_index  INTEGER DEFAULT 0,
                zone       TEXT DEFAULT '',
                active     INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()
        if self.logger:
            self.logger.info("Base de données SQLite initialisée (5 tables).")

    # ------------------------------------------------------------------ #
    #  PROFILS                                                             #
    # ------------------------------------------------------------------ #

    def add_profile_if_not_exists(self, name, role="INTRUS"):
        """Retourne l'id du profil, le crée si nécessaire."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM profiles WHERE name=?", (name,))
        row = cursor.fetchone()
        if row:
            profile_id = row["id"]
        else:
            cursor.execute("INSERT INTO profiles (name, role) VALUES (?, ?)", (name, role))
            conn.commit()
            profile_id = cursor.lastrowid
        conn.close()
        return profile_id

    # ------------------------------------------------------------------ #
    #  EMBEDDINGS                                                          #
    # ------------------------------------------------------------------ #

    def add_embedding(self, name, embedding_array, role="INTRUS"):
        """Persiste un vecteur 512D. Limite à 30 vecteurs par profil."""
        profile_id = self.add_profile_if_not_exists(name, role)
        vector_json = json.dumps(embedding_array.tolist())
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO embeddings (profile_id, vector_json) VALUES (?, ?)",
            (profile_id, vector_json)
        )
        cursor.execute('''
            DELETE FROM embeddings
            WHERE profile_id = ? AND id NOT IN (
                SELECT id FROM embeddings WHERE profile_id = ?
                ORDER BY created_at DESC LIMIT 30
            )
        ''', (profile_id, profile_id))
        conn.commit()
        conn.close()

    def delete_profile(self, name: str):
        """Supprime tous les embeddings et le profil (droit à l'oubli RGPD)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM profiles WHERE name=?", (name,))
        row = cursor.fetchone()
        if row:
            cursor.execute("DELETE FROM embeddings WHERE profile_id=?", (row["id"],))
            cursor.execute("DELETE FROM profiles WHERE id=?", (row["id"],))
            conn.commit()
        conn.close()

    def get_all_embeddings(self):
        """Retourne {name: [np.array, ...]} pour tous les profils ayant des embeddings."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.name, e.vector_json
            FROM profiles p
            JOIN embeddings e ON p.id = e.profile_id
        ''')
        rows = cursor.fetchall()
        conn.close()
        result = {}
        for row in rows:
            name = row["name"]
            vec = np.array(json.loads(row["vector_json"]), dtype=np.float32)
            result.setdefault(name, []).append(vec)
        return result

    # ------------------------------------------------------------------ #
    #  LOGS D'ÉVÉNEMENTS                                                   #
    # ------------------------------------------------------------------ #

    # Types d'événements valides — centralisés ici pour éviter les fautes
    EVENT_VIP_ENTRY            = "VIP_ENTRY"
    EVENT_ACCESS_DENIED        = "ACCESS_DENIED"
    EVENT_INTRUDER_PENDING     = "INTRUDER_PENDING"
    EVENT_INTRUDER_CONFIRMED   = "INTRUDER_CONFIRMED"
    EVENT_LIVENESS_SUCCESS     = "LIVENESS_SUCCESS"
    EVENT_FINGERPRINT_OK       = "FINGERPRINT_OK"
    EVENT_FINGERPRINT_FAIL     = "FINGERPRINT_FAIL"
    EVENT_FLIGHT_ALERT         = "FLIGHT_ALERT"
    EVENT_DETECTION            = "DETECTION"

    def log_event(self, name, confidence, event_type="DETECTION", snapshot_path=None, role="INTRUS"):
        """Enregistre un événement dans la boîte noire."""
        profile_id = self.add_profile_if_not_exists(name, role)
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO event_logs (profile_id, confidence, event_type, snapshot_path) VALUES (?, ?, ?, ?)",
            (profile_id, confidence, event_type, snapshot_path)
        )
        conn.commit()
        conn.close()

    def get_logs(self, limit=50, offset=0, event_type=None, name=None, date_from=None, date_to=None):
        """
        Retourne les logs paginés et filtrés sous forme de liste de dicts.
        Filtres optionnels : event_type, name, date_from (str ISO), date_to (str ISO).
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        query = '''
            SELECT e.id, p.name, p.role, e.confidence, e.event_type,
                   e.snapshot_path, e.timestamp
            FROM event_logs e
            JOIN profiles p ON e.profile_id = p.id
            WHERE 1=1
        '''
        params = []
        if event_type:
            query += " AND e.event_type = ?"
            params.append(event_type)
        if name:
            query += " AND p.name LIKE ?"
            params.append(f"%{name}%")
        if date_from:
            query += " AND e.timestamp >= ?"
            params.append(date_from)
        if date_to:
            query += " AND e.timestamp <= ?"
            params.append(date_to)
        query += " ORDER BY e.timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_log_stats(self):
        """Retourne un résumé statistique pour le widget dashboard."""
        conn = self._get_connection()
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        stats = {}

        cursor.execute(
            "SELECT COUNT(*) FROM event_logs WHERE event_type=? AND timestamp >= ?",
            (self.EVENT_VIP_ENTRY, today)
        )
        stats["vip_entries_today"] = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM event_logs WHERE event_type=? AND timestamp >= ?",
            (self.EVENT_INTRUDER_CONFIRMED, today)
        )
        stats["intruders_today"] = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM event_logs WHERE event_type=? AND timestamp >= ?",
            (self.EVENT_FLIGHT_ALERT, today)
        )
        stats["flight_alerts_today"] = cursor.fetchone()[0]

        cursor.execute("SELECT timestamp FROM event_logs ORDER BY timestamp DESC LIMIT 1")
        row = cursor.fetchone()
        stats["last_event"] = row[0] if row else None

        conn.close()
        return stats

    def delete_log(self, log_id):
        """Supprime un log individuel et son snapshot associé (droit à l'oubli RGPD)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT snapshot_path FROM event_logs WHERE id=?", (log_id,))
        row = cursor.fetchone()
        if row and row["snapshot_path"] and os.path.exists(row["snapshot_path"]):
            os.remove(row["snapshot_path"])
        cursor.execute("DELETE FROM event_logs WHERE id=?", (log_id,))
        conn.commit()
        conn.close()

    def purge_old_snapshots(self, retention_hours=None):
        """
        Supprime les snapshots et logs antérieurs à retention_hours.
        Retourne le nombre d'entrées supprimées.
        """
        hours = retention_hours or config.RGPD_SNAPSHOT_RETENTION_HOURS
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, snapshot_path FROM event_logs WHERE timestamp < ?", (cutoff,)
        )
        old_rows = cursor.fetchall()
        deleted = 0
        for row in old_rows:
            if row["snapshot_path"] and os.path.exists(row["snapshot_path"]):
                os.remove(row["snapshot_path"])
            cursor.execute("DELETE FROM event_logs WHERE id=?", (row["id"],))
            deleted += 1
        conn.commit()
        conn.close()
        return deleted

    # ------------------------------------------------------------------ #
    #  CONFIGURATION SYSTÈME                                               #
    # ------------------------------------------------------------------ #

    # Templates prédéfinis — point de départ pour l'utilisateur
    _TEMPLATES = {
        "PORTAIL": {
            "ALERT_GRACE_PERIOD": 120,
            "MFA_REQUIRED": False,
            "ALERT_WHATSAPP_ENABLED": True,
            "FACE_ANALYSIS_TIME_LIMIT": 1.5,
            "RECHECK_FAILURE_TOLERANCE": 5,
            "RGPD_SNAPSHOT_RETENTION_HOURS": 72,
            "FINGERPRINT_TIMEOUT": 20.0,
            "LIVENESS_ENABLED": True,
        },
        "DOMICILE": {
            "ALERT_GRACE_PERIOD": 60,
            "MFA_REQUIRED": False,
            "ALERT_WHATSAPP_ENABLED": True,
            "FACE_ANALYSIS_TIME_LIMIT": 1.0,
            "RECHECK_FAILURE_TOLERANCE": 3,
            "RGPD_SNAPSHOT_RETENTION_HOURS": 72,
            "FINGERPRINT_TIMEOUT": 15.0,
            "LIVENESS_ENABLED": True,
        },
        "BUREAU": {
            "ALERT_GRACE_PERIOD": 30,
            "MFA_REQUIRED": True,
            "ALERT_WHATSAPP_ENABLED": False,
            "FACE_ANALYSIS_TIME_LIMIT": 1.0,
            "RECHECK_FAILURE_TOLERANCE": 3,
            "RGPD_SNAPSHOT_RETENTION_HOURS": 24,
            "FINGERPRINT_TIMEOUT": 15.0,
            "LIVENESS_ENABLED": True,
        },
        "HAUTE_SECURITE": {
            "ALERT_GRACE_PERIOD": 5,
            "MFA_REQUIRED": True,
            "ALERT_WHATSAPP_ENABLED": True,
            "FACE_ANALYSIS_TIME_LIMIT": 0.8,
            "RECHECK_FAILURE_TOLERANCE": 1,
            "RGPD_SNAPSHOT_RETENTION_HOURS": 12,
            "FINGERPRINT_TIMEOUT": 10.0,
            "LIVENESS_ENABLED": False,
        },
    }

    def get_config(self, key):
        """Retourne la valeur persistée ou None si absente (le code fait le fallback sur config.py)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_config WHERE key=?", (key,))
        row = cursor.fetchone()
        conn.close()
        return json.loads(row["value"]) if row else None

    def set_config(self, key, value):
        """Persiste ou met à jour une clé de configuration."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO system_config (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        ''', (key, json.dumps(value)))
        conn.commit()
        conn.close()

    def get_all_config(self):
        """Retourne toutes les clés persistées sous forme de dict {key: value}."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM system_config")
        rows = cursor.fetchall()
        conn.close()
        return {row["key"]: json.loads(row["value"]) for row in rows}

    def apply_template(self, template_name):
        """
        Écrit les valeurs du template en base en une transaction.
        Retourne False si le template n'existe pas.
        """
        template = self._TEMPLATES.get(template_name.upper())
        if not template:
            return False
        conn = self._get_connection()
        cursor = conn.cursor()
        for key, value in template.items():
            cursor.execute('''
                INSERT INTO system_config (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            ''', (key, json.dumps(value)))
        cursor.execute('''
            INSERT INTO system_config (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        ''', ("SECURITY_PROFILE_NAME", json.dumps(template_name.upper())))
        conn.commit()
        conn.close()
        return True

    def get_templates(self):
        """Retourne les templates disponibles avec leurs valeurs."""
        return {name: dict(values) for name, values in self._TEMPLATES.items()}

    def get_effective_config(self):
        """
        Retourne la configuration effective : valeurs DB en priorité,
        fallback sur config.py pour les clés absentes.
        """
        db_values = self.get_all_config()
        defaults = {
            "FACE_RECOGNITION_THRESHOLD":     config.FACE_RECOGNITION_THRESHOLD,
            "FACE_RECHECK_INTERVAL":          config.FACE_RECHECK_INTERVAL,
            "FACE_ANALYSIS_TIME_LIMIT":       config.FACE_ANALYSIS_TIME_LIMIT,
            "YOLO_CONFIDENCE_THRESHOLD":      config.YOLO_CONFIDENCE_THRESHOLD,
            "YOLO_IMAGE_SIZE":                config.YOLO_IMAGE_SIZE,
            "MFA_REQUIRED":                   config.MFA_REQUIRED,
            "LIVENESS_ENABLED":               config.LIVENESS_ENABLED,
            "TRUST_FACE_THRESHOLD":           config.TRUST_FACE_THRESHOLD,
            "TRUST_LIVENESS_THRESHOLD":       config.TRUST_LIVENESS_THRESHOLD,
            "TRUST_FINGERPRINT_THRESHOLD":    config.TRUST_FINGERPRINT_THRESHOLD,
            "FINGERPRINT_TIMEOUT":            config.FINGERPRINT_TIMEOUT,
            "LIVENESS_CHALLENGE_TIMEOUT":     config.LIVENESS_CHALLENGE_TIMEOUT,
            "RECHECK_FAILURE_TOLERANCE":      config.RECHECK_FAILURE_TOLERANCE,
            "ALERT_GRACE_PERIOD":             config.ALERT_GRACE_PERIOD,
            "ALERT_WHATSAPP_ENABLED":         config.ALERT_WHATSAPP_ENABLED,
            "WHATSAPP_RECIPIENT":             config.WHATSAPP_RECIPIENT,
            "IOT_ENABLED":                    config.IOT_ENABLED,
            "FINGERPRINT_ESP32_IP":           config.FINGERPRINT_ESP32_IP,
            "DOOR_ESP32_IP":                  config.DOOR_ESP32_IP,
            "LIGHT_ESP32_IP":                 config.LIGHT_ESP32_IP,
            "RGPD_SNAPSHOT_RETENTION_HOURS":  config.RGPD_SNAPSHOT_RETENTION_HOURS,
            "SECURITY_PROFILE_NAME":          config.SECURITY_PROFILE_NAME,
        }
        return {**defaults, **db_values}

    # ------------------------------------------------------------------ #
    #  CAMÉRAS                                                             #
    # ------------------------------------------------------------------ #

    def add_camera(self, cam_id: str, name: str, cam_type: str = "usb",
                   url: str = "", usb_index: int = 0, zone: str = "") -> dict:
        """Enregistre une nouvelle source vidéo. Lève IntegrityError si cam_id existe déjà."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO cameras (cam_id, name, type, url, usb_index, zone) VALUES (?,?,?,?,?,?)",
            (cam_id, name, cam_type, url, usb_index, zone),
        )
        conn.commit()
        row_id = cursor.lastrowid
        cursor.execute("SELECT * FROM cameras WHERE id=?", (row_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row)

    def get_cameras(self, active_only: bool = False) -> list:
        """Retourne toutes les caméras enregistrées."""
        conn = self._get_connection()
        cursor = conn.cursor()
        if active_only:
            cursor.execute("SELECT * FROM cameras WHERE active=1 ORDER BY created_at")
        else:
            cursor.execute("SELECT * FROM cameras ORDER BY created_at")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_camera(self, cam_id: str) -> dict | None:
        """Retourne une caméra par son cam_id ou None."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cameras WHERE cam_id=?", (cam_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_camera(self, cam_id: str, **kwargs) -> bool:
        """Met à jour les champs autorisés d'une caméra. Retourne True si trouvée."""
        allowed = {"name", "type", "url", "usb_index", "zone", "active"}
        fields  = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return False
        set_clause = ", ".join(f"{k}=?" for k in fields)
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE cameras SET {set_clause} WHERE cam_id=?",
            (*fields.values(), cam_id),
        )
        changed = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return changed

    def delete_camera(self, cam_id: str) -> bool:
        """Supprime une caméra de la base. Retourne True si trouvée."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cameras WHERE cam_id=?", (cam_id,))
        changed = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return changed
