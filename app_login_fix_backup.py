from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Any

from flask import Flask, g, redirect, render_template, request, url_for, flash, session

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "dellicar.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = "dellicar-dev-secret-key"

PASSWORD = "dellicar"

DEFAULT_SETTINGS = {
    "company_name": "DELLICAR AUTOMOTIVE",
    "address": "Via Molinetto di Voltri 1r/7r - GE Voltri",
    "phone": "010 6134992 / 3458787247",
    "email": "dellicar@outlook.it",
    "website": "www.carrozzeriadellicar.it",
    "vat": "02513920997",
}


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_: Any) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = sqlite3.connect(DB_PATH)
    with closing(db.cursor()) as cur:
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
CREATE TABLE IF NOT EXISTS work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_pratica TEXT,
    client_name TEXT,
    phone TEXT,
    email TEXT,
    plate TEXT,
    make TEXT,
    model TEXT,
    vin TEXT,
    color TEXT,
    km TEXT,
    insurance TEXT,
    claim_number TEXT,
    claim_date TEXT,
    work_description TEXT,
    priority TEXT,
    photos_required INTEGER,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                residence TEXT,
                license_number TEXT,
                license_expiry TEXT,
                issued_by TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS vehicles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                make_model TEXT NOT NULL,
                plate TEXT NOT NULL UNIQUE,
                km INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Disponibile',
                fuel TEXT NOT NULL DEFAULT 'Pieno',
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS rentals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_number TEXT NOT NULL UNIQUE,
                contract_date TEXT NOT NULL,
                client_id INTEGER NOT NULL,
                vehicle_id INTEGER NOT NULL,
                delivery_date TEXT,
                return_date TEXT,
                km_out INTEGER DEFAULT 0,
                km_in INTEGER,
                fuel_out TEXT,
                fuel_in TEXT,
                status TEXT NOT NULL DEFAULT 'Attivo',
                damage_front INTEGER DEFAULT 0,
                damage_rear INTEGER DEFAULT 0,
                damage_left_front INTEGER DEFAULT 0,
                damage_left_rear INTEGER DEFAULT 0,
                damage_right_front INTEGER DEFAULT 0,
                damage_right_rear INTEGER DEFAULT 0,
                damage_notes TEXT,
                return_notes TEXT,
                client_signature TEXT,
                dellicar_signature TEXT,
                FOREIGN KEY (client_id) REFERENCES clients(id),
                FOREIGN KEY (vehicle_id) REFERENCES vehicles(id)
            );
            """
        )
        for key, value in DEFAULT_SETTINGS.items():
            cur.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
                (key, value),
            )
    db.commit()
    db.close()


def seed_demo() -> None:
    db = get_db()
    count = db.execute("SELECT COUNT(*) AS c FROM clients").fetchone()["c"]
    if count:
        return

    db.executemany(
        """
        INSERT INTO clients(full_name, phone, email, residence, license_number, license_expiry, issued_by, notes)
        VALUES(?,?,?,?,?,?,?,?)
        """,
        [
            (
                "Mario Rossi",
                "3331234567",
                "mario@email.it",
                "Genova",
                "GE1234567X",
                "2028-09-30",
                "Motorizzazione GE",
                "Cliente demo",
            ),
            (
                "Luca Bianchi",
                "3479876543",
                "luca@email.it",
                "Savona",
                "SV9876543Y",
                "2027-03-15",
                "Motorizzazione SV",
                "Cliente demo",
            ),
        ],
    )
    db.executemany(
        """
        INSERT INTO vehicles(make_model, plate, km, status, fuel, notes)
        VALUES(?,?,?,?,?,?)
        """,
        [
            ("Fiat Panda", "AB123CD", 82441, "Disponibile", "1/2", ""),
            ("Fiat 500", "GH456KL", 61220, "Disponibile", "3/4", ""),
            ("Toyota Yaris", "TT882YY", 44103, "Manutenzione", "Pieno", ""),
        ],
    )
    db.commit()


def get_settings() -> dict[str, str]:
    db = get_db()
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    data = {row["key"]: row["value"] for row in rows}
    for k, v in DEFAULT_SETTINGS.items():
        data.setdefault(k, v)
    return data


def next_contract_number() -> str:
    year = date.today().year
    db = get_db()
    rows = db.execute(
        "SELECT contract_number FROM rentals WHERE contract_number LIKE ?",
        (f"NOL-{year}-%",),
    ).fetchall()
    nums = []
    for row in rows:
        try:
            nums.append(int(row["contract_number"].split("-")[-1]))
        except Exception:
            pass
    next_num = max(nums, default=0) + 1
    return f"NOL-{year}-{next_num:03d}"


def fetch_dashboard() -> dict[str, Any]:
    db = get_db()
    today_str = date.today().isoformat()
    return {
        "available": db.execute(
            "SELECT COUNT(*) AS c FROM vehicles WHERE status='Disponibile'"
        ).fetchone()["c"],
        "active": db.execute(
            "SELECT COUNT(*) AS c FROM rentals WHERE status='Attivo'"
        ).fetchone()["c"],
        "due_today": db.execute(
            "SELECT COUNT(*) AS c FROM rentals WHERE status='Attivo' AND return_date=?",
            (today_str,),
        ).fetchone()["c"],
        "clients": db.execute("SELECT COUNT(*) AS c FROM clients").fetchone()["c"],
    }


@app.context_processor
def inject_globals() -> dict[str, Any]:
    return {"company": get_settings(), "today": date.today().isoformat()}


@app.route("/")
def dashboard() -> str:
    if not session.get("logged"):
        return redirect("/login")

    db = get_db()
    metrics = fetch_dashboard()
    active_rentals = db.execute(
        """
        SELECT rentals.*, clients.full_name, vehicles.make_model, vehicles.plate
        FROM rentals
        JOIN clients ON clients.id = rentals.client_id
        JOIN vehicles ON vehicles.id = rentals.vehicle_id
        WHERE rentals.status='Attivo'
        ORDER BY rentals.id DESC
        LIMIT 8
        """
    ).fetchall()
    vehicles = db.execute(
        "SELECT * FROM vehicles ORDER BY make_model ASC LIMIT 8"
    ).fetchall()
    return render_template(
        "dashboard.html",
        metrics=metrics,
        active_rentals=active_rentals,
        vehicles=vehicles,
    )


@app.route("/clients", methods=["GET", "POST"])
def clients() -> str:
    db = get_db()
    if request.method == "POST":
        form = request.form
        db.execute(
            """
            INSERT INTO clients(full_name, phone, email, residence, license_number, license_expiry, issued_by, notes)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                form.get("full_name", "").strip(),
                form.get("phone", "").strip(),
                form.get("email", "").strip(),
                form.get("residence", "").strip(),
                form.get("license_number", "").strip(),
                form.get("license_expiry", "").strip(),
                form.get("issued_by", "").strip(),
                form.get("notes", "").strip(),
            ),
        )
        db.commit()
        flash("Cliente salvato.")
        return redirect(url_for("clients"))

    rows = db.execute("SELECT * FROM clients ORDER BY id DESC").fetchall()
    return render_template("clients.html", clients=rows)


