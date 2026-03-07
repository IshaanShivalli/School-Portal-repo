from flask import Blueprint, render_template, request, redirect, url_for, session, abort
from app import db, login_required, role_required, sanitise_grades, save_upload

teacher_bp = Blueprint("teacher", __name__)


@teacher_bp.route("/teacher_messages", methods=["GET", "POST"])
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
            return redirect(url_for("teacher.teacher_messages"))
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


@teacher_bp.route("/teacher_student_inbox")
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


@teacher_bp.route("/teacher_clear_inbox", methods=["POST"])
@login_required
@role_required("teacher")
def teacher_clear_inbox():
    db.execute("DELETE FROM messages WHERE recipient_id = ?", session["user_id"])
    return redirect(url_for("teacher.teacher_messages"))


@teacher_bp.route("/teacher_circulars", methods=["GET", "POST"])
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


@teacher_bp.route("/teacher_homework", methods=["GET", "POST"])
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


@teacher_bp.route("/teacher_to_admin", methods=["GET", "POST"])
@login_required
@role_required("teacher")
def teacher_to_admin():
    abort(403)