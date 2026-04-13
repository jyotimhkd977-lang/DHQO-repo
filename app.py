import os
import pickle
import io
import base64
import sqlite3
import re
from datetime import datetime, date
from functools import wraps

import numpy as np
import pandas as pd

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    flash,
    send_file,
    g,
)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

app = Flask(__name__)
app.secret_key = "hq_secret_2024_@india"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
MPLCONFIGDIR = os.environ.get("MPLCONFIGDIR", "/tmp/matplotlib")

DEPARTMENTS = [
    "Cardiology",
    "Orthopedics",
    "General OPD",
    "Pediatrics",
    "Neurology",
    "Emergency",
    "Dermatology",
]
EMERGENCY_KEYWORDS = [
    "chest pain",
    "breathing",
    "breathless",
    "unconscious",
    "bleeding",
    "stroke",
    "seizure",
    "accident",
    "burn",
    "collapse",
    "heart attack",
    "severe pain",
]
PLACEHOLDER_TOKENS = {
    "test",
    "fake",
    "demo",
    "asdf",
    "none",
    "null",
    "dummy",
    "sample",
    "xyz",
    "na",
    "n/a",
}
COMMON_SYMPTOM_TERMS = {
    "headache",
    "fever",
    "cough",
    "cold",
    "pain",
    "body",
    "weakness",
    "dizziness",
    "nausea",
    "vomiting",
    "stomach",
    "chest",
    "breathing",
    "breathlessness",
    "migraine",
    "rash",
    "allergy",
    "swelling",
    "injury",
    "fracture",
    "burn",
    "diarrhea",
    "fatigue",
    "sore",
    "throat",
    "ache",
    "back",
    "toothache",
    "infection",
    "bleeding",
}
_PLOT_MODULES = None


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db:
        db.close()


def query(sql, params=(), one=False, commit=False):
    db = get_db()
    cur = db.execute(sql, params)
    if commit:
        db.commit()
        return cur.lastrowid
    return cur.fetchone() if one else cur.fetchall()


