from flask import Blueprint, render_template, request, redirect, url_for, session
from app import db, login_required, role_required

student_bp = Blueprint("student", __name__)


def require_grade():
    return db.execute("SELECT 1 FROM grades WHERE user_id = ? LIMIT 1", session["user_id"])


@student_bp.route("/send_request", methods=["GET", "POST"])
@login_required
@role_required("student")
def send_request():
    if not require_grade():
        return redirect(url_for("auth.home", need_info=1))
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


@student_bp.route("/student_inbox")
@login_required
@role_required("student")
def student_inbox():
    if not require_grade():
        return redirect(url_for("auth.home", need_info=1))
    messages = db.execute("""
        SELECT m.message, m.created_at, u.username AS sender
        FROM messages m JOIN users u ON m.sender_id = u.id
        WHERE m.recipient_id = ? ORDER BY m.created_at DESC
    """, session["user_id"])
    db.execute("UPDATE messages SET is_read = 1 WHERE recipient_id = ?", session["user_id"])
    return render_template("student_inbox.html", messages=messages)


@student_bp.route("/clear_inbox", methods=["POST"])
@login_required
@role_required("student")
def clear_inbox():
    if not require_grade():
        return redirect(url_for("auth.home", need_info=1))
    db.execute("DELETE FROM messages WHERE recipient_id = ?", session["user_id"])
    return redirect(url_for("student.student_inbox"))


@student_bp.route("/student_circulars")
@login_required
@role_required("student")
def student_circulars():
    if not require_grade():
        return redirect(url_for("auth.home", need_info=1))
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


@student_bp.route("/student_homework")
@login_required
@role_required("student")
def student_homework():
    if not require_grade():
        return redirect(url_for("auth.home", need_info=1))
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