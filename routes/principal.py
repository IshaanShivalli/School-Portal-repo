from flask import render_template, request, redirect, url_for, session, abort


def principal_messages():
    from app import db
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "principal":
        abort(403)

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