def ensure_column(db, table, column, definition):
    cols = {row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            department TEXT NOT NULL,
            phone TEXT,
            availability INTEGER DEFAULT 1,
            patients_seen INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            queue_number INTEGER,
            name TEXT NOT NULL,
            age INTEGER,
            phone TEXT,
            address TEXT,
            symptoms TEXT,
            severity INTEGER DEFAULT 3,
            emergency INTEGER DEFAULT 0,
            department TEXT,
            arrival_time TEXT,
            predicted_wait REAL DEFAULT 0,
            status TEXT DEFAULT 'pending_review',
            review_status TEXT DEFAULT 'pending',
            review_note TEXT,
            fake_detection TEXT DEFAULT 'pending',
            doctor_id INTEGER,
            treatment TEXT,
            suggestion TEXT,
            prescription_text TEXT,
            treated_at TEXT,
            reviewed_by INTEGER
        );

        CREATE TABLE IF NOT EXISTS sms_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient TEXT,
            phone TEXT,
            message TEXT,
            sent_at TEXT,
            is_read INTEGER DEFAULT 0
        );
    """
    )

    ensure_column(db, "patients", "user_id", "INTEGER")
    ensure_column(db, "patients", "address", "TEXT")
    ensure_column(db, "patients", "symptoms", "TEXT")
    ensure_column(db, "patients", "review_status", "TEXT DEFAULT 'pending'")
    ensure_column(db, "patients", "review_note", "TEXT")
    ensure_column(db, "patients", "fake_detection", "TEXT DEFAULT 'pending'")
    ensure_column(db, "patients", "treatment", "TEXT")
    ensure_column(db, "patients", "suggestion", "TEXT")
    ensure_column(db, "patients", "prescription_text", "TEXT")
    ensure_column(db, "patients", "treated_at", "TEXT")
    ensure_column(db, "patients", "reviewed_by", "INTEGER")
    ensure_column(db, "sms_log", "is_read", "INTEGER DEFAULT 0")
    ensure_column(db, "doctors", "phone", "TEXT")

    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO users (name,phone,password,role) VALUES (?,?,?,?)",
            [
                ("Jyoti", "9776968897", "Jyoti@2006", "admin"),
                ("Dr. Kumar", "9876543210", "doctor123", "doctor"),
                ("Receptionist Priya", "9123456789", "recep123", "receptionist"),
                ("Rahul Patient", "9988776655", "patient123", "patient"),
            ],
        )
    else:
        existing_admin_phone = db.execute(
            "SELECT id FROM users WHERE phone='9776968897'"
        ).fetchone()
        if existing_admin_phone:
            db.execute(
                "UPDATE users SET name=?, password=?, role=? WHERE phone=?",
                ("Jyoti", "Jyoti@2006", "admin", "9776968897"),
            )
        elif db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] == 0:
            db.execute(
                "INSERT INTO users (name,phone,password,role) VALUES (?,?,?,?)",
                ("Jyoti", "9776968897", "Jyoti@2006", "admin"),
            )

        existing_doctor_phone = db.execute(
            "SELECT id FROM users WHERE phone='9876543210'"
        ).fetchone()
        if existing_doctor_phone:
            db.execute(
                "UPDATE users SET name=?, password=?, role=? WHERE phone=?",
                ("Dr. Kumar", "doctor123", "doctor", "9876543210"),
            )
        elif db.execute("SELECT COUNT(*) FROM users WHERE role='doctor'").fetchone()[0] == 0:
            db.execute(
                "INSERT INTO users (name,phone,password,role) VALUES (?,?,?,?)",
                ("Dr. Kumar", "9876543210", "doctor123", "doctor"),
            )

    if db.execute("SELECT COUNT(*) FROM doctors").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO doctors (name,department,phone,availability) VALUES (?,?,?,?)",
            [
                ("Dr. Kumar", "General OPD", "9876543210", 1),
                ("Dr. Arjun Sharma", "Cardiology", None, 1),
                ("Dr. Neha Patel", "Orthopedics", None, 1),
                ("Dr. Ravi Menon", "General OPD", None, 0),
                ("Dr. Sunita Rao", "Pediatrics", None, 1),
                ("Dr. Vikram Iyer", "Neurology", None, 1),
                ("Dr. Priya Singh", "Emergency", None, 1),
                ("Dr. Anil Desai", "Dermatology", None, 0),
            ],
        )

    db.execute(
        """
        UPDATE doctors
        SET phone = (
            SELECT users.phone
            FROM users
            WHERE users.role='doctor' AND users.name=doctors.name
            LIMIT 1
        )
        WHERE (phone IS NULL OR phone='')
          AND EXISTS (
              SELECT 1
              FROM users
              WHERE users.role='doctor' AND users.name=doctors.name
          )
        """
    )

    db.commit()
    db.close()
    print("DB ready.")


def get_plot_modules():
    global _PLOT_MODULES
    if _PLOT_MODULES is None:
        os.makedirs(MPLCONFIGDIR, exist_ok=True)
        import matplotlib

        matplotlib.use("Agg")

        import matplotlib.pyplot as plt
        import seaborn as sns

        _PLOT_MODULES = (plt, sns)
    return _PLOT_MODULES


def load_wait_model():
    path = os.path.join(BASE_DIR, "hospital_model.pkl")
    from model_training import train_model

    if not os.path.exists(path):
        train_model()
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        train_model()
        with open(path, "rb") as f:
            return pickle.load(f)


def load_fake_detection_model():
    path = os.path.join(BASE_DIR, "fake_detection_model.pkl")
    from model_training import train_fake_detection_model

    if not os.path.exists(path):
        train_fake_detection_model()
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        train_fake_detection_model()
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:
            return None


WAIT_ML = load_wait_model()
FAKE_DETECTION_ML = load_fake_detection_model()


def predict_wait(severity, age, emergency, doc_available, queue_len, hour):
    feat = np.array(
        [
            [
                int(severity),
                int(age),
                int(emergency),
                int(doc_available),
                int(queue_len),
                int(hour),
            ]
        ]
    )
    return round(max(1.0, float(WAIT_ML["model"].predict(feat)[0])), 1)


def normalize_phone(ph):
    return ph.strip().replace(" ", "").replace("+91", "")


def validate_indian_phone(ph):
    ph = normalize_phone(ph)
    return ph.isdigit() and len(ph) == 10 and ph[0] in "6789"


def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in.", "warning")
                return redirect(url_for("login"))
            if role:
                allowed = set(role) if isinstance(role, (list, tuple, set)) else {role}
                if session.get("role") not in allowed:
                    flash("Unauthorised.", "danger")
                    return redirect(url_for("dashboard"))
            return f(*args, **kwargs)

        return decorated

    return decorator


def dashboard_for_role(role):
    return {
        "patient": "patient_dashboard",
        "doctor": "doctor_dashboard",
        "receptionist": "reception_dashboard",
        "admin": "admin_dashboard",
    }.get(role, "index")


def send_sms(patient, phone, message):
    query(
        "INSERT INTO sms_log (patient,phone,message,sent_at,is_read) VALUES (?,?,?,?,0)",
        (patient, phone, message, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        commit=True,
    )


def get_notification_phones_for_user(user_id):
    if not user_id:
        return []
    phones = set()
    user = query("SELECT phone FROM users WHERE id=?", (user_id,), one=True)
    if user and user["phone"]:
        phones.add(user["phone"].strip())
    for row in query(
        "SELECT DISTINCT phone FROM patients WHERE user_id=? AND phone IS NOT NULL",
        (user_id,),
    ):
        phone = (row["phone"] or "").strip()
        if phone:
            phones.add(phone)
    return sorted(phones)


def get_sms_logs_for_phones(phones, limit=10, unread_only=False):
    if not phones:
        return []
    placeholders = ",".join("?" for _ in phones)
    unread_clause = " AND is_read=0" if unread_only else ""
    return [
        dict(r)
        for r in query(
            f"""
            SELECT * FROM sms_log
            WHERE phone IN ({placeholders}){unread_clause}
            ORDER BY sent_at DESC
            LIMIT ?
            """,
            (*phones, limit),
        )
    ]


def get_unread_sms_count_for_phones(phones):
    if not phones:
        return 0
    placeholders = ",".join("?" for _ in phones)
    return query(
        f"SELECT COUNT(*) FROM sms_log WHERE phone IN ({placeholders}) AND is_read=0",
        tuple(phones),
        one=True,
    )[0]


def mark_sms_read_for_phones(phones):
    if not phones:
        return
    placeholders = ",".join("?" for _ in phones)
    query(
        f"UPDATE sms_log SET is_read=1 WHERE phone IN ({placeholders}) AND is_read=0",
        tuple(phones),
        commit=True,
    )


@app.context_processor
def inject_patient_notifications():
    if session.get("role") != "patient" or "user_id" not in session:
        return {"patient_notifications": [], "patient_unread_count": 0}
    phones = get_notification_phones_for_user(session["user_id"])
    return {
        "patient_notifications": get_sms_logs_for_phones(phones, limit=6),
        "patient_unread_count": get_unread_sms_count_for_phones(phones),
    }


def compute_priority(p):
    return (0 if p["emergency"] else 100) + (6 - int(p["severity"] or 3)) * 10 + float(
        p["predicted_wait"] or 0
    )


def get_sorted_queue():
    rows = query(
        """
        SELECT p.*, d.name AS doctor_name
        FROM patients p
        LEFT JOIN doctors d ON d.id = p.doctor_id
        WHERE p.review_status='approved' AND p.status='waiting'
        """
    )
    return sorted([dict(r) for r in rows], key=compute_priority)


def assign_doctor(department):
    return query(
        """
        SELECT d.*,
               (SELECT COUNT(*) FROM patients p
                WHERE p.doctor_id=d.id AND p.review_status='approved' AND p.status='waiting') AS active_queue
        FROM doctors d
        WHERE d.department=? AND d.availability=1
        ORDER BY active_queue ASC, d.patients_seen ASC, d.id ASC
        """,
        (department,),
        one=True,
    )


def get_queue_number():
    return (query("SELECT MAX(queue_number) FROM patients", one=True)[0] or 0) + 1


def build_fake_detection_text(name, address, symptoms):
    return (
        f"name: {(name or '').strip()} || "
        f"address: {(address or '').strip()} || "
        f"symptoms: {(symptoms or '').strip()}"
    )


def assess_fake_submission_rules(name, address, symptoms):
    def words(text):
        return re.findall(r"[a-z]+", (text or "").lower())

    score = 0
    reasons = []

    lower_name = (name or "").strip().lower()
    lower_address = (address or "").strip().lower()
    lower_symptoms = (symptoms or "").strip().lower()
    name_words = words(name)
    address_words = words(address)
    symptom_words = words(symptoms)

    if not lower_name:
        score += 50
        reasons.append("missing patient name")
    elif any(token in PLACEHOLDER_TOKENS for token in name_words):
        score += 55
        reasons.append("placeholder name")
    else:
        if any(ch.isdigit() for ch in lower_name):
            score += 25
            reasons.append("name contains digits")
        if len(name_words) < 2:
            score += 12
            reasons.append("name looks incomplete")
        if re.search(r"(.)\1{3,}", lower_name):
            score += 30
            reasons.append("name has repeated characters")

    if not lower_address:
        score += 45
        reasons.append("missing address")
    elif any(token in PLACEHOLDER_TOKENS for token in address_words):
        score += 45
        reasons.append("placeholder address")
    else:
        if len(lower_address) < 8:
            score += 15
            reasons.append("address too short")
        if len(address_words) < 2:
            score += 10
            reasons.append("address incomplete")
        if re.search(r"(.)\1{4,}", lower_address):
            score += 20
            reasons.append("address has repeated characters")

    if not lower_symptoms:
        score += 60
        reasons.append("missing symptoms")
    elif any(token in PLACEHOLDER_TOKENS for token in symptom_words):
        score += 60
        reasons.append("placeholder symptom text")
    else:
        if re.search(r"(.)\1{3,}", lower_symptoms) or "111" in lower_symptoms or "1234" in lower_symptoms:
            score += 35
            reasons.append("symptoms look spammy")
        if len(symptom_words) == 0:
            score += 45
            reasons.append("symptoms are unreadable")
        elif len(symptom_words) == 1 and symptom_words[0] not in COMMON_SYMPTOM_TERMS:
            score += 15
            reasons.append("symptoms are too vague")
        elif len(symptom_words) >= 1 and any(word in COMMON_SYMPTOM_TERMS for word in symptom_words):
            score -= 10
        if len(lower_symptoms) < 4:
            score += 15
            reasons.append("symptoms too short")
        if sum(ch.isdigit() for ch in lower_symptoms) > max(3, len(lower_symptoms) // 3):
            score += 20
            reasons.append("too many digits in symptoms")

    return max(0, min(score, 95)), reasons


def format_fake_detection_result(score, reasons, used_model=False):
    score = max(0, min(int(round(score)), 95))
    if reasons:
        detail = ", ".join(reasons[:3])
    elif score >= 60:
        detail = "classifier flagged suspicious submission" if used_model else "needs manual review"
    elif score >= 30:
        detail = "manual review recommended by classifier" if used_model else "check manually"
    else:
        detail = "looks genuine"

    if score >= 60:
        return f"High risk ({score}%) - {detail}"
    if score >= 30:
        return f"Medium risk ({score}%) - {detail}"
    return f"Low risk ({score}%) - looks genuine"


def detect_fake_submission(name, address, symptoms):
    rule_score, reasons = assess_fake_submission_rules(name, address, symptoms)

    if not FAKE_DETECTION_ML:
        return format_fake_detection_result(rule_score, reasons, used_model=False)

    try:
        text = build_fake_detection_text(name, address, symptoms)
        ml_probability = float(FAKE_DETECTION_ML["model"].predict_proba([text])[0][1]) * 100
        blended_score = (ml_probability * 0.75) + (rule_score * 0.25)
        if rule_score >= 60:
            blended_score = max(blended_score, rule_score)
        return format_fake_detection_result(blended_score, reasons, used_model=True)
    except Exception:
        return format_fake_detection_result(rule_score, reasons, used_model=False)


def predict_emergency_flag(severity, symptoms, patient_marked_emergency):
    symptoms_l = (symptoms or "").lower()
    hits = sum(1 for item in EMERGENCY_KEYWORDS if item in symptoms_l)
    emergency = 1 if patient_marked_emergency or int(severity) >= 5 or hits >= 1 else 0
    if emergency:
        return 1, f"Emergency likely - severity {severity}, keyword hits {hits}"
    return 0, f"Routine case - severity {severity}, keyword hits {hits}"


def calculate_patient_wait(patient, doctor):
    doc_avail = 1 if doctor else 0
    qlen = query(
        """
        SELECT COUNT(*) FROM patients
        WHERE status='waiting' AND review_status='approved' AND department=?
        """,
        (patient["department"],),
        one=True,
    )[0]
    return predict_wait(
        patient["severity"],
        patient["age"] or 30,
        patient["emergency"],
        doc_avail,
        qlen,
        datetime.now().hour,
    )


def to_b64(fig):
    plt, _ = get_plot_modules()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=110)
    plt.close(fig)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode()


def waiting_time_trend_chart():
    plt, _ = get_plot_modules()
    today = date.today().strftime("%Y-%m-%d")
    rows = query(
        """
        SELECT arrival_time,predicted_wait
        FROM patients
        WHERE arrival_time LIKE ? AND review_status='approved'
        ORDER BY arrival_time
        """,
        (today + "%",),
    )
    if not rows:
        return None
    times = [r["arrival_time"][11:16] for r in rows]
    waits = [r["predicted_wait"] for r in rows]
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.plot(times, waits, marker="o", color="#2563eb", linewidth=2)
    ax.fill_between(range(len(waits)), waits, alpha=0.12, color="#2563eb")
    ax.set_title("Waiting Time Trend (Today)", fontsize=12, fontweight="bold")
    ax.set_xlabel("Arrival")
    ax.set_ylabel("Wait (min)")
    ax.set_xticks(range(len(times)))
    ax.set_xticklabels(times, rotation=45, fontsize=7)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return to_b64(fig)


def peak_hour_chart():
    plt, _ = get_plot_modules()
    rows = query("SELECT arrival_time FROM patients WHERE review_status='approved'")
    if not rows:
        return None
    hours = [int(r["arrival_time"][11:13]) for r in rows if r["arrival_time"] and len(r["arrival_time"]) > 12]
    if not hours:
        return None
    hc = pd.Series(hours).value_counts().sort_index().reindex(range(24), fill_value=0)
    fig, ax = plt.subplots(figsize=(7, 3))
    bars = ax.bar(hc.index, hc.values, color="#10b981", alpha=0.8)
    if hc.sum() > 0:
        bars[hc.idxmax()].set_color("#ef4444")
    ax.set_title("Peak Hour Analysis", fontsize=12, fontweight="bold")
    ax.set_xlabel("Hour")
    ax.set_ylabel("Patients")
    ax.set_xticks(range(24))
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    return to_b64(fig)


def dept_load_chart():
    plt, sns = get_plot_modules()
    rows = query("SELECT department FROM patients WHERE review_status='approved'")
    if not rows:
        return None
    counts = pd.Series([r["department"] for r in rows]).value_counts()
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.pie(
        counts.values,
        labels=counts.index,
        autopct="%1.1f%%",
        startangle=140,
        colors=sns.color_palette("Set2", len(counts)),
    )
    ax.set_title("Department Load", fontsize=12, fontweight="bold")
    fig.tight_layout()
    return to_b64(fig)


def feature_importance_chart():
    plt, _ = get_plot_modules()
    fi = WAIT_ML.get("feature_importance", {})
    if not fi:
        return None
    items = sorted(fi.items(), key=lambda x: x[1])
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.barh([x[0] for x in items], [x[1] for x in items], color="#6366f1")
    ax.set_title("ML Feature Importance", fontsize=12, fontweight="bold")
    ax.set_xlabel("Score")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    return to_b64(fig)


def heatmap_chart():
    plt, sns = get_plot_modules()
    rows = query(
        """
        SELECT arrival_time,department,predicted_wait
        FROM patients
        WHERE review_status='approved'
        """
    )
    if len(rows) < 5:
        return None
    data = [
        {"hour": int(r["arrival_time"][11:13]), "dept": r["department"], "wait": r["predicted_wait"]}
        for r in rows
        if r["arrival_time"] and len(r["arrival_time"]) > 12
    ]
    if not data:
        return None
    df = pd.DataFrame(data)
    pivot = df.pivot_table(values="wait", index="dept", columns="hour", aggfunc="mean").fillna(0)
    fig, ax = plt.subplots(figsize=(10, 4))
    sns.heatmap(
        pivot,
        ax=ax,
        cmap="YlOrRd",
        annot=True,
        fmt=".0f",
        linewidths=0.5,
        cbar_kws={"label": "Avg Wait (min)"},
    )
    ax.set_title("Hospital Load Heatmap - Dept x Hour", fontsize=12, fontweight="bold")
    fig.tight_layout()
    return to_b64(fig)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = normalize_phone(request.form.get("phone", ""))
        pwd = request.form.get("password", "").strip()
        if not validate_indian_phone(phone):
            flash("Valid Indian mobile required.", "danger")
            return redirect(url_for("login"))
        user = query("SELECT * FROM users WHERE phone=? AND password=?", (phone, pwd), one=True)
        if user:
            session.update({"user_id": user["id"], "role": user["role"], "name": user["name"]})
            flash(f"Welcome, {user['name']}!", "success")
            return redirect(url_for(dashboard_for_role(user["role"])))
        flash("Invalid credentials.", "danger")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = normalize_phone(request.form.get("phone", ""))
        password = request.form.get("password", "").strip()
        role = "patient"

        if not name or len(password) < 4:
            flash("Name and password (min 4 chars) are required.", "danger")
            return redirect(url_for("register"))
        if not validate_indian_phone(phone):
            flash("Valid Indian mobile required.", "danger")
            return redirect(url_for("register"))
        try:
            query(
                "INSERT INTO users (name,phone,password,role) VALUES (?,?,?,?)",
                (name, phone, password, role),
                commit=True,
            )
            flash("Registration complete. Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("This mobile number is already registered.", "danger")
            return redirect(url_for("register"))
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required()
def dashboard():
    return redirect(url_for(dashboard_for_role(session.get("role"))))


@app.route("/patient/dashboard", methods=["GET", "POST"])
@login_required(role="patient")
def patient_dashboard():
    user = query("SELECT * FROM users WHERE id=?", (session["user_id"],), one=True)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        age_text = request.form.get("age", "").strip()
        address = request.form.get("address", "").strip()
        phone = normalize_phone(request.form.get("phone", "").strip() or query(
            "SELECT phone FROM users WHERE id=?", (session["user_id"],), one=True
        )["phone"])
        symptoms = request.form.get("symptoms", "").strip()
        emergency = 1 if request.form.get("emergency") == "yes" else 0

        if not name or not age_text or not address or not symptoms:
            flash("Please complete all patient details before submitting.", "danger")
            return redirect(url_for("patient_dashboard"))
        if not validate_indian_phone(phone):
            flash("Please enter a valid Indian mobile number.", "danger")
            return redirect(url_for("patient_dashboard"))

        fake_detection = detect_fake_submission(name, address, symptoms)
        query(
            """
            INSERT INTO patients
            (user_id,name,age,phone,address,symptoms,severity,emergency,department,
             arrival_time,status,review_status,fake_detection)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                session["user_id"],
                name,
                int(age_text),
                phone,
                address,
                symptoms,
                3,
                emergency,
                None,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "pending_review",
                "pending",
                fake_detection,
            ),
            commit=True,
        )
        send_sms(
            name,
            phone,
            "Your patient form has been submitted successfully and is waiting for receptionist review.",
        )
        flash("Your form has been submitted to reception for review.", "success")
        return redirect(url_for("patient_dashboard"))

    visits = [
        dict(r)
        for r in query(
            """
            SELECT p.*, d.name AS doctor_name
            FROM patients p
            LEFT JOIN doctors d ON d.id = p.doctor_id
            WHERE p.user_id=?
            ORDER BY p.id DESC
            """,
            (session["user_id"],),
        )
    ]
    latest = visits[0] if visits else None
    return render_template(
        "patient_dashboard.html",
        departments=DEPARTMENTS,
        visits=visits,
        latest=latest,
    )


