from flask import render_template, request, redirect, url_for, session
from datetime import date


def _require_student():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "student":
        from flask import abort
        abort(403)
    return None


def _require_grade():
    from app import db
    return db.execute("SELECT 1 FROM grades WHERE user_id = ? LIMIT 1", session["user_id"])


def _get_grade():
    from app import db
    rows = db.execute("SELECT grade FROM grades WHERE user_id = ? LIMIT 1", session["user_id"])
    return rows[0]["grade"] if rows else None


# ── existing routes ────────────────────────────────────────────────────────

def send_request():
    from app import db
    guard = _require_student()
    if guard:
        return guard
    if not _require_grade():
        return redirect(url_for("home", need_info=1))
    if request.method == "POST":
        message = request.form.get("message", "").strip()
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


def student_inbox():
    from app import db
    guard = _require_student()
    if guard:
        return guard
    if not _require_grade():
        return redirect(url_for("home", need_info=1))
    messages = db.execute("""
        SELECT m.message, m.created_at, u.username AS sender
        FROM messages m JOIN users u ON m.sender_id = u.id
        WHERE m.recipient_id = ? ORDER BY m.created_at DESC
    """, session["user_id"])
    db.execute("UPDATE messages SET is_read = 1 WHERE recipient_id = ?", session["user_id"])
    return render_template("student_inbox.html", messages=messages)


def clear_inbox():
    from app import db
    guard = _require_student()
    if guard:
        return guard
    if not _require_grade():
        return redirect(url_for("home", need_info=1))
    db.execute("DELETE FROM messages WHERE recipient_id = ?", session["user_id"])
    return redirect(url_for("student_inbox"))


def student_circulars():
    from app import db
    guard = _require_student()
    if guard:
        return guard
    if not _require_grade():
        return redirect(url_for("home", need_info=1))
    grade = _get_grade()
    circulars = db.execute("""
        SELECT c.id, c.title, c.body, c.attachment, c.created_at, u.username AS sender
        FROM circulars c JOIN users u ON c.sender_id = u.id
        WHERE c.grade = ? ORDER BY c.created_at DESC
    """, grade)
    for c in circulars:
        db.execute(
            "INSERT INTO circulars_seen (user_id, circular_id) VALUES (?, ?) "
            "ON CONFLICT (user_id, circular_id) DO NOTHING",
            session["user_id"], c["id"]
        )
    return render_template("student_circulars.html", circulars=circulars, grade=grade)


def student_homework():
    from app import db
    guard = _require_student()
    if guard:
        return guard
    if not _require_grade():
        return redirect(url_for("home", need_info=1))
    grade = _get_grade()
    homework = db.execute("""
        SELECT h.id, h.title, h.body, h.attachment, h.created_at, u.username AS sender
        FROM homework h JOIN users u ON h.sender_id = u.id
        WHERE h.grade = ? ORDER BY h.created_at DESC
    """, grade)
    for h in homework:
        db.execute(
            "INSERT INTO homework_seen (user_id, homework_id) VALUES (?, ?) "
            "ON CONFLICT (user_id, homework_id) DO NOTHING",
            session["user_id"], h["id"]
        )
    return render_template("student_homework.html", homework=homework, grade=grade)


# ── NEW ROUTES ─────────────────────────────────────────────────────────────

def student_results():
    from app import db
    guard = _require_student()
    if guard:
        return guard
    if not _require_grade():
        return redirect(url_for("home", need_info=1))
    results = db.execute("""
        SELECT r.exam_name, r.subject, r.marks, r.out_of, r.grade, r.remarks, r.created_at,
               u.username AS sender
        FROM results r JOIN users u ON r.sender_id = u.id
        WHERE r.student_id = ? ORDER BY r.exam_name, r.subject
    """, session["user_id"])
    return render_template("student_results.html", results=results)


def student_attendance():
    from app import db
    guard = _require_student()
    if guard:
        return guard
    if not _require_grade():
        return redirect(url_for("home", need_info=1))
    records = db.execute("""
        SELECT a.date, a.status, u.username AS marked_by
        FROM attendance a JOIN users u ON a.marked_by = u.id
        WHERE a.student_id = ? ORDER BY a.date DESC
    """, session["user_id"])
    total   = len(records)
    present = sum(1 for r in records if r["status"] == "present")
    absent  = sum(1 for r in records if r["status"] == "absent")
    late    = sum(1 for r in records if r["status"] == "late")
    pct     = round((present / total * 100), 1) if total else 0
    summary = {"present": present, "absent": absent, "late": late, "percent": pct}
    return render_template("student_attendance.html", attendance_records=records,
                           attendance_summary=summary)


def student_library():
    from app import db
    guard = _require_student()
    if guard:
        return guard
    if not _require_grade():
        return redirect(url_for("home", need_info=1))
    records = db.execute("""
        SELECT l.book_title, l.author, l.issued_date, l.due_date, l.returned_date,
               u.username AS librarian
        FROM library_records l JOIN users u ON l.librarian_id = u.id
        WHERE l.student_id = ? ORDER BY l.issued_date DESC
    """, session["user_id"])
    return render_template("student_library.html", library_records=records)


def student_canteen():
    from app import db
    guard = _require_student()
    if guard:
        return guard
    menu = db.execute(
        "SELECT * FROM canteen_menu ORDER BY CASE day_of_week "
        "WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3 "
        "WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6 "
        "ELSE 7 END, item_name"
    )
    return render_template("student_canteen.html", canteen_menu=menu)


def student_calendar():
    from app import db
    guard = _require_student()
    if guard:
        return guard
    events = db.execute(
        "SELECT title, description, event_date FROM calendar_events "
        "WHERE event_date >= ? ORDER BY event_date",
        str(date.today())
    )
    return render_template("student_calendar.html", calendar_events=events)


def student_send_email():
    from app import db, send_generic_email
    guard = _require_student()
    if guard:
        return guard
    if request.method == "POST":
        to_email = request.form.get("to_email", "").strip()
        subject  = request.form.get("subject", "").strip()
        body     = request.form.get("body", "").strip()
        if not to_email or not subject or not body:
            return redirect(url_for("home"))
        ok, err = send_generic_email(
            to_email, subject,
            f"Message from {session['username']} (Student) via SchoolBridge:\n\n{body}"
        )
    return redirect(url_for("home"))


def student_reports():
    from app import db
    guard = _require_student()
    if guard:
        return guard
    if not _require_grade():
        return redirect(url_for("home", need_info=1))
    reports = db.execute("""
        SELECT r.report_type, r.title, r.description, r.attachment, r.created_at,
               u.username AS sender
        FROM student_reports r JOIN users u ON r.sender_id = u.id
        WHERE r.student_id = ? ORDER BY r.created_at DESC
    """, session["user_id"])
    return render_template("student_reports.html", reports=reports)
