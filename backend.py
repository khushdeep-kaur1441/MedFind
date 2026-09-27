#backend and data and login check and billing and stock management for the medfind app

import math
from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "hackathon-demo-secret-key"  # only for session cookies, fine for a prototype

DB_PATH = os.path.join(os.path.dirname(__file__), "medfind.db")

LOW_STOCK_THRESHOLD = 5  # quantity below this counts as "Low Stock"


# Database helpers

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Creates tables and inserts sample data the first time the app runs."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pharmacies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            area TEXT NOT NULL,
            license_number TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            latitude REAL,
            longitude REAL
            
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pharmacy_id INTEGER NOT NULL,
            medicine_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (pharmacy_id) REFERENCES pharmacies (id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pharmacy_id INTEGER NOT NULL,
            medicine_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            total REAL NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    #sample pharmacies for demo
    cur.execute("SELECT COUNT(*) FROM pharmacies")
    if cur.fetchone()[0] == 0:
        sample_pharmacies = [
            ("Sharma Medical Store", "Near Gate 1", "LIC001", "1234", 23.2599, 77.4126),
            ("City Health Pharmacy", "Main Market Road", "LIC002", "1234", 23.2650, 77.4200),
            ("Apollo Care Chemist", "Station Road", "LIC003", "1234", 23.2500, 77.4050),
            ("Wellness Pharma", "Civil Lines", "LIC004", "1234", 23.2700, 77.4300),
        ]
        cur.executemany(
            "INSERT INTO pharmacies (name, area, license_number, password, latitude, longitude) VALUES (?, ?, ?, ?, ?, ?)",
            sample_pharmacies,
        )
        conn.commit()

        # sample stock for each pharmacy demo
        cur.execute("SELECT id FROM pharmacies")
        pharmacy_ids = [row[0] for row in cur.fetchall()]

        sample_medicines = [
            ("Paracetamol 500mg", 20, 2.5),
            ("Crocin", 3, 3.0),
            ("ORS Sachet", 0, 15.0),
            ("Azithromycin 500mg", 12, 8.0),
            ("Cetirizine", 2, 1.5),
            ("Amoxicillin 250mg", 15, 6.0),
        ]
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        for pid in pharmacy_ids:
            for med_name, qty, price in sample_medicines:
                # vary quantity a little per pharmacy so data looks realistic
                adjusted_qty = max(0, qty - (pid * 2))
                cur.executemany(
                    "INSERT INTO stock (pharmacy_id, medicine_name, quantity, price, updated_at) VALUES (?,?,?,?,?)",
                    [(pid, med_name, adjusted_qty, price, now)],
                )
        conn.commit()

    conn.close()


def get_status(quantity):
    if quantity <= 0:
        return "Out of Stock"
    elif quantity < LOW_STOCK_THRESHOLD:
        return "Low Stock"
    return "Available"

#for location

def haversine_km(lat1, lon1, lat2, lon2):
    """Calculates straight-line distance between two lat/lng points in kilometers."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371  # Earth's radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 1)

# Customer search 

@app.route("/")
def customer_search():
    query = request.args.get("q", "").strip()
    customer_lat = request.args.get("lat", type=float)
    customer_lng = request.args.get("lng", type=float)
    results = []

    conn = get_db()

    # get list of all distinct medicine names for autocomplete suggestions
    all_medicines = conn.execute(
        "SELECT DISTINCT medicine_name FROM stock ORDER BY medicine_name"
    ).fetchall()
    medicine_names = [row["medicine_name"] for row in all_medicines]

    if query:
        rows = conn.execute(
            """
            SELECT stock.medicine_name, stock.quantity, stock.price, stock.updated_at,
                   pharmacies.name AS pharmacy_name, pharmacies.area,
                   pharmacies.latitude, pharmacies.longitude
            FROM stock
            JOIN pharmacies ON stock.pharmacy_id = pharmacies.id
            WHERE stock.medicine_name LIKE ?
            """,
            (f"%{query}%",),
        ).fetchall()

        for row in rows:
            distance = haversine_km(customer_lat, customer_lng, row["latitude"], row["longitude"])
            results.append({
                "medicine_name": row["medicine_name"],
                "quantity": row["quantity"],
                "price": row["price"],
                "updated_at": row["updated_at"],
                "pharmacy_name": row["pharmacy_name"],
                "area": row["area"],
                "status": get_status(row["quantity"]),
                "distance": distance,
            })

        if customer_lat is not None:
            results.sort(key=lambda x: (x["distance"] is None, x["distance"]))
        else:
            results.sort(key=lambda x: -x["quantity"])

    conn.close()

    return render_template("customer_search.html", query=query, results=results, medicine_names=medicine_names)

#pharamacy sign up

@app.route("/pharmacy/signup", methods=["GET", "POST"])
def pharmacy_signup():
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        area = request.form.get("area", "").strip()
        license_number = request.form.get("license_number", "").strip()
        password = request.form.get("password", "").strip()
        latitude = request.form.get("latitude", type=float)
        longitude = request.form.get("longitude", type=float)

        if not name or not area or not license_number or not password:
            error = "Please fill all fields"
        else:
            conn = get_db()
            existing = conn.execute(
                "SELECT id FROM pharmacies WHERE license_number = ?", (license_number,)
            ).fetchone()

            if existing:
                error = "This license number is already registered"
            else:
                cur = conn.execute(
                    "INSERT INTO pharmacies (name, area, license_number, password, latitude, longitude) VALUES (?, ?, ?, ?, ?, ?)",
                    (name, area, license_number, password, latitude, longitude),
                )
                conn.commit()
                new_id = cur.lastrowid
                conn.close()

                session["pharmacy_id"] = new_id
                session["pharmacy_name"] = name
                return redirect(url_for("pharmacy_dashboard"))

            conn.close()

    return render_template("pharmacy_signup.html", error=error)


#pharamacy login /logout
@app.route("/pharmacy/login", methods=["GET", "POST"])
def pharmacy_login():
    error = None

    conn = get_db()
    pharmacies = conn.execute("SELECT id, name, area FROM pharmacies").fetchall()

    if request.method == "POST":
        pharmacy_id = request.form.get("pharmacy_id")
        password = request.form.get("password")

        row = conn.execute(
            "SELECT * FROM pharmacies WHERE id = ? AND password = ?",
            (pharmacy_id, password),
        ).fetchone()

        if row:
            session["pharmacy_id"] = row["id"]
            session["pharmacy_name"] = row["name"]
            conn.close()
            return redirect(url_for("pharmacy_dashboard"))
        else:
            error = "Wrong pharmacy or password"

    conn.close()
    return render_template("pharmacy_login.html", pharmacies=pharmacies, error=error)

# logout pharmacy

@app.route("/pharmacy/logout")
def pharmacy_logout():
    session.clear()
    return redirect(url_for("pharmacy_login"))


def require_login():
    """Returns True if a pharmacy is logged in, else False."""
    return "pharmacy_id" in session


# Pharmacy dashboard ,view + update 

@app.route("/pharmacy/dashboard")
def pharmacy_dashboard():
    if not require_login():
        return redirect(url_for("pharmacy_login"))

    pharmacy_id = session["pharmacy_id"]
    conn = get_db()
    stock_rows = conn.execute(
        "SELECT * FROM stock WHERE pharmacy_id = ? ORDER BY quantity ASC",
        (pharmacy_id,),
    ).fetchall()
    conn.close()

    stock_list = []
    low_stock_items = []
    max_qty_for_bar = 20  # just for scaling the visual bar width

    for row in stock_rows:
        status = get_status(row["quantity"])
        bar_percent = min(100, int((row["quantity"] / max_qty_for_bar) * 100))
        item = {
            "id": row["id"],
            "medicine_name": row["medicine_name"],
            "quantity": row["quantity"],
            "price": row["price"],
            "status": status,
            "bar_percent": bar_percent,
            "updated_at": row["updated_at"],
        }
        stock_list.append(item)
        if status in ("Low Stock", "Out of Stock"):
            low_stock_items.append(item)

    return render_template(
        "pharmacy_dashboard.html",
        pharmacy_name=session["pharmacy_name"],
        stock_list=stock_list,
        low_stock_items=low_stock_items,
    )

# Update stock route

@app.route("/pharmacy/update_stock", methods=["POST"])
def update_stock():
    if not require_login():
        return redirect(url_for("pharmacy_login"))

    pharmacy_id = session["pharmacy_id"]
    medicine_name = request.form.get("medicine_name", "").strip()
    quantity = request.form.get("quantity", "0")
    price = request.form.get("price", "0")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    if medicine_name:
        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM stock WHERE pharmacy_id = ? AND medicine_name = ?",
            (pharmacy_id, medicine_name),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE stock SET quantity = ?, price = ?, updated_at = ? WHERE id = ?",
                (quantity, price, now, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO stock (pharmacy_id, medicine_name, quantity, price, updated_at) VALUES (?,?,?,?,?)",
                (pharmacy_id, medicine_name, quantity, price, now),
            )
        conn.commit()
        conn.close()

    return redirect(url_for("pharmacy_dashboard"))


# billing

@app.route("/pharmacy/billing", methods=["GET", "POST"])
def billing():
    if not require_login():
        return redirect(url_for("pharmacy_login"))

    pharmacy_id = session["pharmacy_id"]
    conn = get_db()

    receipt = None
    error = None

    if request.method == "POST":
        stock_id = request.form.get("stock_id")
        sell_qty = int(request.form.get("sell_qty", 0))

        item = conn.execute(
            "SELECT * FROM stock WHERE id = ? AND pharmacy_id = ?", (stock_id, pharmacy_id)
        ).fetchone()

        if not item:
            error = "Medicine not found"
        elif sell_qty <= 0:
            error = "Enter a valid quantity"
        elif sell_qty > item["quantity"]:
            error = f"Only {item['quantity']} units available in stock"
        else:
            new_qty = item["quantity"] - sell_qty
            total = round(sell_qty * item["price"], 2)
            now = datetime.now().strftime("%Y-%m-%d %H:%M")

            conn.execute(
                "UPDATE stock SET quantity = ?, updated_at = ? WHERE id = ?",
                (new_qty, now, item["id"]),
            )
            conn.execute(
                "INSERT INTO bills (pharmacy_id, medicine_name, quantity, total, created_at) VALUES (?,?,?,?,?)",
                (pharmacy_id, item["medicine_name"], sell_qty, total, now),
            )
            conn.commit()

            receipt = {
                "medicine_name": item["medicine_name"],
                "quantity": sell_qty,
                "unit_price": item["price"],
                "total": total,
                "time": now,
            }

    stock_rows = conn.execute(
        "SELECT * FROM stock WHERE pharmacy_id = ? AND quantity > 0 ORDER BY medicine_name",
        (pharmacy_id,),
    ).fetchall()

    recent_bills = conn.execute(
        "SELECT * FROM bills WHERE pharmacy_id = ? ORDER BY id DESC LIMIT 5",
        (pharmacy_id,),
    ).fetchall()

    conn.close()

    return render_template(
        "billing.html",
        pharmacy_name=session["pharmacy_name"],
        stock_list=stock_rows,
        receipt=receipt,
        error=error,
        recent_bills=recent_bills,
    )


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
