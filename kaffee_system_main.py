import tkinter as tk
from tkinter import messagebox
from smartcard.System import readers
from smartcard.util import toHexString
import threading
import time
import requests
import socket

# --- KONFIGURATION ---
SERVER_URL = "http://localhost:5000"

def get_ip_address():
    """Ermittelt die lokale IP-Adresse im Netzwerk."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1 (Offline)"

class KaffeeSystem:
    def __init__(self, master):
        self.master = master
        master.title("Kaffee System")
        master.geometry("480x320")
        
        # 1. Vollbild aktivieren
        master.attributes('-fullscreen', True)
        master.configure(bg="#2c3e50") # Hintergrundfarbe für das Hauptfenster

        # 2. Notausgang (Beenden mit ESC)
        def beenden(event=None):
            master.destroy()
        master.bind("<Escape>", beenden)

        # Variablen
        self.current_user = None 
        self.running = True
        self.rfid_cooldown = False
        self.timeout_job = None

        # --- NEU: DAUERHAFTER FOOTER (Immer sichtbar) ---
        # Dieser Balken wird ganz unten am Hauptfenster fixiert
        aktuelle_ip = get_ip_address()
        self.lbl_ip = tk.Label(master, text=f"Web-Dashboard: http://{aktuelle_ip}:5000", 
                               font=("Arial", 12, "bold"), fg="white", bg="#34495e", pady=6)
        self.lbl_ip.pack(side="bottom", fill="x") # 'bottom' pinnt es fest, 'fill="x"' macht es so breit wie den Bildschirm

        # --- CONTAINER FÜR DEN WECHSELNDEN INHALT ---
        # Der Container füllt den restlichen Platz über dem Footer aus
        self.container = tk.Frame(master, bg="#2c3e50")
        self.container.pack(side="top", fill="both", expand=True)

        # --- LAYOUTS (Werden nun im Container platziert statt direkt im Master) ---
        self.frame_start = tk.Frame(self.container, bg="#2c3e50")
        self.frame_auswahl = tk.Frame(self.container, bg="#ecf0f1")

        # 1. STARTSEITE
        self.lbl_start = tk.Label(self.frame_start, text="Bitte Chip\nvorhalten...", 
                                  font=("Arial", 28, "bold"), fg="white", bg="#2c3e50")
        self.lbl_start.pack(expand=True)

        # 2. AUSWAHLSEITE
        self.frame_auswahl.columnconfigure(0, weight=1)
        self.frame_auswahl.columnconfigure(1, weight=1)
        self.frame_auswahl.rowconfigure(1, weight=1)

        self.lbl_info = tk.Label(self.frame_auswahl, text="Lade...", 
                                 font=("Arial", 14, "bold"), bg="#bdc3c7", height=2)
        self.lbl_info.grid(row=0, column=0, columnspan=2, sticky="nsew")

        # Buttons
        self.btn_schwarz = tk.Button(self.frame_auswahl, text="Kaffee\nmit Koffein\n(0.40€)", bg="#6f4e37", fg="white",
                                     font=("Arial", 16, "bold"), command=lambda: self.buche_produkt("Kaffee mit Koffein", 0.40))
        self.btn_schwarz.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        self.btn_decaf = tk.Button(self.frame_auswahl, text="Kaffee\nEntkoffeiniert\n(0.40€)", bg="#16a085", fg="white",
                                   font=("Arial", 16, "bold"), command=lambda: self.buche_produkt("Kaffee Entkoffeiniert", 0.40))
        self.btn_decaf.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)
        
        self.btn_logout = tk.Button(self.frame_auswahl, text="Abbrechen", bg="#c0392b", fg="white",
                                    font=("Arial", 14), command=self.logout)
        self.btn_logout.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        # Startbildschirm initial anzeigen
        self.frame_start.pack(fill="both", expand=True)

        # RFID Thread starten
        self.rfid_thread = threading.Thread(target=self.rfid_loop, daemon=True)
        self.rfid_thread.start()

    def rfid_loop(self):
        while self.running:
            if self.rfid_cooldown:
                time.sleep(0.5)
                continue
                
            try:
                r = readers()
                if not r:
                    time.sleep(1)
                    continue
                
                connection = r[0].createConnection()
                connection.connect()
                
                data, sw1, sw2 = connection.transmit([0xFF, 0xCA, 0x00, 0x00, 0x00])
                if sw1 == 0x90:
                    uid_hex = toHexString(data).replace(" ", "")
                    
                    if self.current_user is None:
                        self.master.after(0, lambda: self.check_karte_am_server(uid_hex))
                        self.rfid_cooldown = True
                        time.sleep(2)
                        self.rfid_cooldown = False
                        
            except Exception:
                pass
            time.sleep(0.1)

    def check_karte_am_server(self, uid):
        print(f"Prüfe Karte: {uid}")
        try:
            response = requests.get(f"{SERVER_URL}/api/check_card/{uid}", timeout=2)
            data = response.json()
            
            if data['status'] == 'ok':
                self.current_user = data
                self.show_auswahl()
            else:
                self.lbl_start.config(text=f"Karte Unbekannt!\nUID: {uid}", fg="red")
                self.master.after(3000, lambda: self.lbl_start.config(text="Bitte Chip\nvorhalten...", fg="white"))
                
        except requests.exceptions.ConnectionError:
            self.lbl_start.config(text="Server Fehler!", fg="orange")
            self.master.after(3000, lambda: self.lbl_start.config(text="Bitte Chip\nvorhalten...", fg="white"))

    def show_auswahl(self):
        self.frame_start.pack_forget()
        self.frame_auswahl.pack(fill="both", expand=True)
        
        saldo = self.current_user['saldo']
        farbe = "#aaffaa" if saldo >= 0 else "#ffaaaa"
        self.lbl_info.config(text=f"Hallo {self.current_user['name']}\nSaldo: {saldo:.2f} €", bg=farbe)
        
        if self.timeout_job:
            self.master.after_cancel(self.timeout_job)
        self.timeout_job = self.master.after(20000, self.logout)

    def buche_produkt(self, produkt_name, preis):
        if not self.current_user: return
        
        if self.timeout_job:
            self.master.after_cancel(self.timeout_job)
            self.timeout_job = None
        
        payload = {
            'user_id': self.current_user['user_id'],
            'product': produkt_name,
            'price': preis
        }
        
        try:
            resp = requests.post(f"{SERVER_URL}/api/book", json=payload)
            result = resp.json()
            
            if result['status'] == 'success':
                new_saldo = result['new_saldo']
                self.lbl_info.config(text=f"✅ {produkt_name}\nRest: {new_saldo:.2f} €", bg="#ffffaa")
                self.master.after(2000, self.logout)
                
        except Exception as e:
            self.lbl_info.config(text="Buchungsfehler!", bg="red")
            self.master.after(2000, self.logout)

    def logout(self):
        if self.timeout_job:
            self.master.after_cancel(self.timeout_job)
            self.timeout_job = None
            
        self.current_user = None
        self.frame_auswahl.pack_forget()
        self.frame_start.pack(fill="both", expand=True)
        self.lbl_start.config(text="Bitte Chip\nvorhalten...", fg="white")

if __name__ == "__main__":
    root = tk.Tk()
    app = KaffeeSystem(root)
    root.mainloop()