@app.route("/notifications/read", methods=["POST"])
@login_required(role="patient")
def mark_notifications_read():
    mark_sms_read_for_phones(get_notification_phones_for_user(session["user_id"]))
    return jsonify({"ok": True})


@app.route("/reception")
@login_required(role="receptionist")
def reception():
    return redirect(url_for("reception_dashboard"))


@app.route("/reception/dashboard", methods=["GET", "POST"])
@login_required(role="receptionist")
def reception_dashboard():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "review_patient":
            patient = query("SELECT * FROM patients WHERE id=?", (request.form["patient_id"],), one=True)
            decision = request.form.get("decision")
            note = request.form.get("review_note", "").strip()
            if patient and decision in {"approve", "reject"}:
                selected_department = request.form.get("department", "").strip()
                selected_severity = int(request.form.get("severity", patient["severity"] or 3))
                emergency_pred, emergency_note = predict_emergency_flag(
                    selected_severity, patient["symptoms"], patient["emergency"]
                )
                fake_detection = detect_fake_submission(
                    patient["name"], patient["address"], patient["symptoms"]
                )

                if decision == "approve":
                    if selected_department not in DEPARTMENTS or selected_severity not in {1, 2, 3, 4, 5}:
                        flash("Receptionist must select department and severity before approval.", "danger")
                        return redirect(url_for("reception_dashboard"))
                    force_emergency = 1 if request.form.get("force_emergency") == "yes" else 0
                    final_emergency = 1 if emergency_pred or force_emergency else 0
                    patient_dict = dict(patient)
                    patient_dict["department"] = selected_department
                    patient_dict["severity"] = selected_severity
                    patient_dict["emergency"] = final_emergency
                    assigned_doctor = assign_doctor(selected_department)
                    queue_number = get_queue_number()
                    wait_time = calculate_patient_wait(patient_dict, assigned_doctor)
                    query(
                        """
                        UPDATE patients
                        SET queue_number=?, emergency=?, severity=?, department=?, predicted_wait=?, status='waiting',
                            review_status='approved', review_note=?, fake_detection=?,
                            doctor_id=?, reviewed_by=?
                        WHERE id=?
                        """,
                        (
                            queue_number,
                            final_emergency,
                            selected_severity,
                            selected_department,
                            wait_time,
                            f"{note} | {emergency_note}".strip(" |"),
                            fake_detection,
                            assigned_doctor["id"] if assigned_doctor else None,
                            session["user_id"],
                            patient["id"],
                        ),
                        commit=True,
                    )
                    if patient["phone"]:
                        doctor_name = assigned_doctor["name"] if assigned_doctor else "Doctor will be assigned soon"
                        send_sms(
                            patient["name"],
                            patient["phone"],
                            f"Queue #{queue_number} approved for {selected_department}. "
                            f"Estimated wait {wait_time} min. Doctor: {doctor_name}.",
                        )
                    flash(f"{patient['name']} approved and added to queue.", "success")
                else:
                    query(
                        """
                        UPDATE patients
                        SET status='rejected', review_status='rejected', review_note=?,
                            fake_detection=?, reviewed_by=?
                        WHERE id=?
                        """,
                        (note or emergency_note, fake_detection, session["user_id"], patient["id"]),
                        commit=True,
                    )
                    if patient["phone"]:
                        send_sms(
                            patient["name"],
                            patient["phone"],
                            f"Your patient form was rejected by reception. Reason: {note or emergency_note}",
                        )
                    flash(f"{patient['name']} rejected.", "warning")

        return redirect(url_for("reception_dashboard"))

    today = date.today().strftime("%Y-%m-%d")
    total_today = query("SELECT COUNT(*) FROM patients WHERE arrival_time LIKE ?", (today + "%",), one=True)[0]
    waiting = query(
        "SELECT COUNT(*) FROM patients WHERE review_status='approved' AND status='waiting'",
        one=True,
    )[0]
    pending_reviews = query(
        "SELECT COUNT(*) FROM patients WHERE review_status='pending'",
        one=True,
    )[0]
    emergency_count = query(
        """
        SELECT COUNT(*) FROM patients
        WHERE arrival_time LIKE ? AND review_status='approved' AND emergency=1
        """,
        (today + "%",),
        one=True,
    )[0]
    avg_row = query(
        """
        SELECT AVG(predicted_wait) FROM patients
        WHERE arrival_time LIKE ? AND review_status='approved'
        """,
        (today + "%",),
        one=True,
    )[0]
    queue = get_sorted_queue()
    pending_patients = [
        dict(r)
        for r in query(
            """
            SELECT * FROM patients
            WHERE review_status='pending'
            ORDER BY arrival_time ASC
            """
        )
    ]
    for patient in pending_patients:
        patient["fake_detection_live"] = detect_fake_submission(
            patient["name"], patient["address"], patient["symptoms"]
        )
        patient["emergency_prediction"], patient["emergency_note"] = predict_emergency_flag(
            patient["severity"] or 3, patient["symptoms"], patient["emergency"]
        )
    return render_template(
        "reception_dashboard.html",
        total_today=total_today,
        waiting_count=waiting,
        pending_reviews=pending_reviews,
        emergency_count=emergency_count,
        avg_wait=round(avg_row or 0, 1),
        queue=queue,
        pending_patients=pending_patients,
        departments=DEPARTMENTS,
    )


