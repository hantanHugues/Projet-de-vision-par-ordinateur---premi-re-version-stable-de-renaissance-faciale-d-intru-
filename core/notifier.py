"""
Notifier — Alertes d'intrusion confirmée vers Telegram et e-mail.

Le calcul IA reste 100 % local : Internet n'est sollicité que comme un tuyau
sortant ponctuel, au moment où une intrusion est confirmée (voir
TrustScore._grace_expired). L'envoi ne bloque jamais le pipeline : chaque canal
part dans son propre thread et un échec est journalisé, jamais propagé.

Les identifiants (jeton du bot, mot de passe SMTP) se lisent dans le module
`config` au moment de l'envoi : un changement fait depuis le dashboard
(PUT /config → DatabaseManager.set_config) est donc pris en compte sans
redémarrer le serveur.
"""

import os
import smtplib
import ssl
import threading
import time
from datetime import datetime
from email.message import EmailMessage

import requests

import config

# Valeur renvoyée à la place d'un secret par GET /config. Un PUT qui la
# renvoie telle quelle (auto-save de la page Configuration) ne doit pas
# écraser le vrai secret.
MASK = "********"
SECRET_CONFIG_KEYS = ("TELEGRAM_BOT_TOKEN", "SMTP_PASSWORD")

TELEGRAM_API = "https://api.telegram.org"
HTTP_TIMEOUT = 15
SMTP_TIMEOUT = 15


def mask_secrets(cfg):
    """Copie de la configuration où les secrets non vides sont remplacés par MASK."""
    return {
        key: (MASK if key in SECRET_CONFIG_KEYS and value else value)
        for key, value in cfg.items()
    }


def drop_masked(updates):
    """Retire d'un PUT /config les secrets qui valent encore MASK (= inchangés)."""
    return {
        key: value for key, value in updates.items()
        if not (key in SECRET_CONFIG_KEYS and value == MASK)
    }


class NotifierError(Exception):
    """Échec d'un canal, avec un message lisible et sans aucun secret dedans."""


