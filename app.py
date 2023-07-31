from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import re
from datetime import datetime

app = Flask(__name__)
app.secret_key = "root"


def create_tables():
    with sqlite3.connect("library.db", check_same_thread=False) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS books (
                id TEXT PRIMARY KEY,
                title TEXT,
                author TEXT,
                stock INTEGER
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY,
                name TEXT,
                outstanding_debt REAL,
                book_fees REAL DEFAULT 0  -- Add the book_fees column with a default value of 0
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY,
                book_id TEXT,
                member_id INTEGER,
                issue_date TEXT,
                return_date TEXT,
                returned INTEGER
            )
            """
        )
        conn.commit()


create_tables()
db = sqlite3.connect("library.db", check_same_thread=False)
cursor = db.cursor()


def execute_query(query, args=()):
    cursor.execute(query, args)
    db.commit()


def fetch_data(query, args=()):
    cursor.execute(query, args)
    return cursor.fetchall()


def is_valid_alphanumeric(input_string):
    return bool(re.match("^[A-Za-z0-9]+$", input_string))


def get_member_id_by_name(member_name):
    member = fetch_data("SELECT id FROM members WHERE name = ?", (member_name,))
    return member[0][0] if member else None


def calculate_rent(issue_date):
    days_issued = (datetime.now() - datetime.strptime(issue_date, "%Y-%m-%d")).days
    return max(days_issued * 10, 0)


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/add_book", methods=["GET", "POST"])
def add_book():
    if request.method == "POST":
        book_id = request.form["book_id"]
        title = request.form["title"]
        author = request.form["author"]
        stock = request.form["stock"]

        if not is_valid_alphanumeric(book_id):
            flash("Book ID should be alphanumeric.", "error")
            return redirect(url_for("add_book"))

        execute_query(
            "INSERT INTO books (id, title, author, stock) VALUES (?, ?, ?, ?)",
            (book_id, title, author, stock),
        )
        flash("Book added successfully!", "success")
        return redirect(url_for("add_book"))

    books = fetch_data("SELECT * FROM books")
    return render_template("add_book.html", books=books)


@app.route("/edit_book/<int:book_id>", methods=["GET", "POST"])
def edit_book(book_id):
    if request.method == "POST":
        title = request.form["title"]
        author = request.form["author"]
        stock = int(request.form["stock"])
        execute_query(
            "UPDATE books SET title = ?, author = ?, stock = ? WHERE id = ?",
            (title, author, stock, book_id),
        )
        flash("Book updated successfully!", "success")
        return redirect(url_for("add_book"))
    else:
        book = fetch_data("SELECT * FROM books WHERE id = ?", (book_id,))
        return render_template("edit_book.html", book=book[0])


@app.route("/delete_book/<int:book_id>", methods=["POST"])
def delete_book(book_id):
    if request.method == "POST":
        execute_query("DELETE FROM books WHERE id = ?", (book_id,))
        flash("Book deleted successfully!", "success")
    return redirect(url_for("add_book"))


@app.route("/add_member", methods=["GET", "POST"])
def add_member():
    if request.method == "POST":
        name = request.form["name"]
        execute_query("INSERT INTO members (name) VALUES (?)", (name,))
        flash("Member added successfully!", "success")
        return redirect(url_for("add_member"))

    members = fetch_data("SELECT * FROM members")
    return render_template("add_member.html", members=members)


@app.route("/edit_member/<int:member_id>", methods=["GET", "POST"])
def edit_member(member_id):
    if request.method == "POST":
        name = request.form["name"]
        execute_query("UPDATE members SET name = ? WHERE id = ?", (name, member_id))
        flash("Member updated successfully!", "success")
        return redirect(url_for("add_member"))
    else:
        member = fetch_data("SELECT * FROM members WHERE id = ?", (member_id,))
        return render_template("edit_member.html", member=member[0])


@app.route("/delete_member/<int:member_id>", methods=["POST"])
def delete_member(member_id):
    execute_query("DELETE FROM members WHERE id = ?", (member_id,))
    flash("Member deleted successfully!", "success")
    return redirect(url_for("add_member"))


def get_member_debt(member_id):
    transactions = fetch_data(
        "SELECT SUM(returned * (julianday(return_date) - julianday(issue_date)) * 10) "
        "FROM transactions "
        "WHERE member_id = ?",
        (member_id,),
    )
    return transactions[0][0] if transactions[0][0] else 0


@app.route("/issue_book", methods=["GET", "POST"])
def issue_book():
    if request.method == "POST":
        book_id = request.form["book_id"]
        member_id = int(request.form["member_id"])

        book = fetch_data("SELECT * FROM books WHERE id = ?", (book_id,))
        if not book or book[0][3] == 0:
            flash("Book not available in stock.", "error")
        else:
            member_debt = get_member_debt(member_id)
            if member_debt >= 500:
                flash("Member has outstanding debt. Cannot issue a book.", "error")
            else:
                execute_query(
                    "INSERT INTO transactions (book_id, member_id, issue_date, returned) "
                    "VALUES (?, ?, DATE('now'), 0)",
                    (book_id, member_id),
                )
                execute_query(
                    "UPDATE books SET stock = stock - 1 WHERE id = ?", (book_id,)
                )
                flash("Book issued successfully!", "success")

    issued_books_data = fetch_data(
        "SELECT transactions.id, books.id, books.title, books.author, members.name, transactions.issue_date "
        "FROM transactions "
        "JOIN books ON transactions.book_id = books.id "
        "JOIN members ON transactions.member_id = members.id "
        "WHERE transactions.returned = 0"
    )

    issued_books = [
        {
            "transaction_id": row[0],
            "book_id": row[1],
            "book_title": row[2],
            "book_author": row[3],
            "member_name": row[4],
            "issue_date": row[5],
        }
        for row in issued_books_data
    ]

    members = fetch_data("SELECT * FROM members")
    books = fetch_data("SELECT * FROM books")
    return render_template(
        "issue_book.html", members=members, books=books, issued_books=issued_books
    )


@app.route("/return_book", methods=["GET", "POST"])
def return_book():
    if request.method == "POST":
        member_name = request.form["member_name"]
        book_id = request.form["book_id"]

        if not member_name or not book_id:
            flash("Please select a valid member and book.", "error")
        else:
            member_id = get_member_id_by_name(member_name)
            if not member_id:
                flash("Member not found. Please enter a valid member name.", "error")
            else:
                execute_query(
                    "UPDATE transactions SET returned = 1, return_date = DATE('now') "
                    "WHERE member_id = ? AND book_id = ? AND returned = 0",
                    (member_id, book_id),
                )
                returned_books_count = cursor.rowcount

                if returned_books_count == 0:
                    flash(
                        "No such book issued to this member is pending return.", "error"
                    )
                else:
                    execute_query(
                        "UPDATE books SET stock = stock + 1 WHERE id = ?", (book_id,)
                    )

                    flash(f"Book returned successfully!", "success")
                    return redirect(url_for("return_book"))

    issued_books_data = fetch_data(
        "SELECT transactions.id, books.id, books.title, books.author, members.name, transactions.issue_date "
        "FROM transactions "
        "JOIN books ON transactions.book_id = books.id "
        "JOIN members ON transactions.member_id = members.id "
        "WHERE transactions.returned = 0"
    )

    member_names = set([issued_book[4] for issued_book in issued_books_data])

    issued_books = [
        {
            "transaction_id": row[0],
            "book_id": row[1],
            "book_title": row[2],
            "book_author": row[3],
            "member_name": row[4],
            "issue_date": row[5],
            "rent": calculate_rent(row[5]),
        }
        for row in issued_books_data
    ]

    return render_template(
        "return_book.html", issued_books=issued_books, member_names=member_names
    )


@app.route("/search_books", methods=["POST"])
def search_books():
    keyword = request.form["keyword"]
    books = fetch_data(
        "SELECT * FROM books WHERE title LIKE ? OR author LIKE ?",
        ("%" + keyword + "%", "%" + keyword + "%"),
    )
    return render_template("add_book.html", books=books)


if __name__ == "__main__":
    app.run(debug=True)