@app.route("/doctor/panel")
@login_required(role="doctor")
def doctor_panel():
    return redirect(url_for("doctor_dashboard"))


@app.route("/admin/dashboard", methods=["GET", "POST"])
@login_required(role="admin")
def admin_dashboard():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_staff_user":
            name = request.form.get("user_name", "").strip()
            phone = normalize_phone(request.form.get("user_phone", ""))
            password = request.form.get("user_pass", "").strip()
            role = "receptionist"
            if not name or len(password) < 4:
                flash("Valid receptionist name and password are required.", "danger")
                return redirect(url_for("admin_dashboard"))
            if not validate_indian_phone(phone):
                flash("Valid Indian mobile required for staff login.", "danger")
                return redirect(url_for("admin_dashboard"))
            try:
                query(
                    "INSERT INTO users (name,phone,password,role) VALUES (?,?,?,?)",
                    (name, phone, password, role),
                    commit=True,
                )
                flash(f"{role.title()} login created for {name}.", "success")
            except sqlite3.IntegrityError:
                flash("This mobile number is already registered.", "danger")

        elif action == "add_doctor":
            doctor_name = request.form.get("doctor_name", "").strip()
            department = request.form.get("department", "").strip()
            doctor_phone = normalize_phone(request.form.get("doctor_phone", ""))
            doctor_password = request.form.get("doctor_password", "").strip()
            if not doctor_name or department not in DEPARTMENTS or len(doctor_password) < 4:
                flash("Doctor name, department, and password (min 4 chars) are required.", "danger")
                return redirect(url_for("admin_dashboard"))
            if not validate_indian_phone(doctor_phone):
                flash("Valid Indian mobile required for doctor login.", "danger")
                return redirect(url_for("admin_dashboard"))

            db = get_db()
            try:
                db.execute(
                    "INSERT INTO users (name,phone,password,role) VALUES (?,?,?,?)",
                    (doctor_name, doctor_phone, doctor_password, "doctor"),
                )
                db.execute(
                    "INSERT INTO doctors (name,department,phone,availability) VALUES (?,?,?,1)",
                    (doctor_name, department, doctor_phone),
                )
                db.commit()
                flash(f"{doctor_name} added to doctor roster with login credentials.", "success")
            except sqlite3.IntegrityError:
                db.rollback()
                flash("This doctor number is already registered.", "danger")

        elif action == "toggle_doctor":
            doc = query("SELECT * FROM doctors WHERE id=?", (request.form["doc_id"],), one=True)
            if doc:
                new_value = 0 if doc["availability"] else 1
                query(
                    "UPDATE doctors SET availability=? WHERE id=?",
                    (new_value, doc["id"]),
                    commit=True,
                )
                flash(
                    f"{doc['name']} marked {'available' if new_value else 'unavailable'}.",
                    "info",
                )

        return redirect(url_for("admin_dashboard"))

    today = date.today().strftime("%Y-%m-%d")
    stats = {
        "total_today": query("SELECT COUNT(*) FROM patients WHERE arrival_time LIKE ?", (today + "%",), one=True)[0],
        "pending_reviews": query("SELECT COUNT(*) FROM patients WHERE review_status='pending'", one=True)[0],
        "approved_waiting": query(
            "SELECT COUNT(*) FROM patients WHERE review_status='approved' AND status='waiting'",
            one=True,
        )[0],
        "staff_accounts": query("SELECT COUNT(*) FROM users WHERE role IN ('doctor','receptionist')", one=True)[0],
    }
    doctors = [dict(r) for r in query("SELECT * FROM doctors ORDER BY department, name")]
    staff_users = [dict(r) for r in query("SELECT * FROM users WHERE role IN ('doctor','receptionist') ORDER BY role, name")]
    sms_logs = [dict(r) for r in query("SELECT * FROM sms_log ORDER BY sent_at DESC LIMIT 10")]
    queue = get_sorted_queue()[:10]
    return render_template(
        "admin.html",
        stats=stats,
        doctors=doctors,
        staff_users=staff_users,
        departments=DEPARTMENTS,
        sms_logs=sms_logs,
        queue=queue,
    )