@app.route("/clients/<int:client_id>/delete", methods=["POST"])
def delete_client(client_id: int):
    db = get_db()
    db.execute("DELETE FROM clients WHERE id=?", (client_id,))
    db.commit()
    flash("Cliente eliminato.")
    return redirect(url_for("clients"))


@app.route("/vehicles", methods=["GET", "POST"])
def vehicles() -> str:
    db = get_db()
    if request.method == "POST":
        form = request.form
        db.execute(
            """
            INSERT INTO vehicles(make_model, plate, km, status, fuel, notes)
            VALUES(?,?,?,?,?,?)
            """,
            (
                form.get("make_model", "").strip(),
                form.get("plate", "").strip().upper(),
                int(form.get("km", 0) or 0),
                form.get("status", "Disponibile"),
                form.get("fuel", "Pieno"),
                form.get("notes", "").strip(),
            ),
        )
        db.commit()
        flash("Veicolo salvato.")
        return redirect(url_for("vehicles"))

    rows = db.execute("SELECT * FROM vehicles ORDER BY id DESC").fetchall()
    return render_template("vehicles.html", vehicles=rows)


@app.route("/vehicles/<int:vehicle_id>/delete", methods=["POST"])
def delete_vehicle(vehicle_id: int):
    db = get_db()
    db.execute("DELETE FROM vehicles WHERE id=?", (vehicle_id,))
    db.commit()
    flash("Veicolo eliminato.")
    return redirect(url_for("vehicles"))


