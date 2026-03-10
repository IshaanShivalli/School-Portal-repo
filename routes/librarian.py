from flask import render_template, request, redirect, url_for, session, abort
from datetime import date, timedelta


def _require_librarian():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "teacher":
        abort(403)
    from app import db
    u = db.execute("SELECT is_librarian FROM users WHERE id = ?", session["user_id"])
    if not u or not u[0]["is_librarian"]:
        abort(403)
    return None


def librarian_library():
    from app import db
    guard = _require_librarian()
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
        action = request.form.get("action", "")

        if action == "issue":
            student_id  = request.form.get("student_id", "").strip()
            book_title  = request.form.get("book_title", "").strip()
            author      = request.form.get("author", "").strip()
            issued_date = request.form.get("issued_date", str(date.today()))
            days        = int(request.form.get("days", 14))
            due_date    = str(date.fromisoformat(issued_date) + timedelta(days=days))

            if not student_id or not book_title:
                error = "Student and book title are required."
            else:
                db.execute(
                    "INSERT INTO library_records (student_id, librarian_id, book_title, author, issued_date, due_date) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    int(student_id), session["user_id"], book_title, author, issued_date, due_date
                )
                success = f"Book '{book_title}' issued!"

        elif action == "return":
            record_id = request.form.get("record_id", "").strip()
            if record_id:
                db.execute(
                    "UPDATE library_records SET returned_date = ? WHERE id = ?",
                    str(date.today()), int(record_id)
                )
                success = "Book marked as returned!"

    # All active (not returned) records
    active = db.execute("""
        SELECT l.id, l.book_title, l.author, l.issued_date, l.due_date, l.returned_date,
               u.username AS student_name, g.grade
        FROM library_records l
        JOIN users u ON l.student_id = u.id
        JOIN grades g ON l.student_id = g.user_id
        WHERE l.returned_date IS NULL
        ORDER BY l.due_date
    """)

    # All history
    history = db.execute("""
        SELECT l.id, l.book_title, l.author, l.issued_date, l.due_date, l.returned_date,
               u.username AS student_name, g.grade
        FROM library_records l
        JOIN users u ON l.student_id = u.id
        JOIN grades g ON l.student_id = g.user_id
        ORDER BY l.issued_date DESC
        LIMIT 50
    """)

    today = str(date.today())
    return render_template("librarian_library.html",
                           students=students, active=active, history=history,
                           today=today, success=success, error=error)