@app.route("/doctor/dashboard", methods=["GET", "POST"])
@login_required(role="doctor")
def doctor_dashboard():
    if request.method == "POST":
        if request.form.get("action") == "treat_patient":
            patient = query("SELECT * FROM patients WHERE id=?", (request.form["patient_id"],), one=True)
            treatment = request.form.get("treatment", "").strip()
            suggestion = request.form.get("suggestion", "").strip()
            prescription = request.form.get("prescription_text", "").strip()
            if not patient or patient["review_status"] != "approved" or patient["status"] != "waiting":
                flash("That patient is not available for treatment.", "danger")
                return redirect(url_for("doctor_dashboard"))
            if not treatment or not suggestion or not prescription:
                flash("Treatment, suggestion, and prescription are all required.", "danger")
                return redirect(url_for("doctor_dashboard"))

            query(
                """
                UPDATE patients
                SET treatment=?, suggestion=?, prescription_text=?,
                    status='completed', treated_at=?
                WHERE id=?
                """,
                (
                    treatment,
                    suggestion,
                    prescription,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    patient["id"],
                ),
                commit=True,
            )
            if patient["doctor_id"]:
                query(
                    "UPDATE doctors SET patients_seen=patients_seen+1 WHERE id=?",
                    (patient["doctor_id"],),
                    commit=True,
                )
            if patient["phone"]:
                send_sms(
                    patient["name"],
                    patient["phone"],
                    f"Treatment completed. Your digital prescription is ready in the patient dashboard.",
                )
            flash(f"{patient['name']} marked as treated.", "success")
        return redirect(url_for("doctor_dashboard"))

    queue = get_sorted_queue()
    completed = [
        dict(r)
        for r in query(
            """
            SELECT p.*, d.name AS doctor_name
            FROM patients p
            LEFT JOIN doctors d ON d.id = p.doctor_id
            WHERE p.status='completed'
            ORDER BY p.treated_at DESC
            LIMIT 10
            """
        )
    ]
    stats = {
        "approved_waiting": len(queue),
        "emergency_count": sum(1 for p in queue if p["emergency"]),
        "completed_today": query(
            "SELECT COUNT(*) FROM patients WHERE status='completed' AND treated_at LIKE ?",
            (date.today().strftime("%Y-%m-%d") + "%",),
            one=True,
        )[0],
        "available_doctors": query("SELECT COUNT(*) FROM doctors WHERE availability=1", one=True)[0],
    }
    return render_template("doctor.html", patients=queue, completed=completed, stats=stats)


