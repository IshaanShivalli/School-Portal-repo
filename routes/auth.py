from flask import render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import os, time


def register():
    from app import db, generate_school_code, send_school_code_email

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
        school_name = f"{username}'s School"

        if role not in {"student", "teacher", "admin", "principal"}:
            return render_template("register.html", error="Please select a valid role.")

        if not username or not password or password != confirm:
            return render_template("register.html", error="Invalid input or passwords don't match.")

        if db.execute("SELECT id FROM users WHERE username = %s", username):
            return render_template("register.html", error="Username already taken.")

        school_id    = None
        is_librarian = 0

        if role in {"teacher", "student"}:
            if not school_code:
                return render_template("register.html", error="School code is required.")
            school = db.execute("SELECT id FROM schools WHERE code = %s", school_code)
            if not school:
                return render_template("register.html", error="Invalid school code.")
            school_id = school[0]["id"]

        if role == "teacher":
            teacher_passwords = [
                p.strip() for p in os.environ.get("TEACHER_PASSWORDS", "").split(",") if p.strip()
            ]
            librarian_passwords = [
                p.strip() for p in os.environ.get("LIBRARIAN_PASSWORDS", "").split(",") if p.strip()
            ]
            all_teacher_passwords = teacher_passwords + librarian_passwords
            if not all_teacher_passwords:
                return render_template("register.html", error="Teacher passwords are not configured.")
            if password not in all_teacher_passwords:
                return render_template("register.html", error="Invalid teacher password.")
            if not department or not phone:
                return render_template("register.html", error="Department and phone are required for teachers.")
            is_librarian = 1 if password in librarian_passwords else 0

        code = None
        if role == "principal":
            if not email:
                return render_template("register.html", error="Email is required for principals.")
            code = generate_school_code()
            while db.execute("SELECT 1 FROM schools WHERE code = %s", code):
                code = generate_school_code()

        hashed = generate_password_hash(password)
        db.execute(
            "INSERT INTO users (username, password, is_admin, role, department, phone, email, is_librarian) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            username, hashed,
            1 if role == "admin" else 0,
            role,
            department if role == "teacher" else None,
            phone if role == "teacher" else None,
            email if role in ("principal", "student") else None,
            is_librarian if role == "teacher" else 0
        )
        new_user = db.execute("SELECT id FROM users WHERE username = %s", username)[0]

        if school_id:
            db.execute("UPDATE users SET school_id = %s WHERE id = %s", school_id, new_user["id"])

        if role == "principal":
            db.execute(
                "INSERT INTO schools (principal_id, name, email, code) VALUES (%s, %s, %s, %s)",
                new_user["id"], school_name, email, code
            )
            ok, err = send_school_code_email(email, code, school_name)
            if ok:
                return render_template("register.html", success="Principal registered. School code sent to your email.")
            return render_template(
                "register.html",
                success=f"Principal registered. School code: {code}",
                error="Email failed - save your code now!"
            )

        return redirect(url_for("login"))

    return render_template("register.html")


def login():
    from app import db

    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            return render_template("login.html", error="Missing credentials.")

        rows = db.execute("SELECT * FROM users WHERE username = %s", username)
        if len(rows) != 1 or not check_password_hash(rows[0]["password"], password):
            return render_template("login.html", error="Invalid username or password.")

        user = rows[0]
        session["user_id"]  = user["id"]
        session["username"] = user["username"]
        session["is_admin"] = bool(user["is_admin"])
        session["role"]     = user["role"]

        db.execute(
            "UPDATE users SET is_logged_in = 1, last_seen = %s WHERE id = %s",
            int(time.time()), user["id"]
        )
        return redirect(url_for("home"))

    return render_template("login.html")


def logout():
    from app import db

    if "user_id" in session:
        db.execute(
            "UPDATE users SET is_logged_in = 0, last_seen = %s WHERE id = %s",
            int(time.time()), session["user_id"]
        )
    session.clear()
    return redirect(url_for("login"))


