import os

from datetime import datetime
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd, calculateScore

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///balance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():

    """Show portfolio of stocks"""
    rows = db.execute("""SELECT wallet.symbol, wallet.company, wallet.shares, grades.grade
                        FROM wallet INNER JOIN grades
                        ON wallet.symbol = grades.symbol
                        WHERE wallet.userId = ?""",
                        session["user_id"])
    totalValue = 0
    totalGrade = 0
    for row in rows:
        print(row)
        price = lookup(row["symbol"])["price"]
        row["total"] = price * row["shares"]
        totalValue += row["total"]
        totalGrade += row["grade"]

    for row in rows:
        row["actualWeight"] = round((row["total"] / totalValue)*100, 2)
        row["idealWeight"] = round((row["grade"]/totalGrade)*100, 2)
        diff = row["idealWeight"] - row["actualWeight"]
        if diff > 0:
            row["todo"] = "Buy"
        else:
            row["todo"] = "Wait"

    return render_template("index.html", rows=rows)


@app.route("/answer", methods=["GET", "POST"])
@login_required
def answer():
    if request.method == "POST":
        stock = lookup(request.form.get("ticker"))
        ticker = stock["symbol"]
        company = stock["name"]
        price = stock["price"]
        answers = db.execute("SELECT * FROM answers WHERE symbol = ? and userId = ?", ticker, session["user_id"])
        if (ticker):
            if (len(answers) > 0):
                return redirect(url_for("answered", ticker=ticker, company=company, price=price))
            else:
                return redirect(url_for("answers", ticker=ticker, company=company, price=price))
        else:
             return apology("Invalid Ticker", 400)
    else:
        rows = db.execute("SELECT symbol, grade FROM grades WHERE userId = ?", session["user_id"])
        for row in rows:
            row["grade"] = round(row["grade"], 2)
            row["name"] = lookup(row["symbol"])["name"]
        return render_template("answer.html", rows=rows)


@app.route("/answered", methods=["GET", "POST"])
@login_required
def answered():
    ticker = request.args['ticker']
    company = request.args['company']
    price = request.args['price']
    questions = db.execute("SELECT questions.question, answers.answer FROM questions INNER JOIN answers ON questions.id = answers.questionId WHERE answers.userId = ? AND answers.symbol = ?", session["user_id"], ticker)
    return render_template("answered.html", questions=questions, ticker=ticker, company=company, price=price)


@app.route("/answers", methods=["GET", "POST"])
@login_required
def answers():
    ticker = request.args['ticker']
    company = request.args['company']
    price = request.args['price']
    questions = db.execute("SELECT * FROM questions WHERE userId = ?", session["user_id"])
    return render_template("answers.html", questions=questions, ticker=ticker, company=company, price=price)


@app.route("/answering", methods=["POST"])
@login_required
def answering():
    ticker = lookup(request.form.get("ticker"))["symbol"]
    questions = db.execute("SELECT * FROM questions WHERE userId = ?", session["user_id"])

    for question in questions:
        answer = request.form.get(str(question["id"]))
        if not answer:
            answer = "Não"
        db.execute("INSERT INTO answers (symbol, userId, questionId, answer) VALUES (? , ?, ?, ?)",
                    ticker, session["user_id"], question["id"], answer)
    flash('Question answered')

    db.execute("INSERT INTO grades (symbol, userId, grade) VALUES (?, ?, ?)",
                    ticker, session["user_id"],  calculateScore(ticker, session["user_id"]))

    return redirect("/answer")


@app.route("/questions", methods=["GET", "POST"])
@login_required
def questions():
    questions = db.execute("SELECT * FROM questions WHERE userId = ?", session["user_id"])
    types = ["Boolean", "Range", "Value", "Direction"]
    if request.method == "POST":
        question = request.form.get("question")
        # check to see if user type an integer
        if (question):
            flash('Question added')
            db.execute("INSERT INTO questions (userId, question, questionWeight) VALUES (?, ?, ?)",
                        session["user_id"], question, int(request.form.get("weight")))
            return redirect("/questions")
        else:
            return apology("Invalid Token", 400)
    else:
        return render_template("questions.html", types=types, questions=questions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE userName = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["paswordHash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]
        # Redirect user to home page
        return redirect("/wallet")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # checks if passwords matches
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Password don't match", 400)

        else:
            # checks if username already exists in DB
            users = db.execute("SELECT userName FROM users WHERE userName = ?", request.form.get("username"))
            if not users:
                # register user
                flash('User Registred')
                db.execute("INSERT INTO users (userName, paswordHash) VALUES (? , ?)", request.form.get("username"),
                           generate_password_hash(request.form.get("password")))
                rows = db.execute("SELECT id FROM users WHERE userName = ?", request.form.get("username"))
                session["user_id"] = rows[0]["id"]
                return redirect("/wallet")
            else:
                return apology("Username Taken", 400)
    return render_template("register.html")


@app.route("/change", methods=["GET", "POST"])
@login_required
def change():
    """Change password"""
    if request.method == "POST":

        # Ensure lastPassuwod was submitted
        if not request.form.get("lastPassword"):
            return apology("must provide last password", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        elif not request.form.get("confirmation"):
            return apology("must provide confirmation", 400)

        else:
            # checks if correct password
            rows = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])

            if len(rows) != 1 or not check_password_hash(rows[0]["paswordHash"], request.form.get("lastPassword")):
                return apology("Invalid password", 400)
            elif request.form.get("password") != request.form.get("confirmation"):
                return apology("Passwords don't match", 400)
            else:
                # change password in DB
                flash('Password changed')
                db.execute("UPDATE users SET paswordHash = ? WHERE id = ?",
                            generate_password_hash(request.form.get("password")), session["user_id"])
                return redirect("/")
    else:
        return render_template("change.html")


@app.route("/wallet", methods=["GET", "POST"])
@login_required
def wallet():

    if request.method == "POST":
        ticker = lookup(request.form.get("symbol"))

        # check to see if user type an integer
        if (ticker):
            db.execute("INSERT INTO wallet (userId, symbol, company, shares) VALUES (? ,? ,?, ?)",
                        session["user_id"], ticker["symbol"], ticker["name"], request.form.get("shares"))
            return redirect("/wallet")
        else:
            return apology("Invalid Token", 400)
    else:
        """Show portfolio of stocks"""
        rows = db.execute("SELECT * FROM wallet WHERE userId = ?", session["user_id"])
        total = 0
        # add values of price and total, and sum the total of the wallet
        for row in rows:
            row["price"] = lookup(row["symbol"])["price"]
            row["total"] = (row["price"] * row["shares"])
            total += row["total"]
            row["price"] = usd(row["price"])
            row["total"] = usd(row["total"])
        return render_template("wallet.html", rows=rows, total=usd(total))


@app.route("/deleteStock", methods=["POST"])
@login_required
def deleteStock():
    ticker = request.form.get("stock")
    db.execute("DELETE FROM wallet WHERE symbol = ?", ticker)
    return redirect("/wallet")

@app.route("/deleteQuestion", methods=["POST"])
@login_required
def deleteQuestion():
    questionId = request.form.get("question")
    db.execute("DELETE FROM questions WHERE id = ?", questionId)
    return redirect("/questions")

@app.route("/deleteAnswers", methods=["POST"])
@login_required
def deleteAnswers():
    symbol = request.form.get("symbol")
    db.execute("DELETE FROM grades WHERE symbol = ? and userId  = ?", symbol, session["user_id"])
    db.execute("DELETE FROM answers WHERE symbol = ? and userId  = ?", symbol, session["user_id"])
    return redirect("/answer")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)