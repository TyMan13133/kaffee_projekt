import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_NAME = 'kaffee.db'

def init_db():
    # Sicherheits-Check: Alte DB löschen, damit die Struktur garantiert stimmt
    if os.path.exists(DB_NAME):
        try:
            os.remove(DB_NAME)
            print(f"Alte Datenbank '{DB_NAME}' gelöscht. Erstelle neu...")
        except PermissionError:
            print("FEHLER: Die Datenbank wird gerade verwendet! Bitte stoppe erst den Server (app.py).")
            return

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # --- NEU: 0. Systemeinstellungen ---
    c.execute('''CREATE TABLE settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )''')
    c.execute("INSERT INTO settings (key, value) VALUES ('gramm_pro_tasse', '12')")
    c.execute("INSERT INTO settings (key, value) VALUES ('reset_datum', '2000-01-01 00:00:00')")

    # 1. User Tabelle (Mit UNIQUE constraint für den Namen!)
    c.execute('''CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    rfid_uid TEXT UNIQUE,
                    password_hash TEXT,
                    is_admin INTEGER DEFAULT 0,
                    saldo REAL DEFAULT 0.0
                )''')
    
    # 2. Transaktionen (Kauf, Einzahlung, Auszahlung, Bohnen, Sonstiges)
    c.execute('''CREATE TABLE transaktionen (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    typ TEXT,
                    beschreibung TEXT,
                    betrag REAL,
                    zeitstempel DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )''')

    # 3. Bohnen-Log (Für Prädiktion)
    c.execute('''CREATE TABLE bohnen_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    menge_gramm INTEGER,
                    preis REAL,
                    sorte TEXT,
                    zeitstempel DATETIME DEFAULT CURRENT_TIMESTAMP
                )''')

    # --- ADMIN USER ERSTELLEN ---
    admin_pw = generate_password_hash("admin123")
    try:
        c.execute("INSERT INTO users (name, rfid_uid, password_hash, is_admin, saldo) VALUES (?, ?, ?, ?, ?)", 
                  ("Administrator", "000000", admin_pw, 1, 0.0))
        print("✅ Admin User erstellt: Benutzer='Administrator', Passwort='admin123'")
    except Exception as e:
        print(f"Fehler beim Admin-Erstellen: {e}")

    # --- TEST USER ERSTELLEN ---
    user_pw = generate_password_hash("user123")
    c.execute("INSERT INTO users (name, rfid_uid, password_hash, is_admin, saldo) VALUES (?, ?, ?, ?, ?)", 
              ("Max Tester", "123456", user_pw, 0, 5.00))
    print("✅ Test-User erstellt: Benutzer='Max Tester', Passwort='user123'")

    conn.commit()
    conn.close()
    print("🚀 Datenbank erfolgreich initialisiert!")

if __name__ == '__main__':
    init_db()