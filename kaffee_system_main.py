import tkinter as tk
from tkinter import messagebox
from smartcard.System import readers
from smartcard.util import toHexString
import threading
import time
import requests

# --- KONFIGURATION ---
SERVER_URL = "http://localhost:5000"

class KaffeeSystem:
    def __init__(self, master):
        self.master = master
        master.title("Kaffee System")
        master.geometry("480x320")
        # master.attributes('-fullscreen', True) 

        # Variablen
        self.current_user = None 
        self.running = True
        self.rfid_cooldown = False
        
        # ÄNDERUNG PUNKT 4: Variable für den Logout-Timer Job
        self.timeout_job = None

        # --- LAYOUT ---
        self.frame_start = tk.Frame(master, bg="#2c3e50")
        self.frame_auswahl = tk.Frame(master, bg="#ecf0f1")

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
        self.btn_schwarz = tk.Button(self.frame_auswahl, text="Kaffee\nSchwarz\n(0.40€)", bg="#6f4e37", fg="white",
                                     font=("Arial", 16, "bold"), command=lambda: self.buche_produkt("Kaffee Schwarz", 0.40))
        self.btn_schwarz.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        self.btn_decaf = tk.Button(self.frame_auswahl, text="Kaffee\nDecaf\n(0.40€)", bg="#16a085", fg="white",
                                   font=("Arial", 16, "bold"), command=lambda: self.buche_produkt("Kaffee Decaf", 0.40))
        self.btn_decaf.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)
        
        self.btn_logout = tk.Button(self.frame_auswahl, text="Abbrechen", bg="#c0392b", fg="white",
                                    font=("Arial", 14), command=self.logout)
        self.btn_logout.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

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
        
        # ÄNDERUNG PUNKT 4: Timeout starten (20 Sekunden = 20000ms)
        if self.timeout_job:
            self.master.after_cancel(self.timeout_job)
        self.timeout_job = self.master.after(20000, self.logout)

    def buche_produkt(self, produkt_name, preis):
        if not self.current_user: return
        
        # ÄNDERUNG PUNKT 4: Timeout abbrechen, da Interaktion erfolgt ist
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
                # Logout nach 2 Sekunden (wie vorher)
                self.master.after(2000, self.logout)
                
        except Exception as e:
            self.lbl_info.config(text="Buchungsfehler!", bg="red")
            self.master.after(2000, self.logout)

    def logout(self):
        # ÄNDERUNG PUNKT 4: Timer sauber aufräumen
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
