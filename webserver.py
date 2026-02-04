from flask import Flask, render_template, request, redirect, url_for
import sqlite3

app = Flask(__name__)
DB_NAME = "kaffee.db"

# --- Konfiguration für Nachkauf-Empfehlung ---
MAX_KAFFEE_BOHNEN = 100 # Angenommen: 1 Packung reicht für 100 Tassen
KRITISCHE_GRENZE = 20   # Warnung ab 20 restlichen Tassen

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row # Damit wir Spaltennamen benutzen können
    return conn

# 1. Startseite & Handlungsempfehlung
@app.route('/')
def index():
    conn = get_db_connection()
    
    # Berechnen, wie viel Kaffee getrunken wurde (seit letztem Reset/Auffüllen)
    # Vereinfacht: Wir zählen einfach alle "Kaffee"-Buchungen
    count = conn.execute("SELECT COUNT(*) FROM buchungen WHERE produkt LIKE 'Kaffee%'").fetchone()[0]
    
    restliche_tassen = MAX_KAFFEE_BOHNEN - (count % MAX_KAFFEE_BOHNEN)
    nachkauf_noetig = restliche_tassen < KRITISCHE_GRENZE
    
    conn.close()
    return render_template('index.html', rest=restliche_tassen, warnung=nachkauf_noetig)

# 2. Buchungsliste (Historie)
@app.route('/history')
def history():
    conn = get_db_connection()
    # Holt die letzten 50 Buchungen inkl. Namen des Users
    buchungen = conn.execute('''
        SELECT buchungen.zeitstempel, users.name, buchungen.produkt, buchungen.preis 
        FROM buchungen 
        JOIN users ON buchungen.user_id = users.id 
        ORDER BY buchungen.zeitstempel DESC LIMIT 50
    ''').fetchall()
    conn.close()
    return render_template('history.html', buchungen=buchungen)

# 3. Admin: Neuer Benutzer
@app.route('/admin', methods=('GET', 'POST'))
def admin():
    if request.method == 'POST':
        name = request.form['name']
        rfid = request.form['rfid']
        
        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO users (name, rfid_uid) VALUES (?, ?)", (name, rfid))
            conn.commit()
            status = "Benutzer angelegt!"
        except:
            status = "Fehler: RFID existiert wohl schon."
        conn.close()
        return render_template('admin.html', status=status)
        
    return render_template('admin.html')

if __name__ == '__main__':
    # host='0.0.0.0' macht den Server im ganzen WLAN erreichbar!
    app.run(debug=True, host='0.0.0.0', port=5000)