@app.route("/api/queue")
@login_required(role=["doctor", "receptionist", "admin"])
def api_queue():
    q = get_sorted_queue()
    return jsonify(
        [
            {
                "id": p["id"],
                "queue_num": p["queue_number"],
                "name": p["name"],
                "department": p["department"],
                "severity": p["severity"],
                "emergency": bool(p["emergency"]),
                "wait": p["predicted_wait"],
                "arrival": p["arrival_time"][11:16] if p["arrival_time"] else "-",
                "priority": round(compute_priority(p), 1),
                "doctor_name": p.get("doctor_name") or "Pending",
            }
            for p in q
        ]
    )


@app.route("/api/stats")
@login_required(role=["doctor", "receptionist", "admin"])
def api_stats():
    today = date.today().strftime("%Y-%m-%d")
    return jsonify(
        {
            "total_today": query(
                "SELECT COUNT(*) FROM patients WHERE arrival_time LIKE ?",
                (today + "%",),
                one=True,
            )[0],
            "waiting": query(
                "SELECT COUNT(*) FROM patients WHERE review_status='approved' AND status='waiting'",
                one=True,
            )[0],
            "pending": query(
                "SELECT COUNT(*) FROM patients WHERE review_status='pending'",
                one=True,
            )[0],
            "emergencies": query(
                """
                SELECT COUNT(*) FROM patients
                WHERE arrival_time LIKE ? AND review_status='approved' AND emergency=1
                """,
                (today + "%",),
                one=True,
            )[0],
            "avg_wait": round(
                query(
                    """
                    SELECT AVG(predicted_wait) FROM patients
                    WHERE arrival_time LIKE ? AND review_status='approved'
                    """,
                    (today + "%",),
                    one=True,
                )[0]
                or 0,
                1,
            ),
            "doctors_avail": query("SELECT COUNT(*) FROM doctors WHERE availability=1", one=True)[0],
            "doctors_total": query("SELECT COUNT(*) FROM doctors", one=True)[0],
        }
    )


