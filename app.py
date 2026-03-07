from flask import Flask, render_template, request, redirect, url_for, session, abort
from cs50 import SQL
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from dotenv import load_dotenv
import os, time, random, string, smtplib
from email.message import EmailMessage

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("SECRET_KEY is not set!")

app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "doc", "docx", "txt"}
VALID_GRADES = {str(i) for i in range(1, 13)}
VALID_SECTIONS = set("ABCDEFG")

db = SQL("sqlite:///db.sqlite3")


def init_db():
    db.execute("""
        CREATE TABLE IF NOT EXISTS schools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            principal_id INTEGER,
            name TEXT NOT NULL DEFAULT 'Unknown School',
            email TEXT NOT NULL,
            code TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            attachment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            rating INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS circulars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            grade TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            attachment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS homework (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            grade TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            attachment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            recipient_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            is_handled INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS circulars_seen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            circular_id INTEGER NOT NULL,
            seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, circular_id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS homework_seen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            homework_id INTEGER NOT NULL,
            seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, homework_id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS news_seen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            news_id INTEGER NOT NULL,
            seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, news_id)
        )
    """)

    cols = {c["name"] for c in db.execute("SELECT name FROM pragma_table_info('users')")}
    if "is_logged_in" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN is_logged_in INTEGER DEFAULT 0")
    if "last_seen" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN last_seen INTEGER DEFAULT 0")
    if "role" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'student'")
    if "department" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN department TEXT")
    if "phone" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN phone TEXT")
    if "school_id" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN school_id INTEGER")

    school_cols = {c["name"] for c in db.execute("SELECT name FROM pragma_table_info('schools')")}
    if "name" not in school_cols:
        db.execute("ALTER TABLE schools ADD COLUMN name TEXT DEFAULT 'Unknown School'")


init_db()


# ── Helpers ───────────────────────────────────────────────────────────────────

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file):
    if not file or file.filename == "":
        return None
    if not allowed_file(file.filename):
        return None
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filename = secure_filename(file.filename)
    unique = f"{int(time.time())}_{filename}"
    file.save(os.path.join(UPLOAD_FOLDER, unique))
    return f"uploads/{unique}"


def sanitise_grades(raw_grades):
    return [g for g in raw_grades if g in VALID_GRADES]


def generate_school_code(length=8):
    return "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(length))


def send_school_code_email(to_email, code, school_name="your school"):
    host     = os.environ.get("SMTP_HOST")
    port     = int(os.environ.get("SMTP_PORT", "0") or 0)
    user     = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    sender   = os.environ.get("SMTP_FROM") or user

    if not host or not port or not sender:
        return False, "Email service is not configured."

    msg = EmailMessage()
    msg["Subject"] = "Your SchoolBridge School Code"
    msg["From"]    = sender
    msg["To"]      = to_email
    msg.set_content(
        f"Your SchoolBridge school code for {school_name} is: {code}\n\n"
        f"Share this code with teachers and students so they can register."
    )
    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            if user and password:
                server.login(user, password)
            server.send_message(msg)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("role") != role:
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def status_for(user, now_ts, idle_seconds=30):
    last_seen = int(user["last_seen"] or 0)
    if last_seen > 0 and (now_ts - last_seen) <= idle_seconds:
        return "online"
    if user["is_logged_in"] == 1:
        return "idle"
    return "offline"


# ── Middleware ────────────────────────────────────────────────────────────────

@app.before_request
def track_last_seen():
    if "user_id" in session:
        db.execute(
            "UPDATE users SET is_logged_in = 1, last_seen = ? WHERE id = ?",
            int(time.time()), session["user_id"]
        )


@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"]        = "no-cache"
    response.headers["Expires"]       = "0"
    return response


# ── Public routes ─────────────────────────────────────────────────────────────

@app.route("/")
def landing_page():
    feedbacks = db.execute("SELECT * FROM feedback ORDER BY created_at DESC LIMIT 6")
    return render_template("landing.html", feedbacks=feedbacks)


@app.route("/landing")
def landing():
    return redirect(url_for("landing_page"))