class Notifier:
    def __init__(self, logger=None):
        self.logger = logger
        self._last_sent = 0.0
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- #
    #  Lecture de la configuration                                       #
    # ---------------------------------------------------------------- #

    @staticmethod
    def _telegram_credentials():
        token = str(config.TELEGRAM_BOT_TOKEN or "").strip()
        chat_id = str(config.TELEGRAM_CHAT_ID or "").strip()
        return token, chat_id

    @staticmethod
    def _email_settings():
        recipients = [
            a.strip()
            for a in str(config.ALERT_EMAIL_TO or "").replace(";", ",").split(",")
            if a.strip()
        ]
        return {
            "host": str(config.SMTP_HOST or "").strip(),
            "port": int(config.SMTP_PORT or 0),
            "user": str(config.SMTP_USER or "").strip(),
            # Google affiche les mots de passe d'application en 4 blocs séparés par des espaces.
            "password": str(config.SMTP_PASSWORD or "").replace(" ", ""),
            "to": recipients,
        }

    def telegram_ready(self):
        token, chat_id = self._telegram_credentials()
        return bool(token and chat_id)

    def email_ready(self):
        s = self._email_settings()
        return bool(s["host"] and s["port"] and s["user"] and s["password"] and s["to"])

    # ---------------------------------------------------------------- #
    #  API publique                                                      #
    # ---------------------------------------------------------------- #

    def notify_intruder(self, name, snapshot_path=None, source=""):
        """
        Envoie l'alerte sur tous les canaux activés et correctement configurés.
        Non bloquant. Un délai minimal (ALERT_COOLDOWN_SECONDS) sépare deux
        alertes pour éviter l'avalanche quand le tracker attribue plusieurs
        identités à la même personne.
        """
        use_telegram = bool(config.ALERT_TELEGRAM_ENABLED) and self.telegram_ready()
        use_email = bool(config.ALERT_EMAIL_ENABLED) and self.email_ready()

        if config.ALERT_TELEGRAM_ENABLED and not use_telegram:
            self._log("warning", "[ALERTE] Telegram activé mais jeton ou identifiant de conversation manquant.")
        if config.ALERT_EMAIL_ENABLED and not use_email:
            self._log("warning", "[ALERTE] E-mail activé mais configuration SMTP incomplète.")
        if not (use_telegram or use_email):
            return

        with self._lock:
            now = time.time()
            if now - self._last_sent < config.ALERT_COOLDOWN_SECONDS:
                self._log("info", "[ALERTE] Notification ignorée (délai minimal entre deux alertes).")
                return
            self._last_sent = now

        text = self._compose(name, source)
        photo = snapshot_path if snapshot_path and os.path.isfile(snapshot_path) else None

        if use_telegram:
            self._spawn("Telegram", lambda: self._send_telegram(text, photo))
        if use_email:
            self._spawn("E-mail", lambda: self._send_email("BioGate — intrus confirmé", text, photo))

    def send_test(self, channel):
        """Envoi synchrone d'un message de test. Retourne (succès, message lisible)."""
        try:
            if channel == "telegram":
                if not self.telegram_ready():
                    return False, "Renseignez le jeton du bot et l'identifiant de conversation."
                self._send_telegram("BioGate — message de test. Les alertes Telegram fonctionnent.")
                return True, "Message de test envoyé sur Telegram."
            if channel == "email":
                if not self.email_ready():
                    return False, "Renseignez le serveur, le compte, le mot de passe et au moins un destinataire."
                self._send_email(
                    "BioGate — message de test",
                    "Message de test BioGate. Les alertes par e-mail fonctionnent.",
                )
                return True, "E-mail de test envoyé."
            return False, "Canal inconnu."
        except NotifierError as exc:
            return False, str(exc)

    def discover_telegram_chat(self):
        """
        Retrouve l'identifiant de conversation à partir du dernier message reçu
        par le bot (getUpdates). Retourne (chat_id, libellé) ou lève NotifierError.
        """
        token, _ = self._telegram_credentials()
        if not token:
            raise NotifierError("Enregistrez d'abord le jeton du bot.")
        data = self._telegram_call(token, "getUpdates", {"timeout": 0})
        for update in reversed(data.get("result", [])):
            chat = (update.get("message") or update.get("edited_message") or {}).get("chat")
            if chat and "id" in chat:
                label = chat.get("title") or chat.get("username") or chat.get("first_name") or ""
                return str(chat["id"]), label
        raise NotifierError("Aucun message reçu par le bot. Ouvrez la conversation avec lui, écrivez-lui « salut », puis réessayez.")

    # ---------------------------------------------------------------- #
    #  Canaux                                                            #
    # ---------------------------------------------------------------- #

    @staticmethod
    def _compose(name, source):
        lines = [
            "ALERTE BioGate — intrus confirmé",
            f"Individu : {name}",
        ]
        if source:
            lines.append(f"Caméra : {source}")
        lines.append(f"Heure : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        return "\n".join(lines)

    def _telegram_call(self, token, method, data, files=None):
        url = f"{TELEGRAM_API}/bot{token}/{method}"
        try:
            resp = requests.post(url, data=data, files=files, timeout=HTTP_TIMEOUT)
        except requests.exceptions.Timeout:
            raise NotifierError("Telegram n'a pas répondu à temps.") from None
        except requests.exceptions.RequestException:
            # Le texte de l'exception contient l'URL, donc le jeton : on ne le propage pas.
            raise NotifierError("Telegram est injoignable (vérifiez la connexion Internet).") from None
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        if not resp.ok or not payload.get("ok", False):
            detail = str(payload.get("description", f"code {resp.status_code}"))
            raise NotifierError(f"Telegram a refusé la requête : {detail.replace(token, '***')}")
        return payload

    def _send_telegram(self, text, photo_path=None):
        token, chat_id = self._telegram_credentials()
        if photo_path:
            with open(photo_path, "rb") as photo:
                self._telegram_call(
                    token, "sendPhoto",
                    {"chat_id": chat_id, "caption": text[:1024]},
                    files={"photo": photo},
                )
        else:
            self._telegram_call(token, "sendMessage", {"chat_id": chat_id, "text": text})

    def _send_email(self, subject, text, photo_path=None):
        s = self._email_settings()
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = s["user"]
        msg["To"] = ", ".join(s["to"])
        msg.set_content(text)
        if photo_path:
            with open(photo_path, "rb") as photo:
                msg.add_attachment(
                    photo.read(), maintype="image", subtype="jpeg",
                    filename=os.path.basename(photo_path),
                )

        context = ssl.create_default_context()
        try:
            if s["port"] == 465:
                server = smtplib.SMTP_SSL(s["host"], s["port"], timeout=SMTP_TIMEOUT, context=context)
            else:
                server = smtplib.SMTP(s["host"], s["port"], timeout=SMTP_TIMEOUT)
            with server:
                if s["port"] != 465:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                server.login(s["user"], s["password"])
                server.send_message(msg)
        except smtplib.SMTPAuthenticationError:
            raise NotifierError(
                "Identifiants refusés par le serveur. Pour Gmail, il faut un mot de passe d'application "
                "(validation en 2 étapes requise), pas le mot de passe du compte."
            ) from None
        except smtplib.SMTPRecipientsRefused:
            raise NotifierError("Le serveur a refusé l'adresse du destinataire.") from None
        except smtplib.SMTPException as exc:
            raise NotifierError(f"Erreur SMTP : {exc.__class__.__name__}.") from None
        except (OSError, TimeoutError):
            raise NotifierError("Serveur SMTP injoignable (vérifiez l'hôte, le port et la connexion Internet).") from None

    # ---------------------------------------------------------------- #
    #  Utilitaires                                                       #
    # ---------------------------------------------------------------- #

    def _spawn(self, label, fn):
        def _run():
            try:
                fn()
                self._log("info", f"[ALERTE] {label} : notification envoyée.")
            except NotifierError as exc:
                self._log("error", f"[ALERTE] {label} : {exc}")
            except Exception as exc:
                self._log("error", f"[ALERTE] {label} : erreur inattendue ({exc.__class__.__name__}).")

        threading.Thread(target=_run, daemon=True, name=f"alert-{label}").start()

    def _log(self, level, msg):
        if self.logger:
            getattr(self.logger, level)(msg)
        else:
            print(f"[{level.upper()}] {msg}")