def settings():
    from app import db, save_profile_upload

    if "user_id" not in session:
        return redirect(url_for("login"))

    error   = ""
    success = ""
    if request.method == "POST":
        action = request.form.get("action")
        if action == "password":
            current = request.form.get("current_password", "")
            new     = request.form.get("new_password", "")
            confirm = request.form.get("confirm_password", "")
            if not current or not new or not confirm:
                error = "All fields are required."
            elif new != confirm:
                error = "New passwords do not match."
            else:
                user = db.execute("SELECT password FROM users WHERE id = %s", session["user_id"])
                if not user or not check_password_hash(user[0]["password"], current):
                    error = "Current password is incorrect."
                else:
                    db.execute(
                        "UPDATE users SET password = %s WHERE id = %s",
                        generate_password_hash(new), session["user_id"]
                    )
                    success = "Password updated."
        elif action == "avatar":
            pic = save_profile_upload(request.files.get("profile_pic"))
            if not pic:
                error = "Please upload a valid image (png/jpg)."
            else:
                db.execute(
                    "UPDATE users SET profile_pic = %s WHERE id = %s",
                    pic, session["user_id"]
                )
                success = "Profile picture updated."

    user = db.execute("SELECT profile_pic FROM users WHERE id = %s", session["user_id"])
    profile_pic = user[0]["profile_pic"] if user else None
    return render_template("settings.html", error=error, success=success, profile_pic=profile_pic)


