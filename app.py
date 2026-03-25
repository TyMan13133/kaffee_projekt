from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import sqlite3
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'supergeheimeschluessel'

import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
# ... deine anderen Imports ...

app = Flask(__name__)
app.secret_key = 'supergeheimeschluessel'

# --- ABSOLUTER PFAD ZUR DATENBANK (WICHTIG FÜR ECHTE SERVER) ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_NAME = os.path.join(BASE_DIR, "kaffee.db")

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    # Stelle sicher, dass die Settings-Tabelle immer existiert!
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    return conn

def get_prediction_stats(conn):
    try:
        row_gramm = conn.execute("SELECT value FROM settings WHERE key='gramm_pro_tasse'").fetchone()
        gramm_pro_tasse = float(row_gramm[0]) if row_gramm else 12.0
    except Exception:
        gramm_pro_tasse = 12.0
        
    # KORREKTUR: Alles komplett über die Datenbank-Zeit berechnen (Zeitzonen ignorieren!)
    times = conn.execute("""
        SELECT 
            COALESCE((SELECT value FROM settings WHERE key='reset_datum'), '2000-01-01 00:00:00') as reset_time,
            datetime('now', '-100 days') as hundred_days_ago,
            datetime('now') as db_now
    """).fetchone()
    
    reset_str = times['reset_time']
    hundred_str = times['hundred_days_ago']
    db_now_str = times['db_now']
    
    # Das neuere Datum gewinnt
    start_date_str = max(reset_str, hundred_str)
    
    # Exakte Tage ausrechnen (nimmt die SQLite-Funktion julianday für exakte Kommazahlen)
    days_passed_query = conn.execute("SELECT julianday(?) - julianday(?)", (db_now_str, start_date_str)).fetchone()[0]
    days_passed = max(days_passed_query, 1.0)
    
    stats = {}
    sorten = [
        ('Koffein', 'KAUF_KOFFEIN', 'Schwarz'), 
        ('Entkoffeiniert', 'KAUF_ENTKOFFEINIERT', 'Decaf')
    ]
    
    for sorte_name, kauf_typ, text_match in sorten:
        bohnen_in = conn.execute("SELECT SUM(menge_gramm) FROM bohnen_log WHERE sorte=?", (sorte_name,)).fetchone()[0] or 0
        tassen_gesamt = conn.execute("SELECT COUNT(*) FROM transaktionen WHERE typ=? OR (typ='KAUF' AND beschreibung LIKE ?)", (kauf_typ, f'%{text_match}%')).fetchone()[0] or 0
        bestand = bohnen_in - (tassen_gesamt * gramm_pro_tasse)
        
        # HIER zählten die Kaffees vorher nicht, weil start_date_str durch Python in der "Zukunft" lag!
        tassen_zeitraum = conn.execute("SELECT COUNT(*) FROM transaktionen WHERE zeitstempel >= ? AND (typ=? OR (typ='KAUF' AND beschreibung LIKE ?))", (start_date_str, kauf_typ, f'%{text_match}%')).fetchone()[0] or 0
        
        tassen_pro_tag = tassen_zeitraum / days_passed
        tage_bis_leer = (bestand / (tassen_pro_tag * gramm_pro_tasse)) if tassen_pro_tag > 0 else 999
        
        stats[sorte_name] = {
            'bestand': int(bestand),
            'tassen_pro_tag': round(tassen_pro_tag, 1),
            'tage_bis_leer': int(tage_bis_leer)
        }
    
    whale_user = conn.execute("SELECT name, saldo FROM users WHERE is_admin = 0 ORDER BY saldo ASC LIMIT 1").fetchone()
    
    return {
        'sorten_stats': stats, 
        'gramm_pro_tasse': gramm_pro_tasse,
        'empfehlung_name': whale_user['name'] if whale_user else "Niemand",
        'empfehlung_saldo': whale_user['saldo'] if whale_user else 0.0
    }        