@app.route("/api/predict", methods=["POST"])
@login_required()
def api_predict():
    d = request.json
    return jsonify(
        {
            "predicted_wait": predict_wait(
                d["severity"],
                d["age"],
                d["emergency"],
                d["doc_available"],
                d["queue_length"],
                d["hour"],
            )
        }
    )


@app.route("/report/pdf")
@login_required(role=["doctor", "receptionist", "admin"])
def download_pdf():
    today = date.today().strftime("%Y-%m-%d")
    patients = [
        dict(r)
        for r in query(
            """
            SELECT p.*, d.name AS doctor_name
            FROM patients p
            LEFT JOIN doctors d ON d.id = p.doctor_id
            WHERE p.arrival_time LIKE ?
            """,
            (today + "%",),
        )
    ]
    doctors = [dict(r) for r in query("SELECT * FROM doctors")]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styl = getSampleStyleSheet()
    story = []
    story.append(
        Paragraph(
            "Hospital Queue - Daily Report",
            ParagraphStyle(
                "T",
                parent=styl["Title"],
                textColor=colors.HexColor("#1e3a5f"),
                fontSize=16,
            ),
        )
    )
    story.append(
        Paragraph(
            f"Date: {date.today().strftime('%d %B %Y')} | {datetime.now().strftime('%H:%M')}",
            styl["Normal"],
        )
    )
    story.append(Spacer(1, 12))
    avg_w = round(
        sum((p["predicted_wait"] or 0) for p in patients if p["review_status"] == "approved") / max(
            sum(1 for p in patients if p["review_status"] == "approved"), 1
        ),
        1,
    )
    stats_d = [
        ["Metric", "Value"],
        ["Total Forms", len(patients)],
        ["Approved Queue", sum(1 for p in patients if p["review_status"] == "approved")],
        ["Pending Reviews", sum(1 for p in patients if p["review_status"] == "pending")],
        ["Emergencies", sum(1 for p in patients if p["emergency"])],
        ["Avg Wait (min)", avg_w],
        ["Docs on Duty", sum(1 for d in doctors if d["availability"])],
        ["ML R2", WAIT_ML["r2_score"]],
        ["ML MAE", WAIT_ML["mae"]],
    ]
    t = Table(stats_d, colWidths=[220, 220])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 16))
    story.append(Paragraph("Patient Log", styl["Heading2"]))
    rows = [["Q#", "Name", "Dept", "Status", "Review", "Doctor", "Wait"]]
    for p in sorted(patients, key=lambda x: x["id"], reverse=True):
        rows.append(
            [
                p["queue_number"] or "-",
                p["name"],
                p["department"],
                p["status"],
                p["review_status"],
                p["doctor_name"] or "-",
                p["predicted_wait"] or "-",
            ]
        )
    pt = Table(rows, colWidths=[35, 90, 75, 55, 55, 90, 45])
    pt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("PADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(pt)
    doc.build(story)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"report_{today}.pdf",
        mimetype="application/pdf",
    )


