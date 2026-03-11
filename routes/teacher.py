from flask import render_template, request, redirect, url_for, session, abort


def _require_teacher():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "teacher":
        abort(403)
    return None


def teacher_messages():
    from app import db
    guard = _require_teacher()
    if guard:
        return guard
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


def teacher_student_inbox():
    from app import db
    guard = _require_teacher()
    if guard:
        return guard
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


def teacher_clear_inbox():
    from app import db
    guard = _require_teacher()
    if guard:
        return guard
    db.execute("DELETE FROM messages WHERE recipient_id = ?", session["user_id"])
    return redirect(url_for("teacher_messages"))


def teacher_circulars():
    from app import db, sanitise_grades, save_upload
    guard = _require_teacher()
    if guard:
        return guard
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


def teacher_homework():
    from app import db, sanitise_grades, save_upload
    guard = _require_teacher()
    if guard:
        return guard
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


def teacher_to_admin():
    guard = _require_teacher()
    if guard:
        return guard
    abort(403)


# ── NEW ROUTES ─────────────────────────────────────────────────────────────

def teacher_results():
    """Teacher posts exam results for individual students."""
    from app import db
    guard = _require_teacher()
    if guard:
        return guard

    students = db.execute("""
        SELECT u.id, u.username, g.grade, g.section
        FROM users u JOIN grades g ON u.id = g.user_id
        WHERE u.role = 'student' ORDER BY g.grade, u.username
    """)
    success = ""
    error   = ""

    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        exam_name  = request.form.get("exam_name", "").strip()
        subject    = request.form.get("subject", "").strip()
        marks      = request.form.get("marks", "").strip()
        out_of     = request.form.get("out_of", "100").strip()
        remarks    = request.form.get("remarks", "").strip()

        if not student_id or not exam_name or not subject or not marks:
            error = "Student, exam name, subject and marks are required."
        else:
            try:
                m = float(marks)
                o = float(out_of) if out_of else 100.0
                pct = (m / o) * 100
                if pct >= 90:   grade = "A+"
                elif pct >= 80: grade = "A"
                elif pct >= 70: grade = "B"
                elif pct >= 60: grade = "C"
                elif pct >= 50: grade = "D"
                else:           grade = "F"
                db.execute(
                    "INSERT INTO results (student_id, sender_id, exam_name, subject, marks, out_of, grade, remarks) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    int(student_id), session["user_id"], exam_name, subject, m, o, grade, remarks
                )
                success = f"Result saved! {subject}: {m}/{o} ({grade})"
            except ValueError:
                error = "Marks must be numbers."

    # Fetch all results this teacher has posted
    posted = db.execute("""
        SELECT r.*, u.username AS student_name
        FROM results r JOIN users u ON r.student_id = u.id
        WHERE r.sender_id = ? ORDER BY r.created_at DESC
    """, session["user_id"])

    return render_template("teacher_results.html",
                           students=students, posted=posted,
                           success=success, error=error)


def teacher_attendance():
    """Teacher marks daily attendance for students."""
    from app import db
    from datetime import date as dt
    guard = _require_teacher()
    if guard:
        return guard

    # Default to teacher's grade's students; show all if no grade filter
    grade_filter = request.args.get("grade", "")
    today = str(dt.today())
    success = ""
    error   = ""

    if request.method == "POST":
        att_date = request.form.get("att_date", today)
        for key, val in request.form.items():
            if key.startswith("status_"):
                sid = key.replace("status_", "")
                db.execute(
                    "INSERT INTO attendance (student_id, marked_by, date, status) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (student_id, date) DO UPDATE SET "
                    "marked_by = EXCLUDED.marked_by, status = EXCLUDED.status",
                    int(sid), session["user_id"], att_date, val
                )
            if key.startswith("roll_"):
                sid = key.replace("roll_", "")
                roll = val.strip()
                if roll:
                    db.execute(
                        "UPDATE grades SET roll_number = ? WHERE user_id = ?",
                        roll, int(sid)
                    )
        success = f"Attendance saved for {att_date}!"

    grades = db.execute("SELECT DISTINCT grade FROM grades ORDER BY grade")
    q = """
        SELECT u.id, u.username, g.grade, g.section, g.roll_number
        FROM users u JOIN grades g ON u.id = g.user_id
        WHERE u.role = 'student'
    """
    students = db.execute(q + " AND g.grade = ? ORDER BY u.username", grade_filter) if grade_filter \
        else db.execute(q + " ORDER BY g.grade, u.username")

    # Fetch today's attendance for these students
    existing = {}
    if students:
        att_date = request.form.get("att_date", today)
        for s in students:
            row = db.execute(
                "SELECT status FROM attendance WHERE student_id = ? AND date = ?",
                s["id"], att_date
            )
            existing[s["id"]] = row[0]["status"] if row else "present"

    return render_template("teacher_attendance.html",
                           students=students, grades=grades,
                           grade_filter=grade_filter,
                           today=today, existing=existing,
                           success=success, error=error)


def teacher_reports():
    """Teacher posts reports for individual students."""
    from app import db, save_upload
    guard = _require_teacher()
    if guard:
        return guard

    students = db.execute("""
        SELECT u.id, u.username, g.grade, g.section
        FROM users u JOIN grades g ON u.id = g.user_id
        WHERE u.role = 'student' ORDER BY g.grade, u.username
    """)
    success = ""
    error   = ""

    if request.method == "POST":
        student_id  = request.form.get("student_id", "").strip()
        report_type = request.form.get("report_type", "").strip()
        title       = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        attachment  = save_upload(request.files.get("attachment"))

        if not student_id or not report_type or not title:
            error = "Student, type and title are required."
        else:
            db.execute(
                "INSERT INTO student_reports (student_id, sender_id, report_type, title, description, attachment) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                int(student_id), session["user_id"], report_type, title, description, attachment
            )
            success = "Report saved!"

    posted = db.execute("""
        SELECT r.*, u.username AS student_name
        FROM student_reports r JOIN users u ON r.student_id = u.id
        WHERE r.sender_id = ? ORDER BY r.created_at DESC
    """, session["user_id"])

    return render_template("teacher_reports.html",
                           students=students, posted=posted,
                           success=success, error=error)


def teacher_calendar():
    """Teacher adds calendar events."""
    from app import db
    from datetime import date as dt
    guard = _require_teacher()
    if guard:
        return guard

    success = ""
    error   = ""
    if request.method == "POST":
        title       = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        event_date  = request.form.get("event_date", "").strip()
        if not title or not event_date:
            error = "Title and date are required."
        else:
            db.execute(
                "INSERT INTO calendar_events (created_by, title, description, event_date) VALUES (?, ?, ?, ?)",
                session["user_id"], title, description, event_date
            )
            success = "Event added!"

    events = db.execute(
        "SELECT ce.*, u.username AS creator FROM calendar_events ce "
        "JOIN users u ON ce.created_by = u.id "
        "WHERE ce.event_date >= ? ORDER BY ce.event_date",
        str(dt.today())
    )
    return render_template("teacher_calendar.html",
                           events=events, success=success, error=error)
