from flask import render_template, request, redirect, url_for, session, abort
from datetime import date, timedelta


def _require_librarian():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "teacher":
        abort(403)
    from app import db
    u = db.execute("SELECT is_librarian FROM users WHERE id = %s", session["user_id"])
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
            roll_number = request.form.get("roll_number", "").strip()
            book_title  = request.form.get("book_title", "").strip()
            author      = request.form.get("author", "").strip()
            issued_date = request.form.get("issued_date", str(date.today()))
            days        = int(request.form.get("days", 14))
            due_date    = str(date.fromisoformat(issued_date) + timedelta(days=days))

            if not roll_number or not book_title:
                error = "Roll number and book title are required."
            else:
                student = db.execute("""
                    SELECT u.id, u.username
                    FROM users u
                    JOIN grades g ON u.id = g.user_id
                    WHERE g.roll_number = %s
                    LIMIT 1
                """, roll_number)
                if not student:
                    # need to fetch active/history here too for the template
                    active  = db.execute("""
                        SELECT l.id, l.book_title, l.author, l.issued_date, l.due_date, l.returned_date,
                               u.username AS student_name, g.grade
                        FROM library_records l
                        JOIN users u ON l.student_id = u.id
                        JOIN grades g ON l.student_id = g.user_id
                        WHERE l.returned_date IS NULL ORDER BY l.due_date
                    """)
                    history = db.execute("""
                        SELECT l.id, l.book_title, l.author, l.issued_date, l.due_date, l.returned_date,
                               u.username AS student_name, g.grade
                        FROM library_records l
                        JOIN users u ON l.student_id = u.id
                        JOIN grades g ON l.student_id = g.user_id
                        ORDER BY l.issued_date DESC LIMIT 50
                    """)
                    return render_template("librarian_library.html",
                                           students=students, active=active, history=history,
                                           today=str(date.today()), success=success,
                                           error="No student found with that roll number.")
                db.execute(
                    "INSERT INTO library_records (student_id, librarian_id, book_title, author, issued_date, due_date) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    int(student[0]["id"]), session["user_id"], book_title, author, issued_date, due_date
                )
                success = f"Book '{book_title}' issued to {student[0]['username']}!"

        elif action == "return":
            record_id = request.form.get("record_id", "").strip()
            if record_id:
                db.execute(
                    "UPDATE library_records SET returned_date = %s WHERE id = %s",
                    str(date.today()), int(record_id)
                )
                success = "Book marked as returned!"

    active = db.execute("""
        SELECT l.id, l.book_title, l.author, l.issued_date, l.due_date, l.returned_date,
               u.username AS student_name, g.grade
        FROM library_records l
        JOIN users u ON l.student_id = u.id
        JOIN grades g ON l.student_id = g.user_id
        WHERE l.returned_date IS NULL
        ORDER BY l.due_date
    """)

    history = db.execute("""
        SELECT l.id, l.book_title, l.author, l.issued_date, l.due_date, l.returned_date,
               u.username AS student_name, g.grade
        FROM library_records l
        JOIN users u ON l.student_id = u.id
        JOIN grades g ON l.student_id = g.user_id
        ORDER BY l.issued_date DESC
        LIMIT 50
    """)

    return render_template("librarian_library.html",
                           students=students, active=active, history=history,
                           today=str(date.today()), success=success, error=error)