@app.route("/prescription/<int:patient_id>/download")
@login_required()
def download_prescription(patient_id):
    patient = query(
        """
        SELECT p.*, d.name AS doctor_name
        FROM patients p
        LEFT JOIN doctors d ON d.id = p.doctor_id
        WHERE p.id=?
        """,
        (patient_id,),
        one=True,
    )
    if not patient or not patient["prescription_text"]:
        flash("Prescription not found.", "danger")
        return redirect(url_for("dashboard"))
    if session["role"] == "patient" and patient["user_id"] != session["user_id"]:
        flash("Unauthorised.", "danger")
        return redirect(url_for("patient_dashboard"))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styl = getSampleStyleSheet()
    story = []
    story.append(
        Paragraph(
            "Digital Prescription",
            ParagraphStyle(
                "PrescriptionTitle",
                parent=styl["Title"],
                textColor=colors.HexColor("#1e3a5f"),
                fontSize=18,
            ),
        )
    )
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Patient: {patient['name']}", styl["Normal"]))
    story.append(Paragraph(f"Age: {patient['age'] or '-'}", styl["Normal"]))
    story.append(Paragraph(f"Department: {patient['department'] or '-'}", styl["Normal"]))
    story.append(Paragraph(f"Doctor: {patient['doctor_name'] or 'Assigned doctor'}", styl["Normal"]))
    story.append(Paragraph(f"Treated At: {patient['treated_at'] or '-'}", styl["Normal"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Symptoms: {patient['symptoms'] or '-'}", styl["BodyText"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Treatment: {patient['treatment'] or '-'}", styl["BodyText"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Suggestion: {patient['suggestion'] or '-'}", styl["BodyText"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Prescription: {patient['prescription_text']}", styl["BodyText"]))
    doc.build(story)
    buf.seek(0)
    safe_name = patient["name"].replace(" ", "_")
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"prescription_{safe_name}_{patient_id}.pdf",
        mimetype="application/pdf",
    )


@app.template_filter("enumerate")
def jinja_enumerate(it):
    return list(enumerate(it))


init_db()


if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
    )