@app.route("/rentals", methods=["GET", "POST"])
def rentals() -> str:
    db = get_db()
    if request.method == "POST":
        form = request.form
        client_id = int(form.get("client_id"))
        vehicle_id = int(form.get("vehicle_id"))
        contract_number = next_contract_number()
        db.execute(
            """
            INSERT INTO rentals(
                contract_number, contract_date, client_id, vehicle_id,
                delivery_date, return_date, km_out, fuel_out, status,
                damage_front, damage_rear, damage_left_front, damage_left_rear,
                damage_right_front, damage_right_rear, damage_notes,
                client_signature, dellicar_signature
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                contract_number,
                form.get("contract_date") or date.today().isoformat(),
                client_id,
                vehicle_id,
                form.get("delivery_date", ""),
                form.get("return_date", ""),
                int(form.get("km_out", 0) or 0),
                form.get("fuel_out", "Pieno"),
                form.get("status", "Attivo"),
                1 if form.get("damage_front") else 0,
                1 if form.get("damage_rear") else 0,
                1 if form.get("damage_left_front") else 0,
                1 if form.get("damage_left_rear") else 0,
                1 if form.get("damage_right_front") else 0,
                1 if form.get("damage_right_rear") else 0,
                form.get("damage_notes", "").strip(),
                form.get("client_signature", "").strip(),
                form.get("dellicar_signature", "").strip(),
            ),
        )
        db.execute(
            "UPDATE vehicles SET status='Noleggiata', km=?, fuel=? WHERE id=?",
            (
                int(form.get("km_out", 0) or 0),
                form.get("fuel_out", "Pieno"),
                vehicle_id,
            ),
        )
        db.commit()
        flash(f"Noleggio creato: {contract_number}")
        return redirect(url_for("rentals"))

    rows = db.execute(
        """
        SELECT rentals.*, clients.full_name, vehicles.make_model, vehicles.plate
        FROM rentals
        JOIN clients ON clients.id = rentals.client_id
        JOIN vehicles ON vehicles.id = rentals.vehicle_id
        ORDER BY rentals.id DESC
        """
    ).fetchall()
    clients_rows = db.execute("SELECT id, full_name FROM clients ORDER BY full_name").fetchall()
    vehicle_rows = db.execute(
        "SELECT id, make_model, plate, km FROM vehicles ORDER BY make_model"
    ).fetchall()
    return render_template(
        "rentals.html",
        rentals=rows,
        clients=clients_rows,
        vehicles=vehicle_rows,
        next_contract=next_contract_number(),
    )


@app.route("/rentals/<int:rental_id>")
def rental_detail(rental_id: int) -> str:
    db = get_db()
    row = db.execute(
        """
        SELECT rentals.*, clients.full_name, clients.phone, clients.email, clients.residence,
               clients.license_number, clients.license_expiry, clients.issued_by,
               vehicles.make_model, vehicles.plate
        FROM rentals
        JOIN clients ON clients.id = rentals.client_id
        JOIN vehicles ON vehicles.id = rentals.vehicle_id
        WHERE rentals.id=?
        """,
        (rental_id,),
    ).fetchone()
    if row is None:
        return redirect(url_for("rentals"))
    return render_template("contract.html", rental=row)


@app.route("/rentals/<int:rental_id>/close", methods=["GET", "POST"])
def close_rental(rental_id: int) -> str:
    db = get_db()
    rental = db.execute(
        """
        SELECT rentals.*, clients.full_name, vehicles.make_model, vehicles.plate
        FROM rentals
        JOIN clients ON clients.id = rentals.client_id
        JOIN vehicles ON vehicles.id = rentals.vehicle_id
        WHERE rentals.id=?
        """,
        (rental_id,),
    ).fetchone()
    if rental is None:
        return redirect(url_for("rentals"))

    if request.method == "POST":
        km_in = int(request.form.get("km_in", 0) or 0)
        fuel_in = request.form.get("fuel_in", "Pieno")
        notes = request.form.get("return_notes", "").strip()
        db.execute(
            """
            UPDATE rentals
            SET status='Chiuso', km_in=?, fuel_in=?, return_notes=?
            WHERE id=?
            """,
            (km_in, fuel_in, notes, rental_id),
        )
        db.execute(
            "UPDATE vehicles SET status='Disponibile', km=?, fuel=? WHERE id=?",
            (km_in or rental["km_out"], fuel_in, rental["vehicle_id"]),
        )
        db.commit()
        flash("Noleggio chiuso.")
        return redirect(url_for("rentals"))

    return render_template("close_rental.html", rental=rental)


@app.route("/settings", methods=["GET", "POST"])
def settings() -> str:
    db = get_db()
    if request.method == "POST":
        for key in DEFAULT_SETTINGS:
            db.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, request.form.get(key, "").strip()),
            )
        db.commit()
        flash("Impostazioni aggiornate.")
        return redirect(url_for("settings"))
    return render_template("settings.html", settings=get_settings())


@app.route("/seed-demo", methods=["POST"])
def seed_demo_route():
    seed_demo()
    flash("Dati demo caricati.")
    return redirect(url_for("dashboard"))

@app.route("/scheda-lavori", methods=["GET", "POST"])
def scheda_lavori():

    if request.method == "POST":
        db = get_db()
        last = db.execute("SELECT id FROM work_orders ORDER BY id DESC LIMIT 1").fetchone()

        if last:
            numero_pratica = f"DL-{last['id']+1:04d}"
        else:
            numero_pratica = "DL-0001"

        db.execute(
            """
            INSERT INTO work_orders (
                numero_pratica,
                client_name,
                plate,
                marca,
                modello,
                colore,
                work_description,
                priority,
                notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                 numero_pratica,
                 request.form.get("client_name"),
                 request.form.get("plate"),
                 request.form.get("make_model"),
                 "",
                 request.form.get("colore"),
                 request.form.get("work_description"),
                 request.form.get("priority"),
                 request.form.get("notes"),
            ),
        )

        db.commit()

        return redirect(url_for("dashboard"))

    db = get_db()
    last = db.execute("SELECT id FROM work_orders ORDER BY id DESC LIMIT 1").fetchone()

    if last:
        prossimo_numero_pratica = f"DL-{last['id']+1:04d}"
    else:
        prossimo_numero_pratica = "DL-0001"

    return render_template("scheda_lavori.html", prossimo_numero_pratica=prossimo_numero_pratica)

