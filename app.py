from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import sqlite3
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'supergeheimeschluessel' # Wichtig für Sessions

# --- KONFIGURATION ---
GRAMM_PRO_TASSE = 12  # Wie viel Gramm verbraucht ein Kaffee?
DB_NAME = "kaffee.db"

# --- HELPER FUNKTIONEN ---

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def get_prediction_stats(conn):
    # 1. Aktuellen Lagerbestand berechnen
    total_bohnen_in = conn.execute("SELECT SUM(menge_gramm) FROM bohnen_log").fetchone()[0] or 0
    total_tassen_verkauft = conn.execute("SELECT COUNT(*) FROM transaktionen WHERE typ = 'KAUF'").fetchone()[0] or 0
    
    verbrauch_total = total_tassen_verkauft * GRAMM_PRO_TASSE
    aktueller_bestand = total_bohnen_in - verbrauch_total
    
    # 2. Prädiktion
    dreissig_tage_her = datetime.now() - timedelta(days=30)
    tassen_letzte_30_tage = conn.execute("""
        SELECT COUNT(*) FROM transaktionen 
        WHERE typ = 'KAUF' AND zeitstempel > ?
    """, (dreissig_tage_her,)).fetchone()[0] or 0
    
    tassen_pro_tag = max(tassen_letzte_30_tage / 30, 0.1) 
    verbrauch_pro_tag_gramm = tassen_pro_tag * GRAMM_PRO_TASSE
    
    tage_bis_leer = aktueller_bestand / verbrauch_pro_tag_gramm
    datum_leer = datetime.now() + timedelta(days=tage_bis_leer)
    
    # 3. Kaufempfehlung (Geringstes Guthaben)
    # ÄNDERUNG PUNKT 3: Admins (is_admin=1) werden hier ausgeschlossen!
    whale_user = conn.execute("SELECT name, saldo FROM users WHERE is_admin = 0 ORDER BY saldo ASC LIMIT 1").fetchone()
    
    return {
        'bestand_gramm': int(aktueller_bestand),
        'tage_bis_leer': int(tage_bis_leer),
        'datum_leer': datum_leer.strftime('%d.%m.%Y'),
        'tassen_pro_tag': round(tassen_pro_tag, 1),
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

# Login Konfiguration
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

# --- ROUTEN ---

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
    conn.close()
    return render_template('admin.html', users=users, finanzen=finanzen)

# --- ZENTRALE ADMIN AKTIONEN ---
@app.route('/admin/action', methods=['POST'])
@login_required
def admin_action():
    if not current_user.is_admin: return "Verboten", 403
    
    aktion = request.form['aktion']
    conn = get_db()
    
    try:
        # 1. Neuer User
        if aktion == 'new_user':
            try:
                pw = generate_password_hash(request.form['password'])
                rfid = request.form['rfid'] if request.form['rfid'] else None
                conn.execute("INSERT INTO users (name, password_hash, rfid_uid) VALUES (?,?,?)", 
                             (request.form['name'], pw, rfid))
                flash(f"User {request.form['name']} angelegt")
            except sqlite3.IntegrityError: 
                flash("Fehler: Name oder RFID existiert schon!")

        # 2. User Bearbeiten
        elif aktion == 'edit_user':
            uid = request.form['user_id']
            name = request.form['name']
            rfid = request.form['rfid'] if request.form['rfid'] else None
            # Achtung: Saldo Änderung hier ist ein "Hard Reset", keine Transaktion.
            saldo = float(request.form['saldo'])
            
            try:
                conn.execute("UPDATE users SET name=?, rfid_uid=?, saldo=? WHERE id=?", 
                             (name, rfid, saldo, uid))
                flash(f"User {name} aktualisiert!")
            except sqlite3.IntegrityError:
                flash("Fehler: Name oder RFID ist bereits vergeben.")

        # 3. User Löschen
        elif aktion == 'delete_user':
            uid = request.form['user_id']
            conn.execute("DELETE FROM users WHERE id=?", (uid,))
            flash("Benutzer gelöscht.")

        # 4. Geld Ein-/Auszahlen
        elif aktion == 'geld_ein':
            uid = request.form['user_id']
            betrag = float(request.form['betrag'])
            
            # ÄNDERUNG PUNKT 1: Automatische Textwahl
            buchungstext = "Bar Einzahlung"
            if betrag < 0:
                buchungstext = "Barauszahlung"
            
            conn.execute("UPDATE users SET saldo = saldo + ? WHERE id=?", (betrag, uid))
            conn.execute("INSERT INTO transaktionen (user_id, typ, beschreibung, betrag) VALUES (?, 'EINZAHLUNG', ?, ?)", 
                         (uid, buchungstext, betrag))
            
            if betrag < 0:
                flash(f"Barauszahlung ({betrag}€) verbucht.")
            else:
                flash(f"Einzahlung ({betrag}€) verbucht.")

        # 5. Bohnen Lieferung
        elif aktion == 'bohnen':
            uid = request.form['user_id']
            menge = int(request.form['menge'])
            preis = float(request.form['preis'])
            sorte = request.form['sorte']
            conn.execute("INSERT INTO bohnen_log (user_id, menge_gramm, preis, sorte) VALUES (?,?,?,?)", (uid, menge, preis, sorte))
            conn.execute("UPDATE users SET saldo = saldo + ? WHERE id=?", (preis, uid))
            conn.execute("INSERT INTO transaktionen (user_id, typ, beschreibung, betrag) VALUES (?, 'BOHNEN', ?, ?)", 
                         (uid, f'Bohnen {menge}g', preis))
            flash("Bohnen erfasst")

        # 6. ÄNDERUNG PUNKT 2: Zubehör / Sonstiges
        elif aktion == 'sonstiges':
            uid = request.form['user_id']
            betrag = float(request.form['betrag'])
            kategorie = request.form['kategorie'] # Filter, Entkalker etc.
            
            # User bekommt das Geld gutgeschrieben (Gutschrift für Auslage)
            conn.execute("UPDATE users SET saldo = saldo + ? WHERE id=?", (betrag, uid))
            conn.execute("INSERT INTO transaktionen (user_id, typ, beschreibung, betrag) VALUES (?, 'SONSTIGES', ?, ?)", 
                         (uid, f'Auslage: {kategorie}', betrag))
            flash(f"Auslage für {kategorie} erstattet.")
            
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
        SELECT t.zeitstempel, u.name, t.beschreibung, t.betrag, t.typ 
        FROM transaktionen t
        JOIN users u ON t.user_id = u.id 
        ORDER BY t.zeitstempel DESC LIMIT 50
    ''').fetchall()
    conn.close()
    return render_template('history.html', buchungen=buchungen)

# --- API FÜR TOUCHSCREEN ---
@app.route('/api/check_card/<uid>')
def api_check_card(uid):
    clean_uid = uid.replace(" ", "").upper()
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE replace(rfid_uid, ' ', '') = ?", (clean_uid,)).fetchone()
    conn.close()
    
    if user:
        return jsonify({
            'status': 'ok',
            'user_id': user['id'],
            'name': user['name'],
            'saldo': user['saldo']
        })
    else:
        return jsonify({'status': 'unknown', 'uid': clean_uid})

@app.route('/api/book', methods=['POST'])
def api_book():
    data = request.get_json()
    user_id = data.get('user_id')
    produkt = data.get('product')
    preis = float(data.get('price'))
    
    conn = get_db()
    conn.execute("UPDATE users SET saldo = saldo - ? WHERE id = ?", (preis, user_id))
    conn.execute("INSERT INTO transaktionen (user_id, typ, beschreibung, betrag) VALUES (?, 'KAUF', ?, ?)", 
                 (user_id, produkt, -preis))
    conn.commit()
    new_saldo = conn.execute("SELECT saldo FROM users WHERE id = ?", (user_id,)).fetchone()[0]
    conn.close()
    
    return jsonify({'status': 'success', 'new_saldo': new_saldo})

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
