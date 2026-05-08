import cv2
import requests
import time
import numpy as np
import threading

# L'adresse de notre nouveau serveur central d'Intelligence Artificielle (FastAPI)
SERVER_URL = "http://127.0.0.1:8000/analyze_frame"
ENROLL_URL = "http://127.0.0.1:8000/enroll"

# --- Variables Globales pour le Multithreading ---
# Permet à la caméra de ne jamais ralentir (30 FPS) pendant que le réseau travaille
latest_frame = None
latest_data = {"detections": [], "server_ping": 0, "fps_net": 0, "status": "Demarrage"}
is_running = True

def network_worker():
    """Ce thread s'occupe de parler au serveur en arrière-plan sans bloquer la caméra."""
    global latest_frame, latest_data, is_running
    
    while is_running:
        if latest_frame is None:
            time.sleep(0.01)
            continue
            
        start_network = time.time()
        
        # Copie de sécurité pour éviter que l'image change pendant l'encodage
        frame_to_send = latest_frame.copy()
        
        # 1. Encodage JPG pour transmission
        _, img_encoded = cv2.imencode('.jpg', frame_to_send, [cv2.IMWRITE_JPEG_QUALITY, 80])
        
        # 2. Envoi HTTP POST
        try:
            response = requests.post(SERVER_URL, files={"file": ("frame.jpg", img_encoded.tobytes(), "image/jpeg")}, timeout=3.0)
            
            if response.status_code == 200:
                data = response.json()
                fps = 1.0 / (time.time() - start_network)
                
                if data.get("success"):
                    latest_data = {
                        "detections": data["detections"],
                        "server_ping": int(data.get("process_time_ms", 0)),
                        "fps_net": fps,
                        "status": "Connecte"
                    }
            else:
                latest_data["status"] = f"ERREUR API: {response.status_code}"
                time.sleep(0.5) # Ne pas spammer le serveur s'il crashe
                
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            latest_data["status"] = "Serveur IA INACCESSIBLE."
            time.sleep(1.0) # Attendre avant de réessayer