@app.route("/ping")
@login_required
def ping():
    db.execute(
        "UPDATE users SET is_logged_in = 1, last_seen = ? WHERE id = ?",
        int(time.time()), session["user_id"]
    )
    return ("", 204)


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username    = request.form.get("username", "").strip()
        password    = request.form.get("password", "")
        confirm     = request.form.get("confirm", "")
        role        = request.form.get("role", "").strip()
        department  = request.form.get("department", "").strip()
        phone       = request.form.get("phone", "").strip()
        school_code = request.form.get("school_code", "").strip().upper()
        email       = request.form.get("email", "").strip()
        school_name = request.form.get("school_name", "").strip()

        if role not in {"student", "teacher", "admin", "principal"}:
            return render_template("register.html", error="Please select a valid role.")

        if not username or not password or password != confirm:
            return render_template("register.html", error="Invalid input or passwords don't match.")

        if db.execute("SELECT id FROM users WHERE username = ?", username):
            return render_template("register.html", error="Username already taken.")

        school_id = None
        if role in {"teacher", "student"}:
            if not school_code:
                return render_template("register.html", error="School code is required.")
            school = db.execute("SELECT id FROM schools WHERE code = ?", school_code)
            if not school:
                return render_template("register.html", error="Invalid school code.")
            school_id = school[0]["id"]

        if role == "teacher":
            teacher_passwords = [
                p.strip() for p in os.environ.get("TEACHER_PASSWORDS", "").split(",") if p.strip()
            ]
            if not teacher_passwords:
                return render_template("register.html", error="Teacher passwords are not configured.")
            if password not in teacher_passwords:
                return render_template("register.html", error="Invalid teacher password.")
            if not department or not phone:
                return render_template("register.html", error="Department and phone are required for teachers.")

        code = None
        if role == "principal":
            principal_passwords = [
                p.strip() for p in os.environ.get("PRINCIPAL_PASSWORDS", "").split(",") if p.strip()
            ]
            if not principal_passwords:
                return render_template("register.html", error="Principal passwords are not configured.")
            if password not in principal_passwords:
                return render_template("register.html", error="Invalid principal password.")
            if not email:
                return render_template("register.html", error="Email is required for principals.")
            if not school_name:
                return render_template("register.html", error="School name is required for principals.")
            code = generate_school_code()
            while db.execute("SELECT 1 FROM schools WHERE code = ?", code):
                code = generate_school_code()

        hashed = generate_password_hash(password)
        db.execute(
            "INSERT INTO users (username, password, is_admin, role, department, phone) VALUES (?, ?, ?, ?, ?, ?)",
            username, hashed,
            1 if role == "admin" else 0,
            role,
            department if role == "teacher" else None,
            phone if role == "teacher" else None
        )
        new_user = db.execute("SELECT id FROM users WHERE username = ?", username)[0]

        if school_id:
            db.execute("UPDATE users SET school_id = ? WHERE id = ?", school_id, new_user["id"])

        if role == "principal":
            db.execute(
                "INSERT INTO schools (principal_id, name, email, code) VALUES (?, ?, ?, ?)",
                new_user["id"], school_name, email, code
            )
            ok, err = send_school_code_email(email, code, school_name)
            if ok:
                return render_template("register.html", success="Principal registered. School code sent to your email.")
            return render_template(
                "register.html",
                success=f"Principal registered. School code: {code}",
                error="Email failed — save your code now!"
            )

        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            return render_template("login.html", error="Missing credentials.")

        rows = db.execute("SELECT * FROM users WHERE username = ?", username)
        if len(rows) != 1 or not check_password_hash(rows[0]["password"], password):
            return render_template("login.html", error="Invalid username or password.")

        user = rows[0]
        session["user_id"]  = user["id"]
        session["username"] = user["username"]
        session["is_admin"] = bool(user["is_admin"])
        session["role"]     = user["role"]

        db.execute(
            "UPDATE users SET is_logged_in = 1, last_seen = ? WHERE id = ?",
            int(time.time()), user["id"]
        )
        return redirect(url_for("home"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    db.execute(
        "UPDATE users SET is_logged_in = 0, last_seen = ? WHERE id = ?",
        int(time.time()), session["user_id"]
    )
    session.clear()
    return redirect(url_for("login"))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    error   = ""
    success = ""
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new     = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if not current or not new or not confirm:
            error = "All fields are required."
        elif new != confirm:
            error = "New passwords do not match."
        else:
            user = db.execute("SELECT password FROM users WHERE id = ?", session["user_id"])
            if not user or not check_password_hash(user[0]["password"], current):
                error = "Current password is incorrect."
            else:
                db.execute(
                    "UPDATE users SET password = ? WHERE id = ?",
                    generate_password_hash(new), session["user_id"]
                )
                success = "Password updated."
    return render_template("settings.html", error=error, success=success)


# ── Home dispatcher ───────────────────────────────────────────────────────────

@app.route("/home", methods=["GET", "POST"])
@login_required
def home():
    role   = session.get("role")
    now_ts = int(time.time())

    if role == "admin":
        return redirect(url_for("admin_dashboard"))

    elif role == "principal":
        school    = db.execute("SELECT id FROM schools WHERE principal_id = ?", session["user_id"])
        school_id = school[0]["id"] if school else None
        students  = []
        teachers  = []
        if school_id:
            students = db.execute("""
                SELECT u.id, u.username, g.grade, u.is_logged_in, u.last_seen
                FROM users u LEFT JOIN grades g ON u.id = g.user_id
                WHERE u.role = 'student' AND u.school_id = ? ORDER BY u.username
            """, school_id)
            teachers = db.execute("""
                SELECT u.id, u.username, u.department, u.phone, u.is_logged_in, u.last_seen
                FROM users u WHERE u.role = 'teacher' AND u.school_id = ? ORDER BY u.username
            """, school_id)
        for u in students:
            u["status"] = status_for(u, now_ts)
        for t in teachers:
            t["status"] = status_for(t, now_ts)
        return render_template("principal_dashboard.html", students=students, teachers=teachers)

    elif role == "teacher":
        uid    = session["user_id"]
        counts = {k: 0 for k in [
            "inbox_unread", "inbox_received", "student_unread", "student_received",
            "sent_students", "sent_admin", "sent_circulars", "sent_homework",
            "news_unread", "news_total"
        ]}
        students = db.execute("""
            SELECT u.username, g.grade, g.section, g.dob FROM users u
            JOIN grades g ON u.id = g.user_id WHERE u.role = 'student' ORDER BY u.username
        """)
        counts["inbox_unread"]     = db.execute("SELECT COUNT(*) AS c FROM messages m JOIN users u ON m.sender_id = u.id WHERE m.recipient_id = ? AND m.is_read = 0 AND u.role IN ('admin','teacher')", uid)[0]["c"]
        counts["inbox_received"]   = db.execute("SELECT COUNT(*) AS c FROM messages m JOIN users u ON m.sender_id = u.id WHERE m.recipient_id = ? AND u.role IN ('admin','teacher')", uid)[0]["c"]
        counts["student_unread"]   = db.execute("SELECT COUNT(*) AS c FROM messages m JOIN users u ON m.sender_id = u.id WHERE m.recipient_id = ? AND m.is_read = 0 AND u.role = 'student'", uid)[0]["c"]
        counts["student_received"] = db.execute("SELECT COUNT(*) AS c FROM messages m JOIN users u ON m.sender_id = u.id WHERE m.recipient_id = ? AND u.role = 'student'", uid)[0]["c"]
        counts["sent_students"]    = db.execute("SELECT COUNT(*) AS c FROM messages m JOIN users u ON m.recipient_id = u.id WHERE m.sender_id = ? AND u.role = 'student'", uid)[0]["c"]
        counts["sent_admin"]       = db.execute("SELECT COUNT(*) AS c FROM messages m JOIN users u ON m.recipient_id = u.id WHERE m.sender_id = ? AND u.role = 'admin'", uid)[0]["c"]
        counts["sent_circulars"]   = db.execute("SELECT COUNT(*) AS c FROM circulars WHERE sender_id = ?", uid)[0]["c"]
        counts["sent_homework"]    = db.execute("SELECT COUNT(*) AS c FROM homework WHERE sender_id = ?", uid)[0]["c"]
        counts["news_total"]       = db.execute("SELECT COUNT(*) AS c FROM news")[0]["c"]
        counts["news_unread"]      = db.execute("SELECT COUNT(*) AS c FROM news n WHERE n.id NOT IN (SELECT news_id FROM news_seen WHERE user_id = ?)", uid)[0]["c"]
        return render_template("teacher_home.html", students=students, counts=counts)

    else:
        uid            = session["user_id"]
        entry          = db.execute("SELECT * FROM grades WHERE user_id = ?", uid)
        info_submitted = bool(entry)
        message        = ""
        error          = ""
        counts         = {k: 0 for k in [
            "total", "inbox_unread", "inbox_total", "sent_total",
            "circulars_unread", "circulars_total",
            "news_unread", "news_total",
            "homework_unread", "homework_total"
        ]}
        if request.args.get("need_info"):
            error = "Please complete your information first."
        if request.method == "POST" and not info_submitted:
            grade   = request.form.get("grade", "").strip()
            section = request.form.get("section", "").strip().upper()
            dob     = request.form.get("dob", "").strip()
            if grade in VALID_GRADES and section in VALID_SECTIONS and dob:
                db.execute(
                    "INSERT INTO grades (user_id, name, grade, section, dob) VALUES (?, ?, ?, ?, ?)",
                    uid, session.get("username", ""), grade, section, dob
                )
                info_submitted = True
                message = "Info submitted!"
            else:
                error = "All fields required. Section must be A-G."
        student_info = entry[0] if entry else None
        if student_info:
            g = student_info["grade"]
            counts["inbox_unread"]     = db.execute("SELECT COUNT(*) AS c FROM messages WHERE recipient_id = ? AND is_read = 0", uid)[0]["c"]
            counts["inbox_total"]      = db.execute("SELECT COUNT(*) AS c FROM messages WHERE recipient_id = ?", uid)[0]["c"]
            counts["sent_total"]       = db.execute("SELECT COUNT(*) AS c FROM messages WHERE sender_id = ?", uid)[0]["c"]
            counts["circulars_unread"] = db.execute("SELECT COUNT(*) AS c FROM circulars c WHERE c.grade = ? AND c.id NOT IN (SELECT circular_id FROM circulars_seen WHERE user_id = ?)", g, uid)[0]["c"]
            counts["circulars_total"]  = db.execute("SELECT COUNT(*) AS c FROM circulars WHERE grade = ?", g)[0]["c"]
            counts["homework_unread"]  = db.execute("SELECT COUNT(*) AS c FROM homework h WHERE h.grade = ? AND h.id NOT IN (SELECT homework_id FROM homework_seen WHERE user_id = ?)", g, uid)[0]["c"]
            counts["homework_total"]   = db.execute("SELECT COUNT(*) AS c FROM homework WHERE grade = ?", g)[0]["c"]
            counts["news_unread"]      = db.execute("SELECT COUNT(*) AS c FROM news n WHERE n.id NOT IN (SELECT news_id FROM news_seen WHERE user_id = ?)", uid)[0]["c"]
            counts["news_total"]       = db.execute("SELECT COUNT(*) AS c FROM news")[0]["c"]
            counts["total"]            = counts["inbox_unread"] + counts["circulars_unread"] + counts["homework_unread"] + counts["news_unread"]
        return render_template(
            "student_dashboard.html",
            info_submitted=info_submitted, message=message, error=error,
            name_prefill=session.get("username", ""),
            student_info=student_info, counts=counts
        )


# ── Shared ────────────────────────────────────────────────────────────────────

@app.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    success = "Thank you for your feedback!" if request.args.get("submitted") else ""
    error   = ""
    if request.method == "POST":
        message = request.form.get("message", "").strip()
        rating  = request.form.get("rating", "5").strip()
        if not message:
            error = "Message cannot be empty."
        elif not rating.isdigit() or not (1 <= int(rating) <= 5):
            error = "Invalid rating."
        else:
            db.execute(
                "INSERT INTO feedback (name, role, message, rating) VALUES (?, ?, ?, ?)",
                session["username"], session["role"], message, int(rating)
            )
            return redirect(url_for("feedback", submitted=1))
    feedbacks = db.execute("SELECT * FROM feedback ORDER BY created_at DESC")
    return render_template("feedback.html", success=success, error=error, feedbacks=feedbacks)


@app.route("/school_news")
@login_required
def school_news():
    news = db.execute("""
        SELECT n.id, n.title, n.body, n.attachment, n.created_at, u.username AS sender
        FROM news n JOIN users u ON n.sender_id = u.id ORDER BY n.created_at DESC
    """)
    if session.get("role") in ("student", "teacher") and news:
        for n in news:
            db.execute(
                "INSERT OR IGNORE INTO news_seen (user_id, news_id) VALUES (?, ?)",
                session["user_id"], n["id"]
            )
    return render_template("school_news.html", news=news)


# ── Student routes ────────────────────────────────────────────────────────────

def _require_grade():
    return db.execute("SELECT 1 FROM grades WHERE user_id = ? LIMIT 1", session["user_id"])


@app.route("/send_request", methods=["GET", "POST"])
@login_required
@role_required("student")
def send_request():
    if not _require_grade():
        return redirect(url_for("home", need_info=1))
    if request.method == "POST":
        message  = request.form.get("message", "").strip()
        if not message:
            return render_template("send_request.html", error="Message cannot be empty.")
        teachers = db.execute("SELECT id FROM users WHERE role = 'teacher'")
        if not teachers:
            return render_template("send_request.html", error="No teacher available.")
        for t in teachers:
            db.execute(
                "INSERT INTO messages (sender_id, recipient_id, message) VALUES (?, ?, ?)",
                session["user_id"], t["id"], message
            )
        return render_template("send_request.html", success="Message sent!")
    return render_template("send_request.html")


@app.route("/student_inbox")
@login_required
@role_required("student")
def student_inbox():
    if not _require_grade():
        return redirect(url_for("home", need_info=1))
    messages = db.execute("""
        SELECT m.message, m.created_at, u.username AS sender
        FROM messages m JOIN users u ON m.sender_id = u.id
        WHERE m.recipient_id = ? ORDER BY m.created_at DESC
    """, session["user_id"])
    db.execute("UPDATE messages SET is_read = 1 WHERE recipient_id = ?", session["user_id"])
    return render_template("student_inbox.html", messages=messages)


@app.route("/clear_inbox", methods=["POST"])
@login_required
@role_required("student")
def clear_inbox():
    if not _require_grade():
        return redirect(url_for("home", need_info=1))
    db.execute("DELETE FROM messages WHERE recipient_id = ?", session["user_id"])
    return redirect(url_for("student_inbox"))


@app.route("/student_circulars")
@login_required
@role_required("student")
def student_circulars():
    if not _require_grade():
        return redirect(url_for("home", need_info=1))
    grade = db.execute("SELECT grade FROM grades WHERE user_id = ? LIMIT 1", session["user_id"])[0]["grade"]
    circulars = db.execute("""
        SELECT c.id, c.title, c.body, c.attachment, c.created_at, u.username AS sender
        FROM circulars c JOIN users u ON c.sender_id = u.id
        WHERE c.grade = ? ORDER BY c.created_at DESC
    """, grade)
    for c in circulars:
        db.execute(
            "INSERT OR IGNORE INTO circulars_seen (user_id, circular_id) VALUES (?, ?)",
            session["user_id"], c["id"]
        )
    return render_template("student_circulars.html", circulars=circulars, grade=grade)


@app.route("/student_homework")
@login_required
@role_required("student")
def student_homework():
    if not _require_grade():
        return redirect(url_for("home", need_info=1))
    grade = db.execute("SELECT grade FROM grades WHERE user_id = ? LIMIT 1", session["user_id"])[0]["grade"]
    homework = db.execute("""
        SELECT h.id, h.title, h.body, h.attachment, h.created_at, u.username AS sender
        FROM homework h JOIN users u ON h.sender_id = u.id
        WHERE h.grade = ? ORDER BY h.created_at DESC
    """, grade)
    for h in homework:
        db.execute(
            "INSERT OR IGNORE INTO homework_seen (user_id, homework_id) VALUES (?, ?)",
            session["user_id"], h["id"]
        )
    return render_template("student_homework.html", homework=homework, grade=grade)


# ── Teacher routes ────────────────────────────────────────────────────────────

@app.route("/teacher_messages", methods=["GET", "POST"])
@login_required
@role_required("teacher")
def teacher_messages():
    students = db.execute("""
        SELECT u.id, u.username, g.grade FROM users u
        JOIN grades g ON u.id = g.user_id WHERE u.role = 'student' ORDER BY u.username
    """)
    if request.method == "POST":
        student_id = request.form.get("student_id")
        message    = request.form.get("message", "").strip()
        if student_id and message:
            db.execute(
                "INSERT INTO messages (sender_id, recipient_id, message) VALUES (?, ?, ?)",
                session["user_id"], student_id, message
            )
            return redirect(url_for("teacher_messages"))
    messages = db.execute("""
        SELECT m.id, m.message, m.created_at, u.username AS sender
        FROM messages m JOIN users u ON m.sender_id = u.id
        WHERE m.recipient_id = ? AND u.role IN ('admin','teacher') ORDER BY m.created_at DESC
    """, session["user_id"])
    db.execute("""
        UPDATE messages SET is_read = 1 WHERE recipient_id = ?
        AND sender_id IN (SELECT id FROM users WHERE role IN ('admin','teacher'))
    """, session["user_id"])
    return render_template("teacher_messages.html", students=students, messages=messages)


@app.route("/teacher_student_inbox")
@login_required
@role_required("teacher")
def teacher_student_inbox():
    messages = db.execute("""
        SELECT m.id, m.message, m.created_at, u.username AS sender
        FROM messages m JOIN users u ON m.sender_id = u.id
        WHERE m.recipient_id = ? AND u.role = 'student' ORDER BY m.created_at DESC
    """, session["user_id"])
    db.execute("""
        UPDATE messages SET is_read = 1 WHERE recipient_id = ?
        AND sender_id IN (SELECT id FROM users WHERE role = 'student')
    """, session["user_id"])
    return render_template("teacher_student_inbox.html", messages=messages)


@app.route("/teacher_clear_inbox", methods=["POST"])
@login_required
@role_required("teacher")
def teacher_clear_inbox():
    db.execute("DELETE FROM messages WHERE recipient_id = ?", session["user_id"])
    return redirect(url_for("teacher_messages"))


@app.route("/teacher_circulars", methods=["GET", "POST"])
@login_required
@role_required("teacher")
def teacher_circulars():
    grades  = db.execute("SELECT DISTINCT grade FROM grades ORDER BY grade")
    success = ""
    error   = ""
    if request.method == "POST":
        selected_grades = sanitise_grades(request.form.getlist("grades"))
        title      = request.form.get("title", "").strip()
        body       = request.form.get("body", "").strip()
        attachment = save_upload(request.files.get("attachment"))
        if not selected_grades:
            error = "Select at least one valid grade."
        elif not title or not body:
            error = "Title and body are required."
        else:
            for g in selected_grades:
                db.execute(
                    "INSERT INTO circulars (sender_id, grade, title, body, attachment) VALUES (?, ?, ?, ?, ?)",
                    session["user_id"], g, title, body, attachment
                )
            success = "Circular sent!"
    circulars = db.execute("""
        SELECT id, grade, title, body, attachment, created_at
        FROM circulars WHERE sender_id = ? ORDER BY created_at DESC
    """, session["user_id"])
    return render_template("teacher_circulars.html", grades=grades, circulars=circulars,
                           success=success, error=error)


@app.route("/teacher_homework", methods=["GET", "POST"])
@login_required
@role_required("teacher")
def teacher_homework():
    grades  = db.execute("SELECT DISTINCT grade FROM grades ORDER BY grade")
    success = ""
    error   = ""
    if request.method == "POST":
        selected_grades = sanitise_grades(request.form.getlist("grades"))
        title      = request.form.get("title", "").strip()
        body       = request.form.get("body", "").strip()
        attachment = save_upload(request.files.get("attachment"))
        if not selected_grades:
            error = "Select at least one valid grade."
        elif not title or not body:
            error = "Title and body are required."
        else:
            for g in selected_grades:
                db.execute(
                    "INSERT INTO homework (sender_id, grade, title, body, attachment) VALUES (?, ?, ?, ?, ?)",
                    session["user_id"], g, title, body, attachment
                )
            success = "Homework sent!"
    homework = db.execute("""
        SELECT id, grade, title, body, attachment, created_at
        FROM homework WHERE sender_id = ? ORDER BY created_at DESC
    """, session["user_id"])
    return render_template("teacher_homework.html", grades=grades, homework=homework,
                           success=success, error=error)


@app.route("/teacher_to_admin", methods=["GET", "POST"])
@login_required
@role_required("teacher")
def teacher_to_admin():
    abort(403)


# ── Admin routes ──────────────────────────────────────────────────────────────

@app.route("/admin_dashboard")
@login_required
@role_required("admin")
def admin_dashboard():
    now_ts = int(time.time())

    students = db.execute("""
        SELECT u.id, u.username, g.grade, u.role, u.is_logged_in, u.last_seen
        FROM users u LEFT JOIN grades g ON u.id = g.user_id WHERE u.role = 'student'
    """)
    teachers = db.execute("""
        SELECT u.id, u.username, u.role, u.is_logged_in, u.last_seen
        FROM users u WHERE u.role = 'teacher' ORDER BY u.username
    """)
    principals = db.execute("""
        SELECT u.id, u.username, u.is_logged_in, u.last_seen,
               s.name AS school_name, s.code AS school_code
        FROM users u LEFT JOIN schools s ON s.principal_id = u.id
        WHERE u.role = 'principal' ORDER BY u.username
    """)

    for u in students:
        u["status"] = status_for(u, now_ts)
    for t in teachers:
        t["status"] = status_for(t, now_ts)
    for p in principals:
        p["status"] = status_for(p, now_ts)

    counts = {
        "inbox_unread":   db.execute("SELECT COUNT(*) AS c FROM messages WHERE recipient_id = ? AND is_read = 0", session["user_id"])[0]["c"],
        "inbox_received": db.execute("SELECT COUNT(*) AS c FROM messages WHERE recipient_id = ?", session["user_id"])[0]["c"],
        "sent_students":  db.execute("SELECT COUNT(*) AS c FROM messages m JOIN users u ON m.recipient_id = u.id WHERE m.sender_id = ? AND u.role = 'student'", session["user_id"])[0]["c"],
        "sent_teachers":  db.execute("SELECT COUNT(*) AS c FROM messages m JOIN users u ON m.recipient_id = u.id WHERE m.sender_id = ? AND u.role = 'teacher'", session["user_id"])[0]["c"],
        "sent_news":      db.execute("SELECT COUNT(*) AS c FROM news WHERE sender_id = ?", session["user_id"])[0]["c"],
        "sent_circulars": db.execute("SELECT COUNT(*) AS c FROM circulars WHERE sender_id = ?", session["user_id"])[0]["c"],
    }

    return render_template(
        "admin_dashboard.html",
        users=students, teachers=teachers, principals=principals, counts=counts
    )


@app.route("/admin_broadcast", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_broadcast():
    grades   = db.execute("SELECT DISTINCT grade FROM grades ORDER BY grade")
    teachers = db.execute("SELECT id, username FROM users WHERE role = 'teacher' ORDER BY username")
    news     = db.execute("""
        SELECT n.id, n.title, n.body, n.attachment, n.created_at, u.username AS sender
        FROM news n JOIN users u ON n.sender_id = u.id ORDER BY n.created_at DESC
    """)
    students = db.execute("""
        SELECT u.username, g.grade FROM users u
        JOIN grades g ON u.id = g.user_id WHERE u.role='student'
    """)
    success = ""
    error   = ""

    if request.method == "POST":
        target  = request.form.get("target")
        message = request.form.get("message", "").strip()

        if target == "news":
            title      = request.form.get("title", "").strip()
            body       = request.form.get("body", "").strip()
            attachment = save_upload(request.files.get("attachment"))
            if not title or not body:
                error = "Title and body are required."
            else:
                db.execute(
                    "INSERT INTO news (sender_id, title, body, attachment) VALUES (?, ?, ?, ?)",
                    session["user_id"], title, body, attachment
                )
                success = "News posted!"

        elif target == "admin_circular":
            selected_grades = sanitise_grades(request.form.getlist("grades"))
            title      = request.form.get("title", "").strip()
            body       = request.form.get("body", "").strip()
            attachment = save_upload(request.files.get("attachment"))
            if not selected_grades:
                error = "Select at least one valid grade."
            elif not title or not body:
                error = "Title and body are required."
            else:
                for g in selected_grades:
                    db.execute(
                        "INSERT INTO circulars (sender_id, grade, title, body, attachment) VALUES (?, ?, ?, ?, ?)",
                        session["user_id"], g, title, body, attachment
                    )
                success = "Circular sent!"

        elif target == "teachers":
            if not message:
                error = "Message cannot be empty."
            else:
                selected_teachers = request.form.getlist("teachers")
                if "ALL" in selected_teachers or not selected_teachers:
                    recipients = db.execute("SELECT id FROM users WHERE role = 'teacher'")
                else:
                    placeholders = ", ".join(["?"] * len(selected_teachers))
                    recipients = db.execute(
                        f"SELECT id FROM users WHERE role = 'teacher' AND id IN ({placeholders})",
                        *selected_teachers
                    )
                for r in recipients:
                    db.execute(
                        "INSERT INTO messages (sender_id, recipient_id, message) VALUES (?, ?, ?)",
                        session["user_id"], r["id"], message
                    )
                success = "Message sent to teachers!"

        else:
            if not message:
                error = "Message cannot be empty."
            else:
                selected_grades = sanitise_grades(request.form.getlist("grades"))
                if "ALL" in request.form.getlist("grades") or not selected_grades:
                    recipients = db.execute("SELECT id FROM users WHERE role = 'student'")
                else:
                    placeholders = ", ".join(["?"] * len(selected_grades))
                    recipients = db.execute(
                        f"SELECT DISTINCT u.id FROM users u JOIN grades g ON u.id = g.user_id WHERE g.grade IN ({placeholders})",
                        *selected_grades
                    )
                for r in recipients:
                    db.execute(
                        "INSERT INTO messages (sender_id, recipient_id, message) VALUES (?, ?, ?)",
                        session["user_id"], r["id"], message
                    )
                success = "Message sent to students!"

    return render_template("admin_broadcast.html", grades=grades, students=students,
                           teachers=teachers, news=news, success=success, error=error)


@app.route("/admin_messages")
@login_required
@role_required("admin")
def admin_messages():
    messages = db.execute("""
        SELECT m.id, m.message, m.created_at, u.username AS sender
        FROM messages m JOIN users u ON m.sender_id = u.id
        WHERE m.recipient_id = ? ORDER BY m.created_at DESC
    """, session["user_id"])
    db.execute("UPDATE messages SET is_read = 1 WHERE recipient_id = ?", session["user_id"])
    return render_template("admin_messages.html", messages=messages)


@app.route("/admin_clear_inbox", methods=["POST"])
@login_required
@role_required("admin")
def admin_clear_inbox():
    db.execute("DELETE FROM messages WHERE recipient_id = ?", session["user_id"])
    return redirect(url_for("admin_messages"))


@app.route("/handle_message", methods=["POST"])
@login_required
@role_required("admin")
def handle_message():
    msg_id = request.form.get("msg_id")
    if msg_id:
        db.execute("UPDATE messages SET is_handled = 1 WHERE id = ?", msg_id)
    return redirect(url_for("admin_messages"))


@app.route("/admin_grades", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_grades():
    grades = db.execute("SELECT DISTINCT grade FROM grades ORDER BY grade")
    if request.method == "POST":
        selected_grade = request.form.get("grade", "").strip()
        if selected_grade not in VALID_GRADES:
            return render_template("admin_grades.html", grades=grades, students=[], error="Invalid grade.")
        students = db.execute("""
            SELECT u.username, g.grade, u.id FROM users u
            JOIN grades g ON u.id = g.user_id WHERE g.grade = ? ORDER BY u.username
        """, selected_grade)
    else:
        students = db.execute("""
            SELECT u.username, g.grade, u.id FROM users u
            JOIN grades g ON u.id = g.user_id WHERE u.role = 'student' ORDER BY u.username
        """)
    return render_template("admin_grades.html", grades=grades, students=students)


@app.route("/delete_user", methods=["POST"])
@login_required
@role_required("admin")
def delete_user():
    username = request.form.get("username")
    if not username:
        return redirect(url_for("admin_dashboard"))
    user = db.execute("SELECT id, is_admin FROM users WHERE username = ?", username)
    if not user or user[0]["is_admin"] == 1:
        return redirect(url_for("admin_dashboard"))
    uid = user[0]["id"]
    db.execute("DELETE FROM messages WHERE sender_id = ? OR recipient_id = ?", uid, uid)
    db.execute("DELETE FROM grades WHERE user_id = ?", uid)
    db.execute("DELETE FROM circulars_seen WHERE user_id = ?", uid)
    db.execute("DELETE FROM homework_seen WHERE user_id = ?", uid)
    db.execute("DELETE FROM news_seen WHERE user_id = ?", uid)
    db.execute("DELETE FROM users WHERE id = ?", uid)
    return redirect(url_for("admin_dashboard"))


# ── Principal routes ──────────────────────────────────────────────────────────

@app.route("/principal_messages", methods=["GET", "POST"])
@login_required
@role_required("principal")
def principal_messages():
    school    = db.execute("SELECT id FROM schools WHERE principal_id = ?", session["user_id"])
    school_id = school[0]["id"] if school else None
    admins    = db.execute("SELECT id, username FROM users WHERE role = 'admin' ORDER BY username")
    teachers  = []
    students  = []
    if school_id:
        teachers = db.execute(
            "SELECT id, username FROM users WHERE role = 'teacher' AND school_id = ? ORDER BY username",
            school_id
        )
        students = db.execute(
            "SELECT id, username FROM users WHERE role = 'student' AND school_id = ? ORDER BY username",
            school_id
        )
    if request.method == "POST":
        recipient_id = request.form.get("recipient_id")
        message      = request.form.get("message", "").strip()
        if recipient_id and message:
            db.execute(
                "INSERT INTO messages (sender_id, recipient_id, message) VALUES (?, ?, ?)",
                session["user_id"], recipient_id, message
            )
            return redirect(url_for("principal_messages"))
    messages = db.execute("""
        SELECT m.message, m.created_at, u.username AS sender
        FROM messages m JOIN users u ON m.sender_id = u.id
        WHERE m.recipient_id = ? ORDER BY m.created_at DESC
    """, session["user_id"])
    db.execute("UPDATE messages SET is_read = 1 WHERE recipient_id = ?", session["user_id"])
    return render_template(
        "principal_messages.html",
        teachers=teachers, students=students, admins=admins, messages=messages
    )


if __name__ == "__main__":
    app.run(debug=False)