@app.route("/scheda/<int:id>")
def apri_scheda(id):
    db = get_db()
    scheda = db.execute(
        "SELECT * FROM work_orders WHERE id = ?", (id,)
    ).fetchone()

    if not scheda:
        return "Scheda non trovata"

    return render_template("scheda_dettaglio.html", scheda=scheda)

@app.route("/schede-lavori")
def archivio_schede_lavori():
    db = get_db()

    search = request.args.get("search")

    if search:
        work_orders = db.execute("""
            SELECT id, client_name, plate, priority, created_at
            FROM work_orders
            WHERE plate LIKE ? OR client_name LIKE ?
            ORDER BY id DESC
         """, (f"%{search}%", f"%{search}%")).fetchall()
    else:
        work_orders = db.execute("""
            SELECT id, client_name, plate, priority, created_at
            FROM work_orders
            ORDER BY id DESC
        """).fetchall()
    return render_template("work_orders.html", work_orders=work_orders)


@app.route("/schede-lavori/<int:id>")
def apri_scheda_lavori(id):
    db = get_db()

    scheda = db.execute(
        """
        SELECT *
        FROM work_orders
        WHERE id = ?
        """,
        (id,)
    ).fetchone()

    return render_template("work_order_detail.html", w=scheda)

@app.route("/schede-lavori/<int:id>/modifica", methods=["GET","POST"])
def modifica_scheda(id):


    db = get_db()

    if request.method == "POST":
        client_name = request.form.get("client_name")
        plate = request.form.get("plate")
        priority = request.form.get("priority")
        work_description = request.form.get("work_description")
        notes = request.form.get("notes")

        db.execute("""
        UPDATE work_orders
        SET client_name=?, plate=?, priority=?, work_description=?, notes=?
        WHERE id=?
        """, (client_name, plate, priority, work_description, notes, id))

        db.commit()

        return redirect(url_for("apri_scheda_lavori", id=id))

    scheda = db.execute(
        "SELECT * FROM work_orders WHERE id = ?",
        (id,)
    ).fetchone()

    return render_template("edit_work_order.html", w=scheda)