def start_client():
    global latest_frame, is_running, latest_data
    
    print("=== Configuration de la Source Vidéo ===")
    print("1. Webcam Locale PC (Défaut)")
    print("2. IP Webcam (Smartphone WiFi LAN)")
    choice = input("Choisissez votre source (1 ou 2) [Défaut: 1] : ").strip()
    
    if choice == "2":
        ip_url = input("Entrez l'URL HD (ex: http://192.168.1.95:8080/video) : ").strip()
        # Si l'utilisateur appuie juste sur entrer, on met une url générique pour éviter le crash
        source = ip_url if ip_url else "http://192.168.1.95:8080/video"
        cap = cv2.VideoCapture(source)
        print(f"Tentative de connexion au flux réseau : {source}")
    else:
        cap = cv2.VideoCapture(0)
        print("Caméra Locale Démarrée.")
        
    if not cap.isOpened():
        print("[ERREUR] Impossible de se connecter à la source vidéo. Vérifiez IP ou votre webcam.")
        return
        
    print("Mode Asynchrone (Anti-Lag) Activé.")
    
    # Résolution (Ignoré par certains flux HTTP IP Webcam, mais sécurisant)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    # Variables pour le Terminal Interactif UI
    terminal_lines = ["--- Terminal Client SURVEILLE.IA ---", "Tapez 'enroll [Nom]' + Entree pour inscrire un VIP."]
    terminal_input = ""
    mode = "NORMAL"
    enroll_name = ""
    enroll_start_time = 0
    
    def log_term(msg):
        terminal_lines.append(msg)
        if len(terminal_lines) > 5:
            terminal_lines.pop(0)

    # Démarrage du thread réseau
    net_thread = threading.Thread(target=network_worker, daemon=True)
    net_thread.start()
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        latest_frame = frame.copy()
        h_frame, w_frame = frame.shape[:2]
        
        data_copy = latest_data.copy()
        
        # 3. DESSIN MODE NORMAL (TRACKING)
        if mode == "NORMAL" and data_copy["status"] == "Connecte":
            for obj in data_copy["detections"]:
                x, y, w, h = obj["bbox"]
                identity = obj["identity"]
                object_id = obj["object_id"]
                
                # Dessin de la boîte Principale Bounding Box de YOLO
                color = (0, 255, 0) if identity and not identity.startswith("Intrus") else (0, 0, 255)
                cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
                
                # Dessin du "Face Box" rassurant (S'il est détecté sur cette frame)
                if obj.get("face_box"):
                    fx, fy, fw, fh = obj["face_box"]
                    # On dessine une belle bordure un peu plus fine autour de la tête (cyan)
                    cv2.rectangle(frame, (fx, fy), (fx+fw, fy+fh), (255, 255, 0), 1)
                    # Un tout petit label pour dire "Face OK" (Montre que le Face Gate passe)
                    cv2.putText(frame, "Visage vu", (fx, fy - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)

                text = f"ID {object_id}: {identity}"
                cv2.putText(frame, text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                
            cv2.putText(frame, f"Server Ping: {data_copy['server_ping']} ms | FPS Reseau: {data_copy['fps_net']:.1f}", 
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        elif data_copy["status"] != "Connecte":
            cv2.putText(frame, data_copy["status"], (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        # 4. GESTION DU MODE ENROLLMENT (INSCRIPTION)
        if mode == "ENROLL_WAIT":
            elapsed = time.time() - enroll_start_time
            remaining = 3.0 - elapsed
            
            # Filtre sombre pour se concentrer
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (w_frame, h_frame), (0, 0, 0), -1)
            frame = cv2.addWeighted(overlay, 0.5, frame, 0.5, 0)
            
            cv2.putText(frame, f"Fixez l'objectif d'un air neutre", (w_frame//2 - 200, h_frame//2 - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            cv2.putText(frame, f"Capture dans {remaining:.1f}s", (w_frame//2 - 120, h_frame//2 + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            if remaining <= 0:
                mode = "ENROLL_SHOOT"
                
        elif mode == "ENROLL_SHOOT":
            # Effet de Flash (Écran blanc furtif)
            flash = np.full((h_frame, w_frame, 3), 255, dtype=np.uint8)
            # Afficher temporairement le flash avec un terminal vide basique
            flash_display = np.vstack((flash, np.zeros((150, w_frame, 3), dtype=np.uint8)))
            cv2.imshow("Client Camera (Edge)", flash_display)
            cv2.waitKey(50)
            
            log_term(f"Envoi de la photo VIP pour '{enroll_name}'...")
            _, img_encoded = cv2.imencode('.jpg', latest_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            
            try:
                # Appel direct à ta belle route définitive sur l'API FastAPI !
                response = requests.post(
                    ENROLL_URL, 
                    data={"name": enroll_name},
                    files={"file": ("frame.jpg", img_encoded.tobytes(), "image/jpeg")},
                    timeout=5.0
                )
                if response.status_code == 200:
                    res_data = response.json()
                    if res_data.get("success"):
                        log_term(f"[SUCCES] {res_data.get('message')}")
                    else:
                        log_term(f"[ECHEC] {res_data.get('message')}")
                else:
                    log_term(f"[ERREUR] API Code {response.status_code}")
            except Exception as e:
                log_term(f"[ERREUR RESEAU] Impossible de joindre le backend.")
                
            mode = "NORMAL"
            enroll_name = ""

        # 5. DESSINER LE TERMINAL INTERACTIF EN BAS
        term_height = 150
        terminal_bg = np.zeros((term_height, w_frame, 3), dtype=np.uint8)
        
        # Afficher l'historique Logs
        y_text = 25
        for line in terminal_lines:
            cv2.putText(terminal_bg, line, (10, y_text), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            y_text += 20
            
        # Afficher la ligne de Commande d'Input utilisateur
        cv2.putText(terminal_bg, f"root@camera:~# {terminal_input}_", (10, term_height - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        # Fusionner Flux vidéo Haut + Terminal Bas
        final_display = np.vstack((frame, terminal_bg))
        
        cv2.imshow("Client Camera (Edge)", final_display)
        
        # 6. CAPTURE CLAVIER INTERACTIVE
        key = cv2.waitKey(1) & 0xFF
        if key != 255:
            if key == 27: # Touche "Echap" pour quitter tout
                is_running = False
                break
            elif key == 8: # Touche "Backspace" (Effacer un caractère)
                terminal_input = terminal_input[:-1]
            elif key == 13 or key == 10: # Touche "Entrée" (Valider Commande)
                if terminal_input.strip():
                    cmd = terminal_input.strip()
                    log_term(f"root@camera:~# {cmd}")
                    terminal_input = ""
                    
                    parts = cmd.split()
                    cmd_name = parts[0].lower()
                    
                    if cmd_name == "enroll":
                        if len(parts) > 1:
                            enroll_name = " ".join(parts[1:])
                            mode = "ENROLL_WAIT"  # Déclenche le processus UI
                            enroll_start_time = time.time()
                            log_term(f"Preparation a l'enregistrement de '{enroll_name}'...")
                        else:
                            log_term("Usage: enroll [Ton Prenom]")
                    elif cmd_name == "quit" or cmd_name == "exit":
                        is_running = False
                        break
                    else:
                        log_term("Commande inconnue. ('enroll [Nom]', 'quit')")
            elif 32 <= key <= 126: # Caractères normaux ABC...
                # On bloque l'ancienne touche fermante si on tape, sauf si c'est la seule
                terminal_input += chr(key)

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    start_client()
