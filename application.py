import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
import requests

from helpers import apology, login_required, lookup, usd

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
db = SQL("sqlite:///finance.db")

# Make sure API key is set
#if not os.environ.get("API_KEY"):
    #raise RuntimeError("API_KEY not set")

# export API_KEY=pk_d44d44758a3149ef96e5e6c03098a089


def get_portifolio():
    portifolio = db.execute("SELECT * FROM portifolio WHERE user_id = :user_id and shares <> 0", user_id=session["user_id"])
    for stock in portifolio:
        stock_data = lookup(stock["symbol"])
        stock["name"] = stock_data["name"]
        stock["price"] = stock_data["price"]
        stock["total"] = int(stock["shares"]) * float(stock_data["price"])

    return portifolio


def get_history():
    history = db.execute("SELECT * FROM operations WHERE user_id = :user_id", user_id=session["user_id"])
    for item in history:
        item["price"] = item["price"]

    return history


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    portifolio = get_portifolio()

    user = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])

    total = 0.0
    for stock in portifolio:
        total += stock["total"]
    total += user[0]["cash"]

    return render_template("index.html", portifolio=portifolio, cash=user[0]["cash"], total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "GET":
        return render_template("buy.html")
    elif request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Symbol must be provided")

        stock_data = lookup(symbol)
        if not stock_data:
            return apology("Invalid symbol")

        shares = request.form.get("shares")
        if not shares:
            return apology("Shares must be provided")
        if not shares.isnumeric():
            return apology("Shares must be a number")
        if int(shares) <= 0:
            return apology("Shares must be a positive number")

        shares = float(shares)
        price = float(stock_data["price"])
        total = shares * price

        rows = db.execute("SELECT cash FROM users WHERE id = :id",  id=session["user_id"])
        if len(rows) != 1:
            return apology(f"Was not possible to find the user {session['user_id']} and his cash")
        if float(rows[0]["cash"]) < total:
            return apology(f"You haven't enought money for this purchase")

        db.execute("INSERT INTO operations (user_id, datetime, symbol, shares, price, total) " +
                   "VALUES (:user_id, :datetime, :symbol, :shares, :price, :total)",
                   user_id=session["user_id"],
                   datetime=datetime.now(),
                   symbol=stock_data["symbol"],
                   shares=shares,
                   price=stock_data["price"],
                   total=total)

        rows = db.execute("SELECT shares FROM portifolio where user_id = :user_id and symbol = :symbol",
                          user_id=session["user_id"],
                          symbol=stock_data["symbol"])

        if len(rows) == 0:
            db.execute("INSERT INTO portifolio (user_id, symbol, shares) " +
                       "VALUES (:user_id, :symbol, :shares)",
                       user_id=session["user_id"],
                       symbol=stock_data["symbol"],
                       shares=shares)
        elif len(rows) == 1:
            db.execute("UPDATE portifolio SET shares = :shares WHERE user_id = :user_id and symbol = :symbol",
                       user_id=session["user_id"],
                       symbol=stock_data["symbol"],
                       shares=shares + rows[0]["shares"])
        else:
            return apology("It's embarrassing, but something really bad happen and you can't buy this stock.")

        db.execute("UPDATE users SET cash = cash - :cash WHERE id = :user_id",
                   user_id=session["user_id"],
                   cash=total)

        flash("Bought")

        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = get_history()

    return render_template("history.html", history=history)


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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

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


@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    if request.method   == "GET":
        return render_template("deposit.html")
    elif request.method == "POST":
        cash = request.form.get("cash")
        if not cash:
            return apology("Cash must be a positive number")
        if float(cash) <= 0:
            return apology("Cash must be a positive number")

        cash = float(cash)

        db.execute("INSERT INTO operations (user_id, datetime, symbol, shares, price, total) " +
                   "VALUES (:user_id, :datetime, :symbol, :shares, :price, :total)",
                   user_id=session["user_id"],
                   datetime=datetime.now(),
                   symbol="CASH",
                   shares=1,
                   price=cash,
                   total=cash)

        db.execute("UPDATE users SET cash = cash + :cash WHERE id = :user_id",
                   user_id=session["user_id"],
                   cash=cash)

        flash("Deposited")

        return redirect("/")


@app.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw():
    if request.method == "GET":
        return render_template("withdraw.html")
    elif request.method == "POST":
        amount = request.form.get("amount")
        if not amount:
            return apology("Amount must be a positive number")
        if float(amount) <= 0:
            return apology("Amount must be a positive number")

        amount = float(amount)

        rows = db.execute("SELECT cash FROM users WHERE id = :id",  id=session["user_id"])
        if len(rows) != 1:
            return apology(f"Was not possible to find the user {session['user_id']} and his cash")
        if float(rows[0]["cash"]) < amount:
            return apology(f"You haven't enought money for this withdrawing")

        db.execute("INSERT INTO operations (user_id, datetime, symbol, shares, price, total) " +
                   "VALUES (:user_id, :datetime, :symbol, :shares, :price, :total)",
                   user_id=session["user_id"],
                   datetime=datetime.now(),
                   symbol="CASH",
                   shares=1,
                   price=-1*amount,
                   total=-1*amount)

        db.execute("UPDATE users SET cash = cash - :amount WHERE id = :user_id",
                   user_id=session["user_id"],
                   amount=amount)

        flash("Withdrawed")

        return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    elif request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Symbol is required")

        stock_data = lookup(symbol)
        if not stock_data:
            return apology("Invalid symbol")

        return render_template("quoted.html", name=stock_data["name"], symbol=stock_data["symbol"], price=stock_data["price"])


@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "GET":
        return render_template("change_password.html")
    elif request.method == "POST":
        password = request.form.get("password")
        if not password:
            return apology("Password is required")

        confirmation = request.form.get("confirmation")
        if not confirmation:
            return apology("Password confirmation is required")

        if password != confirmation:
            return apology("Password and confirmation don't match")

        hashed_password = generate_password_hash(password)

        db.execute("update users set hash = :hash", hash=hashed_password)

        flash("Password changed")

        return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    elif request.method == "POST":
        username = request.form.get("username")
        if not username:
            return apology("Username is required")

        password = request.form.get("password")
        if not password:
            return apology("Password is required")

        confirmation = request.form.get("confirmation")
        if not confirmation:
            return apology("Password confirmation is required")

        if password != confirmation:
            return apology("Password and confirmation don't match")

        hashed_password = generate_password_hash(password)

        rows = db.execute("select * from users where username = :username", username=username)
        if len(rows) > 0:
            return apology(f"User {username} already exists")

        id = db.execute("insert into users (username, hash) values (:username, :hash)", username=username, hash=hashed_password)

        session["user_id"] = id

        flash("Registered")

        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        return render_template("sell.html", portifolio=get_portifolio())
    elif request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Symbol must be provided")

        stock_data = lookup(symbol)
        if not stock_data:
            return apology("Invalid symbol")

        shares = request.form.get("shares")
        if not shares:
            return apology("Shares must be provided")
        if not shares.isnumeric():
            return apology("Shares must be a positive number")
        if int(shares) <= 0:
            return apology("Shares must be a positive number")

        shares = float(shares)
        price = float(stock_data["price"])
        total = shares * price

        portifolio = db.execute("SELECT shares FROM portifolio where user_id = :user_id and symbol = :symbol",
                                user_id=session["user_id"],
                                symbol=stock_data["symbol"])
        if len(portifolio) == 0:
            apology("You haven't a share of this stock")
        elif len(portifolio) == 1:
            if shares > float(portifolio[0]["shares"]):
                return apology(f"You have just {portifolio[0]['shares']} shares of this stock")
        else:
            return apology("It's embarrassing, but something really bad happen and you can't sell this stock.")

        db.execute("INSERT INTO operations (user_id, datetime, symbol, shares, price, total) "+
                   "VALUES (:user_id, :datetime, :symbol, :shares, :price, :total)",
                   user_id=session["user_id"],
                   datetime=datetime.now(),
                   symbol=stock_data["symbol"],
                   shares=shares*-1,
                   price=stock_data["price"],
                   total=total)

        db.execute("UPDATE portifolio SET shares = shares - :shares WHERE user_id = :user_id and symbol = :symbol",
                   user_id=session["user_id"],
                   symbol=stock_data["symbol"],
                   shares=shares)

        db.execute("UPDATE users SET cash = cash + :cash WHERE id = :user_id",
                   user_id=session["user_id"],
                   cash=total)

        flash("Sold")

        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
