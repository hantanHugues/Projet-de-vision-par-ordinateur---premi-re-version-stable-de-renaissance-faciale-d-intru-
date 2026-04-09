import cv2
import requests
import time
import numpy as np
import threading

# L'adresse de notre nouveau serveur central d'Intelligence Artificielle (FastAPI)
SERVER_URL = "http://127.0.0.1:8000/analyze_frame"

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
    
    cap = cv2.VideoCapture(0)
    print("Caméra Démarrée. Mode Asynchrone (Anti-Lag) Activé.")
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    # Démarrage du thread réseau
    net_thread = threading.Thread(target=network_worker, daemon=True)
    net_thread.start()
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        # Mettre à jour l'image pour le thread réseau
        latest_frame = frame.copy()
        
        # 3. Réception des résultats et Dessin
        # On lit les dernières données reçues par le thread
        data_copy = latest_data.copy()
        
        if data_copy["status"] == "Connecte":
            for obj in data_copy["detections"]:
                x, y, w, h = obj["bbox"]
                identity = obj["identity"]
                object_id = obj["object_id"]
                
                # Choix des couleurs
                color = (0, 255, 0) if identity and not identity.startswith("Intrus") else (0, 0, 255)
                
                # Dessin de la boîte
                cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
                
                # Ajout du texte
                text = f"ID {object_id}: {identity}"
                cv2.putText(frame, text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                
            # Affichage du Ping réseau
            cv2.putText(frame, f"Server Ping: {data_copy['server_ping']} ms | FPS Reseau: {data_copy['fps_net']:.1f}", 
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        else:
            # En cas de problème ou démarrage
            cv2.putText(frame, data_copy["status"], (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            
        # Affichage (Fluide à 30 FPS garanti !)
        cv2.imshow("Client Camera (Edge)", frame)
        
        # Taper 'q' pour quitter
        if cv2.waitKey(1) & 0xFF == ord('q'):
            is_running = False
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    start_client()
