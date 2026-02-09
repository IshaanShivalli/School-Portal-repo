from flask import Flask, render_template, request, redirect, url_for, session, abort
from cs50 import SQL
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import os
import time

app = Flask(__name__)
app.secret_key = "the-password234!"
db = SQL("sqlite:///db.sqlite3")
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "doc", "docx", "txt"}

def init_db():
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

    # Add online-status columns to users if missing
    cols = db.execute("SELECT name FROM pragma_table_info('users')")
    col_names = {c["name"] for c in cols}
    if "is_logged_in" not in col_names:
        db.execute("ALTER TABLE users ADD COLUMN is_logged_in INTEGER DEFAULT 0")
    if "last_seen" not in col_names:
        db.execute("ALTER TABLE users ADD COLUMN last_seen INTEGER DEFAULT 0")

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
    path = os.path.join(UPLOAD_FOLDER, unique)
    file.save(path)
    return f"uploads/{unique}"

init_db()

@app.before_request
def track_last_seen():
    if "user_id" in session:
        db.execute(
            "UPDATE users SET is_logged_in = 1, last_seen = ? WHERE id = ?",
            int(time.time()),
            session["user_id"]
        )

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

@app.route("/ping")
@login_required
def ping():
    # Heartbeat to keep last_seen fresh
    db.execute(
        "UPDATE users SET is_logged_in = 1, last_seen = ? WHERE id = ?",
        int(time.time()),
        session["user_id"]
    )
    return ("", 204)

@app.route("/dev_reset", methods=["GET", "POST"])
def dev_reset():
    try:
        db.execute("DELETE FROM messages")
        db.execute("DELETE FROM grades")
        db.execute("DELETE FROM users")
        db.execute("DELETE FROM news")
        db.execute("DELETE FROM circulars")
        db.execute("DELETE FROM homework")
        db.execute("DELETE FROM news_seen")
        db.execute("DELETE FROM circulars_seen")
        db.execute("DELETE FROM homework_seen")
        session.clear()
        return "Database cleared!"
    except Exception as e:
        return f"Reset failed: {e}", 500