def get_financial_health(conn):
    guthaben_summe = conn.execute("SELECT SUM(saldo) FROM users WHERE saldo > 0").fetchone()[0] or 0
    schulden_summe = conn.execute("SELECT SUM(saldo) FROM users WHERE saldo < 0").fetchone()[0] or 0
    return {
        'summe_guthaben': guthaben_summe,
        'summe_schulden': schulden_summe,
        'bilanz': guthaben_summe + schulden_summe
    }

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, name, is_admin, saldo):
        self.id = id
        self.name = name
        self.is_admin = is_admin
        self.saldo = saldo

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if u:
        return User(u['id'], u['name'], u['is_admin'], u['saldo'])
    return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form['name']
        password = request.form['password']
        conn = get_db()
        user_data = conn.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()
        conn.close()
        
        if user_data and check_password_hash(user_data['password_hash'], password):
            user_obj = User(user_data['id'], user_data['name'], user_data['is_admin'], user_data['saldo'])
            login_user(user_obj)
            return redirect(url_for('dashboard'))
        else:
            flash('Login fehlgeschlagen. Name oder Passwort falsch.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    transaktionen = conn.execute("SELECT * FROM transaktionen WHERE user_id = ? ORDER BY zeitstempel DESC LIMIT 10", (current_user.id,)).fetchall()
    curr_saldo = conn.execute("SELECT saldo FROM users WHERE id = ?", (current_user.id,)).fetchone()[0]
    stats = get_prediction_stats(conn)
    conn.close()
    return render_template('dashboard.html', transaktionen=transaktionen, saldo=curr_saldo, stats=stats)

@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin: return "Zugriff verweigert", 403
    conn = get_db()
    users = conn.execute("SELECT * FROM users ORDER BY saldo ASC").fetchall()
    finanzen = get_financial_health(conn)
    # Gebe die aktuellen Settings an das Admin-Template weiter
    try:
        row_gramm = conn.execute("SELECT value FROM settings WHERE key='gramm_pro_tasse'").fetchone()
        gramm_pro_tasse = float(row_gramm[0]) if row_gramm else 12.0
    except Exception:
        gramm_pro_tasse = 12.0
        
    settings = {'gramm_pro_tasse': gramm_pro_tasse}
    conn.close()
    return render_template('admin.html', users=users, finanzen=finanzen, settings=settings)

@app.route('/admin/action', methods=['POST'])
@login_required
def admin_action():
    if not current_user.is_admin: return "Verboten", 403
    aktion = request.form['aktion']
    conn = get_db()
    
    try:
        if aktion == 'new_user':
            try:
                pw = generate_password_hash(request.form['password'])
                rfid = request.form['rfid'] if request.form['rfid'] else None
                conn.execute("INSERT INTO users (name, password_hash, rfid_uid) VALUES (?,?,?)", (request.form['name'], pw, rfid))
                flash(f"User {request.form['name']} angelegt")
            except sqlite3.IntegrityError: 
                flash("Fehler: Name oder RFID existiert schon!")

        elif aktion == 'edit_user':
            uid = request.form['user_id']
            name = request.form['name']
            rfid = request.form['rfid'] if request.form['rfid'] else None
            saldo = float(request.form['saldo'])
            try:
                conn.execute("UPDATE users SET name=?, rfid_uid=?, saldo=? WHERE id=?", (name, rfid, saldo, uid))
                flash(f"User {name} aktualisiert!")
            except sqlite3.IntegrityError:
                flash("Fehler: Name oder RFID ist bereits vergeben.")

        elif aktion == 'delete_user':
            uid = request.form['user_id']
            conn.execute("DELETE FROM users WHERE id=?", (uid,))
            flash("Benutzer gelöscht.")

        elif aktion == 'geld_ein':
            uid = request.form['user_id']
            betrag = float(request.form['betrag'])
            if betrag < 0:
                betrag_positiv = abs(betrag)
                conn.execute("UPDATE users SET saldo = saldo - ? WHERE id=?", (betrag_positiv, uid))
                conn.execute("INSERT INTO transaktionen (user_id, typ, beschreibung, betrag) VALUES (?, 'AUSZAHLUNG', 'Barauszahlung', ?)", (uid, -betrag_positiv))
                flash(f"Barauszahlung ({betrag_positiv}€) verbucht.")
            else:
                conn.execute("UPDATE users SET saldo = saldo + ? WHERE id=?", (betrag, uid))
                conn.execute("INSERT INTO transaktionen (user_id, typ, beschreibung, betrag) VALUES (?, 'EINZAHLUNG', 'Bar Einzahlung', ?)", (uid, betrag))
                flash(f"Einzahlung ({betrag}€) verbucht.")

        elif aktion == 'bohnen':
            uid = request.form['user_id']
            menge, preis, sorte = int(request.form['menge']), float(request.form['preis']), request.form['sorte']
            conn.execute("INSERT INTO bohnen_log (user_id, menge_gramm, preis, sorte) VALUES (?,?,?,?)", (uid, menge, preis, sorte))
            conn.execute("UPDATE users SET saldo = saldo + ? WHERE id=?", (preis, uid))
            conn.execute("INSERT INTO transaktionen (user_id, typ, beschreibung, betrag) VALUES (?, 'BOHNEN', ?, ?)", (uid, f'Bohnen {menge}g ({sorte})', preis))
            flash("Bohnen erfasst")

        elif aktion == 'sonstiges':
            uid, betrag, kategorie = request.form['user_id'], float(request.form['betrag']), request.form['kategorie']
            conn.execute("UPDATE users SET saldo = saldo + ? WHERE id=?", (betrag, uid))
            conn.execute("INSERT INTO transaktionen (user_id, typ, beschreibung, betrag) VALUES (?, 'SONSTIGES', ?, ?)", (uid, f'Auslage: {kategorie}', betrag))
            flash(f"Auslage für {kategorie} erstattet.")
            
        # DIE WICHTIGEN ÄNDERUNGEN SIND HIER: Namen an admin.html angepasst!
        elif aktion == 'set_gramm_pro_tasse':
            neue_gramm = float(request.form['gramm_pro_tasse'])
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('gramm_pro_tasse', ?)", (neue_gramm,))
            flash(f'Gramm pro Tasse auf {neue_gramm}g aktualisiert!')
            
        elif aktion == 'reset_verbrauch':
            # KORREKTUR: Nutze CURRENT_TIMESTAMP der Datenbank, statt der Python-Zeit!
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('reset_datum', CURRENT_TIMESTAMP)")
            flash('Durchschnittsverbrauch wurde erfolgreich zurückgesetzt!')
            
    except Exception as e:
        flash(f"Ein unerwarteter Fehler ist aufgetreten: {e}")

    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route('/history')
@login_required
def history():
    conn = get_db()
    buchungen = conn.execute('''
        SELECT t.zeitstempel, COALESCE(u.name, 'Unbekannte Karte') as name, t.beschreibung, t.betrag, t.typ 
        FROM transaktionen t
        LEFT JOIN users u ON t.user_id = u.id 
        ORDER BY t.zeitstempel DESC LIMIT 50
    ''').fetchall()
    conn.close()
    return render_template('history.html', buchungen=buchungen)

@app.route('/api/check_card/<uid>')
def api_check_card(uid):
    clean_uid = uid.replace(" ", "").upper()
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE replace(rfid_uid, ' ', '') = ?", (clean_uid,)).fetchone()
    
    if user:
        conn.close()
        return jsonify({
            'status': 'ok',
            'user_id': user['id'],
            'name': user['name'],
            'saldo': user['saldo']
        })
    else:
        conn.execute("INSERT INTO transaktionen (user_id, typ, beschreibung, betrag) VALUES (NULL, 'WARNUNG', ?, 0.0)", 
                     (f"RFID Scan fehlgeschlagen: {clean_uid}",))
        conn.commit()
        conn.close()
        return jsonify({'status': 'unknown', 'uid': clean_uid})

@app.route('/api/book', methods=['POST'])
def api_book():
    data = request.get_json()
    user_id = data.get('user_id')
    produkt = data.get('product', '')
    preis = float(data.get('price'))
    
    kauf_typ = 'KAUF_ENTKOFFEINIERT' if 'entkoffeiniert' in produkt.lower() or 'decaf' in produkt.lower() else 'KAUF_KOFFEIN'
    
    conn = get_db()
    conn.execute("UPDATE users SET saldo = saldo - ? WHERE id = ?", (preis, user_id))
    conn.execute("INSERT INTO transaktionen (user_id, typ, beschreibung, betrag) VALUES (?, ?, ?, ?)", (user_id, kauf_typ, produkt, -preis))
    conn.commit()
    new_saldo = conn.execute("SELECT saldo FROM users WHERE id = ?", (user_id,)).fetchone()[0]
    conn.close()
    
    return jsonify({'status': 'success', 'new_saldo': new_saldo})

if __name__ == "__main__":
    from waitress import serve
    print("Server startet auf Port 5000... ")
    serve(app, host='0.0.0.0', port=5000)