@app.route("/schede-lavori/<int:id>/elimina")
def elimina_scheda(id):
    db = get_db()

    db.execute("DELETE FROM work_orders WHERE id = ?", (id,))
    db.commit()

    return redirect(url_for("archivio_schede_lavori"))


@app.route("/search_rentals")
def search_rentals():

    plate = request.args.get("plate", "")
    search_date = request.args.get("date")

    db = get_db()

    query = """
    SELECT rentals.*, clients.full_name, vehicles.plate
    FROM rentals
    LEFT JOIN clients ON rentals.client_id = clients.id
    JOIN vehicles ON rentals.vehicle_id = vehicles.id
    WHERE vehicles.plate LIKE ?
    """

    params = ["%" + plate + "%"]

    if search_date:
        query += """
        AND date(rentals.delivery_date) <= date(?)
        AND (rentals.return_date IS NULL OR date(rentals.return_date) >= 
date(?))
        """
        params.extend([search_date, search_date])

    query += " ORDER BY rentals.delivery_date DESC"

    results = db.execute(query, params).fetchall()

    return render_template(
        "search_rentals.html",
        results=results,
        plate=plate,
        search_date=search_date
    )

@app.route("/search")
def search():
    q = request.args.get("search", "").strip()
    date = request.args.get("date", "").strip()

    db = get_db()
    like = f"%{q}%"

    work_orders = db.execute("""
        SELECT *
        FROM work_orders
        WHERE client_name LIKE ?
           OR plate LIKE ?
           OR IFNULL(marca,'') LIKE ?
           OR IFNULL(modello,'') LIKE ?
        ORDER BY id DESC
    """, (like, like, like, like)).fetchall()

    clients = db.execute("""
    SELECT *
    FROM clients
    WHERE IFNULL(full_name,'') LIKE ?
       OR IFNULL(phone,'') LIKE ?
       OR IFNULL(email,'') LIKE ?
    ORDER BY id DESC
""", (like, like, like)).fetchall()

    vehicles = db.execute("""
        SELECT *
        FROM vehicles
        WHERE IFNULL(make_model,'') LIKE ?
           OR IFNULL(plate,'') LIKE ?
        ORDER BY id DESC
    """, (like, like)).fetchall()

    rentals = db.execute("""
        SELECT rentals.*, clients.full_name AS client_name, vehicles.make_model, vehicles.plate
        FROM rentals
        LEFT JOIN clients ON rentals.client_id = clients.id
        LEFT JOIN vehicles ON rentals.vehicle_id = vehicles.id
        WHERE IFNULL(rentals.contract_number,'') LIKE ?
           OR IFNULL(clients.full_name,'') LIKE ?
           OR IFNULL(vehicles.make_model,'') LIKE ?
           OR IFNULL(vehicles.plate,'') LIKE ?
        ORDER BY rentals.id DESC
    """, (like, like, like, like)).fetchall()

    return render_template(
        "search_results.html",
        query=q,
        date=date,
        work_orders=work_orders,
        clients=clients,
        vehicles=vehicles,
        rentals=rentals
    )

@app.route("/update_vehicle_status", methods=["POST"])
def update_vehicle_status():
    plate = request.form.get("plate")
    status = request.form.get("status")

    conn = sqlite3.connect("dellicar.db")
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE vehicles SET status = ? WHERE plate = ?",
        (status, plate),
    )

    conn.commit()
    conn.close()

    return redirect("/vehicles")
@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":
        username = request.form.get("username")
password = request.form.get("password")

conn = sqlite3.connect("dellicar.db")
c = conn.cursor()

c.execute("SELECT role FROM users WHERE username=? AND password=?", (username, password))
user = c.fetchone()

conn.close()

if user:
    session["logged"] = True
    session["role"] = user[0]
    return redirect("/")

return """
<h2>Login Gestionale Dellicar</h2>
<form method="post">
    <input type="text" name="username" placeholder="Username">
    <input type="password" name="password" placeholder="Password">
    <button type="submit">Accedi</button>
</form>
"""
   
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5001, debug=True)
