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
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}
VALID_GRADES = {str(i) for i in range(1, 13)}
VALID_SECTIONS = set("ABCDEFG")
SCHOOL_NAME_OPTIONS = [
    s.strip() for s in os.environ.get("SCHOOL_NAME_OPTIONS", "").split(",") if s.strip()
]

# ── Database connection ───────────────────────────────────────────────────────
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)
if not _db_url:
    raise RuntimeError("DATABASE_URL must be set to a PostgreSQL connection string.")
if not _db_url.startswith("postgresql://"):
    raise RuntimeError("DATABASE_URL must start with postgresql://")
DATABASE_URL = _db_url
db = SQL(DATABASE_URL)


def init_db():
    pk = "SERIAL PRIMARY KEY"

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS users (
            id {pk},
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            role TEXT DEFAULT 'student',
            department TEXT,
            phone TEXT,
            email TEXT,
            is_librarian INTEGER DEFAULT 0,
            school_id INTEGER,
            profile_pic TEXT,
            is_logged_in INTEGER DEFAULT 0,
            last_seen INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS grades (
            id {pk},
            user_id INTEGER NOT NULL,
            name TEXT,
            grade TEXT,
            section TEXT,
            dob TEXT,
            roll_number TEXT
        )
    """)

    db.execute(f"""
        CREATE TABLE IF NOT EXISTS schools (
            id {pk},
            principal_id INTEGER,
            name TEXT NOT NULL DEFAULT 'Unknown School',
            email TEXT NOT NULL,
            code TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS news (
            id {pk},
            sender_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            attachment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS feedback (
            id {pk},
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            rating INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS circulars (
            id {pk},
            sender_id INTEGER NOT NULL,
            grade TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            attachment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS homework (
            id {pk},
            sender_id INTEGER NOT NULL,
            grade TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            attachment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS messages (
            id {pk},
            sender_id INTEGER NOT NULL,
            recipient_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            is_handled INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS circulars_seen (
            id {pk},
            user_id INTEGER NOT NULL,
            circular_id INTEGER NOT NULL,
            seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, circular_id)
        )
    """)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS homework_seen (
            id {pk},
            user_id INTEGER NOT NULL,
            homework_id INTEGER NOT NULL,
            seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, homework_id)
        )
    """)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS news_seen (
            id {pk},
            user_id INTEGER NOT NULL,
            news_id INTEGER NOT NULL,
            seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, news_id)
        )
    """)

    db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_logged_in INTEGER DEFAULT 0")
    db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen INTEGER DEFAULT 0")
    db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'student'")
    db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS department TEXT")
    db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT")
    db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS school_id INTEGER")
    db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_pic TEXT")
    db.execute("ALTER TABLE feedback ADD COLUMN IF NOT EXISTS user_id INTEGER")
    db.execute("ALTER TABLE schools ADD COLUMN IF NOT EXISTS name TEXT DEFAULT 'Unknown School'")
    db.execute("ALTER TABLE grades ADD COLUMN IF NOT EXISTS roll_number TEXT")

    # ── NEW TABLES ──────────────────────────────────────────────────────────
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS results (
            id {pk},
            student_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            exam_name TEXT NOT NULL,
            subject TEXT NOT NULL,
            marks REAL NOT NULL,
            out_of REAL NOT NULL DEFAULT 100,
            grade TEXT,
            remarks TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS attendance (
            id {pk},
            student_id INTEGER NOT NULL,
            marked_by INTEGER NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'present',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, date)
        )
    """)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS library_records (
            id {pk},
            student_id INTEGER NOT NULL,
            librarian_id INTEGER NOT NULL,
            book_title TEXT NOT NULL,
            author TEXT,
            issued_date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            returned_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS canteen_menu (
            id {pk},
            item_name TEXT NOT NULL,
            price REAL NOT NULL,
            emoji TEXT,
            day_of_week TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS calendar_events (
            id {pk},
            created_by INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            event_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS student_reports (
            id {pk},
            student_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            report_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            attachment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # librarian flag on users
    db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_librarian INTEGER DEFAULT 0")
    db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT")


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


def save_profile_upload(file):
    if not file or file.filename == "":
        return None
    if "." not in file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        return None
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filename = secure_filename(file.filename)
    unique = f"profile_{int(time.time())}_{filename}"
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
    password = (os.environ.get("SMTP_PASS") or "").replace(" ", "")
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


def send_generic_email(to_email, subject, body, from_name="SchoolBridge"):
    host     = os.environ.get("SMTP_HOST")
    port     = int(os.environ.get("SMTP_PORT", "0") or 0)
    user     = os.environ.get("SMTP_USER")
    password = (os.environ.get("SMTP_PASS") or "").replace(" ", "")
    sender   = os.environ.get("SMTP_FROM") or user
    if not host or not port or not sender:
        return False, "Email service not configured."
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"]    = f"{from_name} <{sender}>"
    msg["To"]      = to_email
    msg.set_content(body)
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


# ── Routes (imported from separate files, registered on app directly) ─────────

from routes.auth      import register, login, logout, home, settings, profile_view
from routes.student   import (send_request, student_inbox, clear_inbox,
                               student_circulars, student_homework,
                               student_results, student_attendance,
                               student_library, student_canteen,
                               student_calendar, student_send_email,
                               student_reports)
from routes.teacher   import (teacher_messages, teacher_student_inbox,
                               teacher_clear_inbox, teacher_circulars,
                               teacher_homework, teacher_to_admin,
                               teacher_results, teacher_attendance,
                               teacher_reports, teacher_calendar)
from routes.admin     import admin_dashboard, admin_broadcast, admin_messages, admin_clear_inbox, handle_message, admin_grades, delete_user, admin_canteen, admin_calendar
from routes.principal import principal_messages
from routes.librarian import librarian_library

app.add_url_rule("/register",             "register",             register,             methods=["GET", "POST"])
app.add_url_rule("/login",                "login",                login,                methods=["GET", "POST"])
app.add_url_rule("/logout",               "logout",               logout)
app.add_url_rule("/home",                 "home",                 home,                 methods=["GET", "POST"])
app.add_url_rule("/settings",             "settings",             settings,             methods=["GET", "POST"])
app.add_url_rule("/profile/<int:user_id>", "profile_view",        profile_view)

app.add_url_rule("/send_request",         "send_request",         send_request,         methods=["GET", "POST"])
app.add_url_rule("/student_inbox",        "student_inbox",        student_inbox)
app.add_url_rule("/clear_inbox",          "clear_inbox",          clear_inbox,          methods=["POST"])
app.add_url_rule("/student_circulars",    "student_circulars",    student_circulars)
app.add_url_rule("/student_homework",     "student_homework",     student_homework)
app.add_url_rule("/student_results",      "student_results",      student_results)
app.add_url_rule("/student_attendance",   "student_attendance",   student_attendance)
app.add_url_rule("/student_library",      "student_library",      student_library)
app.add_url_rule("/student_canteen",      "student_canteen",      student_canteen)
app.add_url_rule("/student_calendar",     "student_calendar",     student_calendar)
app.add_url_rule("/student_send_email",   "student_send_email",   student_send_email,   methods=["POST"])
app.add_url_rule("/student_reports",      "student_reports",      student_reports)

app.add_url_rule("/teacher_messages",     "teacher_messages",     teacher_messages,     methods=["GET", "POST"])
app.add_url_rule("/teacher_student_inbox","teacher_student_inbox",teacher_student_inbox)
app.add_url_rule("/teacher_clear_inbox",  "teacher_clear_inbox",  teacher_clear_inbox,  methods=["POST"])
app.add_url_rule("/teacher_circulars",    "teacher_circulars",    teacher_circulars,    methods=["GET", "POST"])
app.add_url_rule("/teacher_homework",     "teacher_homework",     teacher_homework,     methods=["GET", "POST"])
app.add_url_rule("/teacher_to_admin",     "teacher_to_admin",     teacher_to_admin,     methods=["GET", "POST"])
app.add_url_rule("/teacher_results",      "teacher_results",      teacher_results,      methods=["GET", "POST"])
app.add_url_rule("/teacher_attendance",   "teacher_attendance",   teacher_attendance,   methods=["GET", "POST"])
app.add_url_rule("/teacher_reports",      "teacher_reports",      teacher_reports,      methods=["GET", "POST"])
app.add_url_rule("/teacher_calendar",     "teacher_calendar",     teacher_calendar,     methods=["GET", "POST"])

app.add_url_rule("/admin_dashboard",      "admin_dashboard",      admin_dashboard)
app.add_url_rule("/admin_broadcast",      "admin_broadcast",      admin_broadcast,      methods=["GET", "POST"])
app.add_url_rule("/admin_messages",       "admin_messages",       admin_messages)
app.add_url_rule("/admin_clear_inbox",    "admin_clear_inbox",    admin_clear_inbox,    methods=["POST"])
app.add_url_rule("/handle_message",       "handle_message",       handle_message,       methods=["POST"])
app.add_url_rule("/admin_grades",         "admin_grades",         admin_grades,         methods=["GET", "POST"])
app.add_url_rule("/delete_user",          "delete_user",          delete_user,          methods=["POST"])
app.add_url_rule("/admin_canteen",        "admin_canteen",        admin_canteen,        methods=["GET", "POST"])
app.add_url_rule("/admin_calendar",       "admin_calendar",       admin_calendar,       methods=["GET", "POST"])

app.add_url_rule("/principal_messages",   "principal_messages",   principal_messages,   methods=["GET", "POST"])

app.add_url_rule("/librarian_library",    "librarian_library",    librarian_library,    methods=["GET", "POST"])


@app.route("/")
def landing_page():
    feedbacks = db.execute("""
        SELECT f.*, u.profile_pic
        FROM feedback f
        LEFT JOIN users u ON (u.id = f.user_id) OR (u.username = f.name)
        ORDER BY f.created_at DESC
        LIMIT 6
    """)
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
                "INSERT INTO feedback (name, role, message, rating, user_id) VALUES (?, ?, ?, ?, ?)",
                session["username"], session["role"], message, int(rating), session["user_id"]
            )
            return redirect(url_for("feedback", submitted=1))
    feedbacks = db.execute("""
        SELECT f.*, u.profile_pic
        FROM feedback f
        LEFT JOIN users u ON (u.id = f.user_id) OR (u.username = f.name)
        ORDER BY f.created_at DESC
    """)
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
                "INSERT INTO news_seen (user_id, news_id) VALUES (?, ?) ON CONFLICT (user_id, news_id) DO NOTHING",
                session["user_id"], n["id"]
            )
    return render_template("school_news.html", news=news)


if __name__ == "__main__":
    app.run(debug=False)
