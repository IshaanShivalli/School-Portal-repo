from flask import render_template, request, redirect, url_for, session
import time


def admin_dashboard():
    from app import db, status_for

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


def admin_broadcast():
    from app import db, sanitise_grades, save_upload

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


def admin_messages():
    from app import db

    messages = db.execute("""
        SELECT m.id, m.message, m.created_at, u.username AS sender
        FROM messages m JOIN users u ON m.sender_id = u.id
        WHERE m.recipient_id = ? ORDER BY m.created_at DESC
    """, session["user_id"])
    db.execute("UPDATE messages SET is_read = 1 WHERE recipient_id = ?", session["user_id"])
    return render_template("admin_messages.html", messages=messages)


def admin_clear_inbox():
    from app import db

    db.execute("DELETE FROM messages WHERE recipient_id = ?", session["user_id"])
    return redirect(url_for("admin_messages"))


def handle_message():
    from app import db

    msg_id = request.form.get("msg_id")
    if msg_id:
        db.execute("UPDATE messages SET is_handled = 1 WHERE id = ?", msg_id)
    return redirect(url_for("admin_messages"))


def admin_grades():
    from app import db, VALID_GRADES

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


def delete_user():
    from app import db

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