@app.route("/", methods=["GET", "POST"])
@login_required
def home():
    role = session.get("role")
    if role == "admin":
        return redirect(url_for("admin_dashboard"))
    elif role == "teacher":
        counts = {
            "inbox_unread": 0,
            "inbox_received": 0,
            "student_unread": 0,
            "student_received": 0,
            "sent_students": 0,
            "sent_admin": 0,
            "sent_circulars": 0,
            "sent_homework": 0,
            "news_unread": 0,
            "news_total": 0,
        }
        students = db.execute("""
            SELECT u.username, g.grade, g.section, g.dob
            FROM users u
            JOIN grades g ON u.id = g.user_id
            WHERE u.role = 'student'
            ORDER BY u.username
        """)
        counts["inbox_unread"] = db.execute("""
            SELECT COUNT(*) AS c
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.recipient_id = ? AND m.is_read = 0
              AND u.role IN ('admin', 'teacher')
        """, session["user_id"])[0]["c"]
        counts["inbox_received"] = db.execute("""
            SELECT COUNT(*) AS c
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.recipient_id = ?
              AND u.role IN ('admin', 'teacher')
        """, session["user_id"])[0]["c"]
        counts["student_unread"] = db.execute("""
            SELECT COUNT(*) AS c
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.recipient_id = ? AND m.is_read = 0
              AND u.role = 'student'
        """, session["user_id"])[0]["c"]
        counts["student_received"] = db.execute("""
            SELECT COUNT(*) AS c
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.recipient_id = ?
              AND u.role = 'student'
        """, session["user_id"])[0]["c"]
        counts["sent_students"] = db.execute("""
            SELECT COUNT(*) AS c
            FROM messages m
            JOIN users u ON m.recipient_id = u.id
            WHERE m.sender_id = ?
              AND u.role = 'student'
        """, session["user_id"])[0]["c"]
        counts["sent_admin"] = db.execute("""
            SELECT COUNT(*) AS c
            FROM messages m
            JOIN users u ON m.recipient_id = u.id
            WHERE m.sender_id = ?
              AND u.role = 'admin'
        """, session["user_id"])[0]["c"]
        counts["sent_circulars"] = db.execute(
            "SELECT COUNT(*) AS c FROM circulars WHERE sender_id = ?",
            session["user_id"]
        )[0]["c"]
        counts["sent_homework"] = db.execute(
            "SELECT COUNT(*) AS c FROM homework WHERE sender_id = ?",
            session["user_id"]
        )[0]["c"]
        counts["news_total"] = db.execute("SELECT COUNT(*) AS c FROM news")[0]["c"]
        counts["news_unread"] = db.execute("""
            SELECT COUNT(*) AS c
            FROM news n
            WHERE n.id NOT IN (
                SELECT news_id FROM news_seen WHERE user_id = ?
            )
        """, session["user_id"])[0]["c"]
        return render_template("teacher_home.html", students=students, counts=counts)
    else:
        entry = db.execute("SELECT * FROM grades WHERE user_id = ?", session["user_id"])
        info_submitted = bool(entry)
        message = ""
        error = ""
        counts = {
            "total": 0,
            "inbox_unread": 0,
            "inbox_total": 0,
            "sent_total": 0,
            "circulars_unread": 0,
            "circulars_total": 0,
            "news_unread": 0,
            "news_total": 0,
            "homework_unread": 0,
            "homework_total": 0,
        }
        if request.args.get("need_info"):
            error = "Please complete your information first."
        if request.method == "POST" and not info_submitted:
            name = session.get("username", "").strip()
            grade = request.form.get("grade", "").strip()
            section = request.form.get("section", "").strip().upper()
            dob = request.form.get("dob", "").strip()
            if name and grade and section and dob and len(section) == 1 and section in "ABCDEFG":
                db.execute(
                    "INSERT INTO grades (user_id, name, grade, section, dob) VALUES (?, ?, ?, ?, ?)",
                    session["user_id"], name, grade or None, section or None, dob or None
                )
                info_submitted = True
                message = "Info submitted!"
            else:
                error = "All fields are required. Section must be a single letter A-G."
        student_info = entry[0] if entry else None
        if student_info:
            counts["inbox_unread"] = db.execute(
                "SELECT COUNT(*) AS c FROM messages WHERE recipient_id = ? AND is_read = 0",
                session["user_id"]
            )[0]["c"]
            counts["inbox_total"] = db.execute(
                "SELECT COUNT(*) AS c FROM messages WHERE recipient_id = ?",
                session["user_id"]
            )[0]["c"]
            counts["sent_total"] = db.execute(
                "SELECT COUNT(*) AS c FROM messages WHERE sender_id = ?",
                session["user_id"]
            )[0]["c"]
            counts["circulars_unread"] = db.execute("""
                SELECT COUNT(*) AS c
                FROM circulars c
                WHERE c.grade = ?
                  AND c.id NOT IN (
                      SELECT circular_id FROM circulars_seen WHERE user_id = ?
                  )
            """, student_info["grade"], session["user_id"])[0]["c"]
            counts["circulars_total"] = db.execute(
                "SELECT COUNT(*) AS c FROM circulars WHERE grade = ?",
                student_info["grade"]
            )[0]["c"]
            counts["homework_unread"] = db.execute("""
                SELECT COUNT(*) AS c
                FROM homework h
                WHERE h.grade = ?
                  AND h.id NOT IN (
                      SELECT homework_id FROM homework_seen WHERE user_id = ?
                  )
            """, student_info["grade"], session["user_id"])[0]["c"]
            counts["homework_total"] = db.execute(
                "SELECT COUNT(*) AS c FROM homework WHERE grade = ?",
                student_info["grade"]
            )[0]["c"]
            counts["news_unread"] = db.execute("""
                SELECT COUNT(*) AS c
                FROM news n
                WHERE n.id NOT IN (
                    SELECT news_id FROM news_seen WHERE user_id = ?
                )
            """, session["user_id"])[0]["c"]
            counts["news_total"] = db.execute("SELECT COUNT(*) AS c FROM news")[0]["c"]
            counts["total"] = (
                counts["inbox_unread"]
                + counts["circulars_unread"]
                + counts["homework_unread"]
                + counts["news_unread"]
            )
        return render_template(
            "student_dashboard.html",
            info_submitted=info_submitted,
            message=message,
            error=error,
            name_prefill=session.get("username", ""),
            student_info=student_info,
            counts=counts
        )

