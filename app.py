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


def send_school_code_email(to_email, code, school_name):
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
        f"Share this code with teachers and students to register."
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


# ── Register blueprints ──────────────────────────────────────────────────────
from routes.auth     import auth_bp
from routes.student  import student_bp
from routes.teacher  import teacher_bp
from routes.admin    import admin_bp
from routes.principal import principal_bp

app.register_blueprint(auth_bp)
app.register_blueprint(student_bp)
app.register_blueprint(teacher_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(principal_bp)


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
        FROM news n JOIN users u ON n.sender_id = u.id
        ORDER BY n.created_at DESC
    """)
    if session.get("role") in ("student", "teacher") and news:
        for n in news:
            db.execute(
                "INSERT OR IGNORE INTO news_seen (user_id, news_id) VALUES (?, ?)",
                session["user_id"], n["id"]
            )
    return render_template("school_news.html", news=news)


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


if __name__ == "__main__":
    app.run(debug=False)