def home():
    from app import db, status_for, VALID_GRADES, VALID_SECTIONS

    if "user_id" not in session:
        return redirect(url_for("login"))

    role   = session.get("role")
    now_ts = int(time.time())

    if role == "admin":
        return redirect(url_for("admin_dashboard"))

    elif role == "principal":
        school    = db.execute("SELECT id FROM schools WHERE principal_id = %s", session["user_id"])
        school_id = school[0]["id"] if school else None
        students  = []
        teachers  = []
        if school_id:
            students = db.execute("""
                SELECT u.id, u.username, g.grade, u.is_logged_in, u.last_seen
                FROM users u LEFT JOIN grades g ON u.id = g.user_id
                WHERE u.role = 'student' AND u.school_id = %s ORDER BY u.username
            """, school_id)
            teachers = db.execute("""
                SELECT u.id, u.username, u.department, u.phone, u.is_logged_in, u.last_seen
                FROM users u WHERE u.role = 'teacher' AND u.school_id = %s ORDER BY u.username
            """, school_id)
        for u in students:
            u["status"] = status_for(u, now_ts)
        for t in teachers:
            t["status"] = status_for(t, now_ts)
        return render_template("principal_dashboard.html", students=students, teachers=teachers)

    elif role == "teacher":
        uid = session["user_id"]
        u   = db.execute("SELECT is_librarian FROM users WHERE id = %s", uid)
        session["is_librarian"] = bool(u and u[0]["is_librarian"])
        if session["is_librarian"]:
            return redirect(url_for("librarian_library"))

        counts = {k: 0 for k in [
            "inbox_unread", "inbox_received", "student_unread", "student_received",
            "sent_students", "sent_admin", "sent_circulars", "sent_homework",
            "news_unread", "news_total"
        ]}
        students = db.execute("""
            SELECT u.username, g.grade, g.section, g.dob FROM users u
            JOIN grades g ON u.id = g.user_id WHERE u.role = 'student' ORDER BY u.username
        """)
        counts["inbox_unread"]     = db.execute("SELECT COUNT(*) AS c FROM messages m JOIN users u ON m.sender_id = u.id WHERE m.recipient_id = %s AND m.is_read = 0 AND u.role IN ('admin','teacher')", uid)[0]["c"]
        counts["inbox_received"]   = db.execute("SELECT COUNT(*) AS c FROM messages m JOIN users u ON m.sender_id = u.id WHERE m.recipient_id = %s AND u.role IN ('admin','teacher')", uid)[0]["c"]
        counts["student_unread"]   = db.execute("SELECT COUNT(*) AS c FROM messages m JOIN users u ON m.sender_id = u.id WHERE m.recipient_id = %s AND m.is_read = 0 AND u.role = 'student'", uid)[0]["c"]
        counts["student_received"] = db.execute("SELECT COUNT(*) AS c FROM messages m JOIN users u ON m.sender_id = u.id WHERE m.recipient_id = %s AND u.role = 'student'", uid)[0]["c"]
        counts["sent_students"]    = db.execute("SELECT COUNT(*) AS c FROM messages m JOIN users u ON m.recipient_id = u.id WHERE m.sender_id = %s AND u.role = 'student'", uid)[0]["c"]
        counts["sent_admin"]       = db.execute("SELECT COUNT(*) AS c FROM messages m JOIN users u ON m.recipient_id = u.id WHERE m.sender_id = %s AND u.role = 'admin'", uid)[0]["c"]
        counts["sent_circulars"]   = db.execute("SELECT COUNT(*) AS c FROM circulars WHERE sender_id = %s", uid)[0]["c"]
        counts["sent_homework"]    = db.execute("SELECT COUNT(*) AS c FROM homework WHERE sender_id = %s", uid)[0]["c"]
        counts["news_total"]       = db.execute("SELECT COUNT(*) AS c FROM news")[0]["c"]
        counts["news_unread"]      = db.execute("SELECT COUNT(*) AS c FROM news n WHERE n.id NOT IN (SELECT news_id FROM news_seen WHERE user_id = %s)", uid)[0]["c"]
        return render_template("teacher_home.html", students=students, counts=counts)

    else:  # student
        uid            = session["user_id"]
        entry          = db.execute("SELECT * FROM grades WHERE user_id = %s", uid)
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
                    "INSERT INTO grades (user_id, name, grade, section, dob) VALUES (%s, %s, %s, %s, %s)",
                    uid, session.get("username", ""), grade, section, dob
                )
                info_submitted = True
                message = "Info submitted!"
            else:
                error = "All fields required. Section must be A-G."

        student_info       = entry[0] if entry else None
        messages           = []
        homework_list      = []
        circulars_list     = []
        attendance_summary = None
        attendance_records = []
        results            = []
        library_records    = []
        canteen_menu       = []
        calendar_events    = []
        reports            = []

        if student_info:
            g = student_info["grade"]
            counts["inbox_unread"]     = db.execute("SELECT COUNT(*) AS c FROM messages WHERE recipient_id = %s AND is_read = 0", uid)[0]["c"]
            counts["inbox_total"]      = db.execute("SELECT COUNT(*) AS c FROM messages WHERE recipient_id = %s", uid)[0]["c"]
            counts["sent_total"]       = db.execute("SELECT COUNT(*) AS c FROM messages WHERE sender_id = %s", uid)[0]["c"]
            counts["circulars_unread"] = db.execute("SELECT COUNT(*) AS c FROM circulars c WHERE c.grade = %s AND c.id NOT IN (SELECT circular_id FROM circulars_seen WHERE user_id = %s)", g, uid)[0]["c"]
            counts["circulars_total"]  = db.execute("SELECT COUNT(*) AS c FROM circulars WHERE grade = %s", g)[0]["c"]
            counts["homework_unread"]  = db.execute("SELECT COUNT(*) AS c FROM homework h WHERE h.grade = %s AND h.id NOT IN (SELECT homework_id FROM homework_seen WHERE user_id = %s)", g, uid)[0]["c"]
            counts["homework_total"]   = db.execute("SELECT COUNT(*) AS c FROM homework WHERE grade = %s", g)[0]["c"]
            counts["news_unread"]      = db.execute("SELECT COUNT(*) AS c FROM news n WHERE n.id NOT IN (SELECT news_id FROM news_seen WHERE user_id = %s)", uid)[0]["c"]
            counts["news_total"]       = db.execute("SELECT COUNT(*) AS c FROM news")[0]["c"]
            counts["total"]            = counts["inbox_unread"] + counts["circulars_unread"] + counts["homework_unread"] + counts["news_unread"]

            messages = db.execute("""
                SELECT m.message AS content, m.created_at, u.username AS sender
                FROM messages m JOIN users u ON m.sender_id = u.id
                WHERE m.recipient_id = %s ORDER BY m.created_at DESC LIMIT 5
            """, uid)
            homework_list = db.execute("""
                SELECT h.title, h.body, h.attachment, h.created_at, u.username AS sender, h.grade
                FROM homework h JOIN users u ON h.sender_id = u.id
                WHERE h.grade = %s ORDER BY h.created_at DESC LIMIT 6
            """, g)
            circulars_list = db.execute("""
                SELECT c.title, c.body, c.attachment, c.created_at, u.username AS sender
                FROM circulars c JOIN users u ON c.sender_id = u.id
                WHERE c.grade = %s ORDER BY c.created_at DESC LIMIT 6
            """, g)
            results = db.execute("""
                SELECT r.exam_name, r.subject, r.marks, r.out_of, r.grade, r.remarks
                FROM results r WHERE r.student_id = %s ORDER BY r.exam_name, r.subject
            """, uid)
            att_records = db.execute("""
                SELECT a.date, a.status, u.username AS marked_by
                FROM attendance a JOIN users u ON a.marked_by = u.id
                WHERE a.student_id = %s ORDER BY a.date DESC
            """, uid)
            attendance_records = att_records
            total_att = len(att_records)
            present   = sum(1 for r in att_records if r["status"] == "present")
            absent    = sum(1 for r in att_records if r["status"] == "absent")
            late      = sum(1 for r in att_records if r["status"] == "late")
            pct       = round(present / total_att * 100, 1) if total_att else 0
            attendance_summary = {"present": present, "absent": absent, "late": late, "percent": pct}
            library_records = db.execute("""
                SELECT l.book_title, l.author, l.issued_date, l.due_date, l.returned_date
                FROM library_records l WHERE l.student_id = %s ORDER BY l.issued_date DESC
            """, uid)
            canteen_menu = db.execute(
                "SELECT * FROM canteen_menu ORDER BY CASE day_of_week "
                "WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3 "
                "WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6 ELSE 7 END, item_name"
            )
            from datetime import date as dt
            calendar_events = db.execute(
                "SELECT title, description, event_date FROM calendar_events "
                "WHERE event_date >= %s ORDER BY event_date LIMIT 10", str(dt.today())
            )
            reports = db.execute("""
                SELECT r.report_type, r.title, r.description, r.attachment, r.created_at,
                       u.username AS sender
                FROM student_reports r JOIN users u ON r.sender_id = u.id
                WHERE r.student_id = %s ORDER BY r.created_at DESC
            """, uid)
            school_row = db.execute(
                "SELECT s.name AS school_name FROM schools s JOIN users u ON u.school_id = s.id WHERE u.id = %s", uid
            )
            if school_row:
                student_info = dict(student_info)
                student_info["school_name"] = school_row[0]["school_name"]

        return render_template(
            "student_dashboard.html",
            info_submitted=info_submitted, message=message, error=error,
            name_prefill=session.get("username", ""),
            student_info=student_info, counts=counts,
            messages=messages, homework_list=homework_list, circulars_list=circulars_list,
            results=results, attendance_summary=attendance_summary,
            attendance_records=attendance_records, library_records=library_records,
            canteen_menu=canteen_menu, calendar_events=calendar_events, reports=reports
        )


def profile_view(user_id):
    from app import db
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = db.execute("""
        SELECT u.id, u.username, u.role, u.profile_pic, u.department, u.phone, s.name AS school_name
        FROM users u
        LEFT JOIN schools s ON u.school_id = s.id
        WHERE u.id = %s
    """, user_id)
    if not user:
        return redirect(url_for("home"))
    return render_template("profile.html", profile=user[0])