@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("home"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        role = request.form.get("role", "student")
        if not username or not password or password != confirm:
            return render_template("register.html", error="Invalid input")
        if db.execute("SELECT * FROM users WHERE username = ?", username):
            return render_template("register.html", error="Username exists")
        hashed = generate_password_hash(password)
        is_admin = 1 if role == "admin" else 0
        db.execute(
            "INSERT INTO users (username, password, is_admin, role) VALUES (?, ?, ?, ?)",
            username, hashed, is_admin, role
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
            return render_template("login.html", error="Missing credentials")
        user = db.execute("SELECT * FROM users WHERE username = ?", username)
        if len(user) != 1 or not check_password_hash(user[0]["password"], password):
            return render_template("login.html", error="Invalid credentials")
        session["user_id"] = user[0]["id"]
        session["username"] = user[0]["username"]
        session["is_admin"] = user[0]["is_admin"]
        session["role"] = user[0]["role"]
        db.execute(
            "UPDATE users SET is_logged_in = 1, last_seen = ? WHERE id = ?",
            int(time.time()),
            user[0]["id"]
        )
        return redirect(url_for("home"))
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    if "user_id" in session:
        db.execute(
            "UPDATE users SET is_logged_in = 0, last_seen = ? WHERE id = ?",
            int(time.time()),
            session["user_id"]
        )
    session.clear()
    return redirect(url_for("login"))

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    error = ""
    success = ""
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
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
                hashed = generate_password_hash(new)
                db.execute("UPDATE users SET password = ? WHERE id = ?", hashed, session["user_id"])
                success = "Password updated."
    return render_template("settings.html", error=error, success=success)

@app.route("/send_request", methods=["GET", "POST"])
@login_required
@role_required("student")
def send_request():
    if not db.execute("SELECT 1 FROM grades WHERE user_id = ? LIMIT 1", session["user_id"]):
        return redirect(url_for("home", need_info=1))
    if request.method == "POST":
        message = request.form.get("message", "").strip()
        if not message:
            return render_template("send_request.html", error="Message empty")

        teachers = db.execute(
            "SELECT id FROM users WHERE role = 'teacher'"
        )

        if not teachers:
            return render_template("send_request.html", error="No teacher available")

        for t in teachers:
            db.execute(
                "INSERT INTO messages (sender_id, recipient_id, message) VALUES (?, ?, ?)",
                session["user_id"],
                t["id"],
                message
            )

        return render_template("send_request.html", success="Message sent!")

    return render_template("send_request.html")

@app.route("/admin_broadcast", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_broadcast():
    grades = db.execute("SELECT DISTINCT grade FROM grades ORDER BY grade")
    teachers = db.execute("SELECT id, username FROM users WHERE role = 'teacher' ORDER BY username")
    news = db.execute("""
        SELECT n.id, n.title, n.body, n.attachment, n.created_at, u.username AS sender
        FROM news n
        JOIN users u ON n.sender_id = u.id
        ORDER BY n.created_at DESC
    """)

    students = db.execute("""
        SELECT u.username, g.grade
        FROM users u
        JOIN grades g ON u.id = g.user_id
        WHERE u.role='student'
    """)

    success = ""
    error = ""

    if request.method == "POST":
        target = request.form.get("target")
        selected_grades = request.form.getlist("grades")
        message = request.form.get("message", "").strip()

        if target == "news":
            title = request.form.get("title", "").strip()
            body = request.form.get("body", "").strip()
            attachment = save_upload(request.files.get("attachment"))
            if not title or not body:
                error = "Title and body are required"
            else:
                db.execute(
                    "INSERT INTO news (sender_id, title, body, attachment) VALUES (?, ?, ?, ?)",
                    session["user_id"], title, body, attachment
                )
                success = "News posted!"
        elif target == "admin_circular":
            selected_grades = request.form.getlist("grades")
            title = request.form.get("title", "").strip()
            body = request.form.get("body", "").strip()
            attachment = save_upload(request.files.get("attachment"))
            if not selected_grades:
                error = "Select at least one grade"
            elif not title or not body:
                error = "Title and body are required"
            else:
                for g in selected_grades:
                    db.execute(
                        "INSERT INTO circulars (sender_id, grade, title, body, attachment) VALUES (?, ?, ?, ?, ?)",
                        session["user_id"], g, title, body, attachment
                    )
                success = "Circular sent!"
        elif not message:
            error = "Message empty"
        elif target == "teachers":
            selected_teachers = request.form.getlist("teachers")
            send_to_all_teachers = ("ALL" in selected_teachers) or (not selected_teachers)

            if send_to_all_teachers:
                recipients = db.execute("""
                    SELECT u.id FROM users u
                    WHERE u.role = 'teacher'
                """)
            else:
                placeholders = ", ".join(["?"] * len(selected_teachers))
                recipients = db.execute(f"""
                    SELECT u.id FROM users u
                    WHERE u.role = 'teacher' AND u.id IN ({placeholders})
                """, *selected_teachers)

            for r in recipients:
                db.execute(
                    "INSERT INTO messages (sender_id, recipient_id, message) VALUES (?, ?, ?)",
                    session["user_id"], r["id"], message
                )
            success = "Message sent to teachers!"
        else:
            send_to_all = ("ALL" in selected_grades) or (not selected_grades)

            if send_to_all:
                recipients = db.execute("""
                    SELECT u.id FROM users u
                    WHERE u.role = 'student'
                """)
            else:
                placeholders = ", ".join(["?"] * len(selected_grades))
                recipients = db.execute(f"""
                    SELECT DISTINCT u.id FROM users u
                    JOIN grades g ON u.id = g.user_id
                    WHERE g.grade IN ({placeholders})
                """, *selected_grades)

            for r in recipients:
                db.execute(
                    "INSERT INTO messages (sender_id, recipient_id, message) VALUES (?, ?, ?)",
                    session["user_id"], r["id"], message
                )
            success = "Message sent to students!"

    return render_template(
        "admin_broadcast.html",
        grades=grades,
        students=students,
        teachers=teachers,
        news=news,
        success=success,
        error=error,
    )

@app.route("/student_inbox")
@login_required
@role_required("student")
def student_inbox():
    if not db.execute("SELECT 1 FROM grades WHERE user_id = ? LIMIT 1", session["user_id"]):
        return redirect(url_for("home", need_info=1))
    messages = db.execute("""
        SELECT m.message, m.created_at, u.username AS sender
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE m.recipient_id = ?
        ORDER BY m.created_at DESC
    """, session["user_id"])

    db.execute(
        "UPDATE messages SET is_read = 1 WHERE recipient_id = ?",
        session["user_id"]
    )

    return render_template("student_inbox.html", messages=messages)

@app.route("/teacher_messages", methods=["GET", "POST"])
@login_required
@role_required("teacher")
def teacher_messages():
    students = db.execute("""
        SELECT u.id, u.username, g.grade
        FROM users u
        JOIN grades g ON u.id = g.user_id
        WHERE u.role = 'student'
        ORDER BY u.username
    """)

    if request.method == "POST":
        student_id = request.form.get("student_id")
        message = request.form.get("message")

        if student_id and message:
            db.execute(
                "INSERT INTO messages (sender_id, recipient_id, message) VALUES (?, ?, ?)",
                session["user_id"], student_id, message
            )

    messages = db.execute("""
        SELECT DISTINCT m.id, m.message, m.created_at, u.username AS sender
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE m.recipient_id = ?
          AND u.role IN ('admin', 'teacher')
        ORDER BY m.created_at DESC
    """, session["user_id"])

    db.execute("""
        UPDATE messages
        SET is_read = 1
        WHERE recipient_id = ?
          AND sender_id IN (SELECT id FROM users WHERE role IN ('admin', 'teacher'))
    """, session["user_id"])

    return render_template("teacher_messages.html", students=students, messages=messages)

@app.route("/teacher_student_inbox")
@login_required
@role_required("teacher")
def teacher_student_inbox():
    messages = db.execute("""
        SELECT m.id, m.message, m.created_at, u.username AS sender
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE m.recipient_id = ?
          AND u.role = 'student'
        ORDER BY m.created_at DESC
    """, session["user_id"])
    db.execute("""
        UPDATE messages
        SET is_read = 1
        WHERE recipient_id = ?
          AND sender_id IN (SELECT id FROM users WHERE role = 'student')
    """, session["user_id"])
    return render_template("teacher_student_inbox.html", messages=messages)

@app.route("/school_news")
@login_required
def school_news():
    news = db.execute("""
        SELECT n.id, n.title, n.body, n.attachment, n.created_at, u.username AS sender
        FROM news n
        JOIN users u ON n.sender_id = u.id
        ORDER BY n.created_at DESC
    """)
    if session.get("role") in ("student", "teacher") and news:
        for n in news:
            db.execute(
                "INSERT OR IGNORE INTO news_seen (user_id, news_id) VALUES (?, ?)",
                session["user_id"], n["id"]
            )
    return render_template("school_news.html", news=news)

@app.route("/teacher_circulars", methods=["GET", "POST"])
@login_required
@role_required("teacher")
def teacher_circulars():
    grades = db.execute("SELECT DISTINCT grade FROM grades ORDER BY grade")
    success = ""
    error = ""
    if request.method == "POST":
        selected_grades = request.form.getlist("grades")
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        attachment = save_upload(request.files.get("attachment"))
        if not selected_grades:
            error = "Select at least one grade"
        elif not title or not body:
            error = "Title and body are required"
        else:
            for g in selected_grades:
                db.execute(
                    "INSERT INTO circulars (sender_id, grade, title, body, attachment) VALUES (?, ?, ?, ?, ?)",
                    session["user_id"], g, title, body, attachment
                )
            success = "Circular sent!"
    circulars = db.execute("""
        SELECT id, grade, title, body, attachment, created_at
        FROM circulars
        WHERE sender_id = ?
        ORDER BY created_at DESC
    """, session["user_id"])
    return render_template("teacher_circulars.html", grades=grades, circulars=circulars, success=success, error=error)

@app.route("/teacher_homework", methods=["GET", "POST"])
@login_required
@role_required("teacher")
def teacher_homework():
    grades = db.execute("SELECT DISTINCT grade FROM grades ORDER BY grade")
    success = ""
    error = ""
    if request.method == "POST":
        selected_grades = request.form.getlist("grades")
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        attachment = save_upload(request.files.get("attachment"))
        if not selected_grades:
            error = "Select at least one grade"
        elif not title or not body:
            error = "Title and body are required"
        else:
            for g in selected_grades:
                db.execute(
                    "INSERT INTO homework (sender_id, grade, title, body, attachment) VALUES (?, ?, ?, ?, ?)",
                    session["user_id"], g, title, body, attachment
                )
            success = "Homework sent!"
    homework = db.execute("""
        SELECT id, grade, title, body, attachment, created_at
        FROM homework
        WHERE sender_id = ?
        ORDER BY created_at DESC
    """, session["user_id"])
    return render_template("teacher_homework.html", grades=grades, homework=homework, success=success, error=error)

@app.route("/student_circulars")
@login_required
@role_required("student")
def student_circulars():
    if not db.execute("SELECT 1 FROM grades WHERE user_id = ? LIMIT 1", session["user_id"]):
        return redirect(url_for("home", need_info=1))
    grade = db.execute("SELECT grade FROM grades WHERE user_id = ? LIMIT 1", session["user_id"])[0]["grade"]
    circulars = db.execute("""
        SELECT c.id, c.title, c.body, c.attachment, c.created_at, u.username AS sender
        FROM circulars c
        JOIN users u ON c.sender_id = u.id
        WHERE c.grade = ?
        ORDER BY c.created_at DESC
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
    if not db.execute("SELECT 1 FROM grades WHERE user_id = ? LIMIT 1", session["user_id"]):
        return redirect(url_for("home", need_info=1))
    grade = db.execute("SELECT grade FROM grades WHERE user_id = ? LIMIT 1", session["user_id"])[0]["grade"]
    homework = db.execute("""
        SELECT h.id, h.title, h.body, h.attachment, h.created_at, u.username AS sender
        FROM homework h
        JOIN users u ON h.sender_id = u.id
        WHERE h.grade = ?
        ORDER BY h.created_at DESC
    """, grade)
    for h in homework:
        db.execute(
            "INSERT OR IGNORE INTO homework_seen (user_id, homework_id) VALUES (?, ?)",
            session["user_id"], h["id"]
        )
    return render_template("student_homework.html", homework=homework, grade=grade)

@app.route("/teacher_to_admin", methods=["GET", "POST"])
@login_required
@role_required("teacher")
def teacher_to_admin():
    admin = db.execute("SELECT id FROM users WHERE role='admin' LIMIT 1")
    if not admin:
        return render_template("teacher_to_admin.html", error="No admin available.")

    admin_id = admin[0]["id"]
    success = ""
    if request.method == "POST":
        message = request.form.get("message")
        if message:
            db.execute(
                "INSERT INTO messages (sender_id, recipient_id, message) VALUES (?, ?, ?)",
                session["user_id"], admin_id, message
            )
            success = "Message sent to admin."

    return render_template("teacher_to_admin.html", success=success)

@app.route("/admin_dashboard")
@login_required
@role_required("admin")
def admin_dashboard():
    now_ts = int(time.time())
    idle_seconds = 30

    students = db.execute("""
        SELECT u.id, u.username, g.grade, u.role, u.is_logged_in, u.last_seen
        FROM users u
        LEFT JOIN grades g ON u.id = g.user_id
        WHERE u.role = 'student'
    """)
    teachers = db.execute("""
        SELECT u.id, u.username, u.role, u.is_logged_in, u.last_seen
        FROM users u
        WHERE u.role = 'teacher'
        ORDER BY u.username
    """)

    def status_for(user):
        last_seen = int(user["last_seen"] or 0)
        if last_seen > 0 and (now_ts - last_seen) <= idle_seconds:
            return "online"
        if user["is_logged_in"] == 1:
            return "idle"
        return "offline"

    for u in students:
        u["status"] = status_for(u)
    for t in teachers:
        t["status"] = status_for(t)

    admin_counts = {
        "inbox_unread": 0,
        "inbox_received": 0,
        "sent_students": 0,
        "sent_teachers": 0,
        "sent_news": 0,
        "sent_circulars": 0,
    }
    admin_counts["inbox_unread"] = db.execute(
        "SELECT COUNT(*) AS c FROM messages WHERE recipient_id = ? AND is_read = 0",
        session["user_id"]
    )[0]["c"]
    admin_counts["inbox_received"] = db.execute(
        "SELECT COUNT(*) AS c FROM messages WHERE recipient_id = ?",
        session["user_id"]
    )[0]["c"]
    admin_counts["sent_students"] = db.execute("""
        SELECT COUNT(*) AS c
        FROM messages m
        JOIN users u ON m.recipient_id = u.id
        WHERE m.sender_id = ? AND u.role = 'student'
    """, session["user_id"])[0]["c"]
    admin_counts["sent_teachers"] = db.execute("""
        SELECT COUNT(*) AS c
        FROM messages m
        JOIN users u ON m.recipient_id = u.id
        WHERE m.sender_id = ? AND u.role = 'teacher'
    """, session["user_id"])[0]["c"]
    admin_counts["sent_news"] = db.execute(
        "SELECT COUNT(*) AS c FROM news WHERE sender_id = ?",
        session["user_id"]
    )[0]["c"]
    admin_counts["sent_circulars"] = db.execute(
        "SELECT COUNT(*) AS c FROM circulars WHERE sender_id = ?",
        session["user_id"]
    )[0]["c"]

    return render_template(
        "admin_dashboard.html",
        users=students,
        teachers=teachers,
        counts=admin_counts
    )

@app.route("/admin_messages")
@login_required
@role_required("admin")
def admin_messages():
    messages = db.execute("""
        SELECT m.id, m.message, m.created_at, u.username AS sender
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE m.recipient_id = ?
        ORDER BY m.created_at DESC
    """, session["user_id"])

    db.execute(
        "UPDATE messages SET is_read = 1 WHERE recipient_id = ?",
        session["user_id"]
    )
    return render_template("admin_messages.html", messages=messages)

@app.route("/handle_message", methods=["POST"])
@login_required
@role_required("admin")
def handle_message():
    msg_id = request.form.get("msg_id")
    if msg_id:
        db.execute("UPDATE messages SET is_handled = 1 WHERE id = ?", msg_id)
    return redirect(url_for("admin_messages"))

@app.route("/clear_inbox", methods=["POST"])
@login_required
@role_required("student")
def clear_inbox():
    if not db.execute("SELECT 1 FROM grades WHERE user_id = ? LIMIT 1", session["user_id"]):
        return redirect(url_for("home", need_info=1))
    db.execute("DELETE FROM messages WHERE recipient_id = ?", session["user_id"])
    return redirect(url_for("student_inbox"))

@app.route("/teacher_clear_inbox", methods=["POST"])
@login_required
@role_required("teacher")
def teacher_clear_inbox():
    db.execute("DELETE FROM messages WHERE recipient_id = ?", session["user_id"])
    return redirect(url_for("teacher_messages"))

@app.route("/admin_clear_inbox", methods=["POST"])
@login_required
@role_required("admin")
def admin_clear_inbox():
    db.execute("DELETE FROM messages WHERE recipient_id = ?", session["user_id"])
    return redirect(url_for("admin_messages"))

@app.route("/view_students")
@login_required
@role_required("admin")
def view_students():
    students = db.execute("""
        SELECT u.username, g.grade, u.id
        FROM users u
        JOIN grades g ON u.id = g.user_id
        WHERE u.role = 'student'
    """)
    return render_template("student_dashboard.html", students=students)

@app.route("/admin_grades", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_grades():
    grades = db.execute("SELECT DISTINCT grade FROM grades ORDER BY grade")
    students = []

    if request.method == "POST":
        selected_grade = request.form.get("grade")
        students = db.execute("""
            SELECT u.username, g.grade, u.id
            FROM users u
            JOIN grades g ON u.id = g.user_id
            WHERE g.grade = ?
            ORDER BY u.username
        """, selected_grade)
    else:
        students = db.execute("""
            SELECT u.username, g.grade, u.id
            FROM users u
            JOIN grades g ON u.id = g.user_id
            WHERE u.role = 'student'
            ORDER BY u.username
        """)
    return render_template("admin_grades.html", grades=grades, students=students)

@app.route("/delete_user", methods=["POST"])
@login_required
@role_required("admin")
def delete_user():
    username = request.form.get("username")
    if not username:
        return redirect(url_for("admin_dashboard"))

    user = db.execute("SELECT id FROM users WHERE username = ?", username)
    if not user:
        return redirect(url_for("admin_dashboard"))

    user_id = user[0]["id"]

    is_admin_user = db.execute("SELECT is_admin FROM users WHERE id = ?", user_id)
    if is_admin_user and is_admin_user[0]["is_admin"] == 1:
        return redirect(url_for("admin_dashboard"))

    db.execute("DELETE FROM messages WHERE sender_id = ? OR recipient_id = ?", user_id, user_id)
    db.execute("DELETE FROM grades WHERE user_id = ?", user_id)
    db.execute("DELETE FROM users WHERE id = ?", user_id)

    return redirect(url_for("admin_dashboard"))

if __name__ == "__main__":
    app.run(debug=True, port=5001)
