import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash

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


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Retrieve required data from corresponding tables
    id = session.get("user_id")
    symbols = db.execute("SELECT symbol FROM portfolio WHERE id = :id", id = id)
    cash = db.execute("SELECT cash FROM users WHERE id = :id", id = id)

    #In case no stocks in portfolio
    if symbols == []:
        cash[0]['cash'] = usd(cash[0]['cash'])
        totals= [{'sum(total) + cash': cash[0]['cash']}]
        port_list = cash + totals
        return render_template("index.html", buys = port_list)
    else:
        for symbol in symbols:
            # Retrieve sum of shares from each stock
            shares = db.execute("SELECT sum(shares) FROM portfolio WHERE id = :id GROUP BY symbol HAVING symbol= :symbol", id = id, symbol = symbol['symbol'])
            # Use lookup to get latest price for stocks
            current_price = lookup(symbol['symbol'])['price']
            total_price = float(shares[0]['sum(shares)']) * current_price
            company_name = lookup(symbol['symbol'])['name']

            #Check if it is an existing stock in the table
            display = db.execute("SELECT symbol FROM display WHERE id = :id", id = id)
            if symbol in display:
                # Update with new price
                db.execute("UPDATE display SET price= :current_price, shares= :shares, total= :total_price, cash =:cash  WHERE id = :id AND symbol = :symbol",id = id, symbol = symbol['symbol'], current_price=current_price, shares = shares[0]['sum(shares)'], total_price=total_price, cash= cash[0]['cash'])
            else:
                # Insert into table upon purchase of new stock
                db.execute("INSERT INTO display (id, symbol, name, shares, price, total, cash) VALUES (:id, :symbol, :company_name , :shares, :current_price, :total_price, :cash)", id=id, symbol=symbol['symbol'], company_name=company_name, shares=shares[0]['sum(shares)'], current_price=current_price, total_price=total_price, cash= cash[0]['cash'])

        # Retrieve the sum of current price totals added to available cash
        totals= db.execute("SELECT sum(total) + cash  FROM display WHERE id = :id",id = id)

        # Employ the usd function from helpers
        totals[0]['sum(total) + cash'] = usd(totals[0]['sum(total) + cash'])
        symbols = db.execute("SELECT symbol FROM display WHERE id = :id", id = id)
        for symbol in symbols:
            shares = db.execute("SELECT shares FROM display WHERE id = :id GROUP BY symbol HAVING symbol= :symbol", id = id, symbol = symbol['symbol'])
            current_price = lookup(symbol['symbol'])['price']
            total_price = float(shares[0]['shares']) * current_price
            db.execute("UPDATE display SET price= :current_price, total= :total_price, cash = :cash  WHERE id = :id AND symbol = :symbol",id = id, symbol = symbol['symbol'], current_price=usd(current_price), total_price=usd(total_price), cash= usd(cash[0]['cash']))

        # Retrieve data to be displayed to user on index
        rows = db.execute("SELECT symbol, name, shares, price, total, cash FROM display WHERE id = :id ORDER BY symbol", id = id)
        port_list = rows + totals

        return render_template("index.html", buys = port_list)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # Retrieve user id
    id = session.get("user_id")

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure symbol was submitted
        symbol = request.form.get("symbol").upper()
        if not symbol:
            return apology("missing symbol", 400)
        elif lookup(symbol) == None:
            return apology("invalid symbol", 400)
        # Ensure shares was submitted
        elif not request.form.get("shares"):
            return apology("missing shares", 400)

        else:
            shares = request.form.get("shares")
            current_price = lookup(symbol)['price']
            company_name = lookup(symbol)['name']
            total_price = float(shares) * current_price

            # Retrieve available cash
            cash_available = db.execute("SELECT cash FROM users WHERE id = :id", id = id)
            # Check if enough cash for purchase
            if total_price > cash_available[0]["cash"]:
                return apology("can't afford", 400)
            else:
                flash("Bought!")

                # Update cash account for user
                db.execute("UPDATE users SET cash= :cash WHERE id = :id", id = id, cash= cash_available[0]['cash'] - total_price)
                # Insert purchase into relevent table
                db.execute("INSERT INTO 'portfolio' (id, symbol, name, shares, price, total) VALUES (:id, :symbol, :company_name , :shares, :price, :total_price)", id=id, symbol=symbol, company_name=company_name, shares= int(shares), price=current_price, total_price=total_price)
                # Redirect user to Index page
                return redirect("/")
    else:
        return render_template("buy.html")



@app.route("/fund", methods=["GET", "POST"])
@login_required
def fund():
    """Add funds to user account"""

        # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure correct fund amount
        fund = request.form.get("fund")
        if not fund:
            return apology("No Money", 400)
        else:
            # Add funds to existing cash
            flash("FUNDED!")
            id = session.get("user_id")
            cash_available = db.execute("SELECT cash FROM users WHERE id = :id", id = id)
            db.execute("UPDATE users SET cash= :cash WHERE id = :id", id = id, cash= cash_available[0]['cash'] + float(fund))
            #Direct user to index page
            return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("fund.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Retrieve user id
    id = session.get("user_id")

    # Select relevent data from portfolio table
    transactions = db.execute("SELECT symbol, shares, price, transacted FROM portfolio WHERE id = :id ORDER BY transacted", id = id)
    # Select data from history table
    history = db.execute("SELECT symbol, shares, price, transacted FROM history WHERE id = :id ORDER BY transacted", id = id )
    # Compare for existing data in history
    for trans in transactions:
        if not trans['transacted'] in [row['transacted'] for row in history]:
            #Update history table with new transactions
            db.execute("INSERT INTO history (id, symbol, shares, price, transacted) VALUES (:id, :symbol, :shares, :price, :transacted)", id = id, symbol = trans["symbol"], shares = trans['shares'], price = usd(trans['price']), transacted = trans['transacted'])
    # Select data to be presented to user
    history = db.execute("SELECT symbol, shares, price, transacted FROM history WHERE id = :id ORDER BY transacted", id = id )
    return render_template("history.html",buys = history)


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


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure correct spelling
        symbol = (request.form.get("symbol")).upper()
        if lookup(symbol) == None:
            return apology("Invalid symbol", 400)
        else:
            # Display stock company name and price
             return render_template("quoted.html", name = lookup(symbol)['name'], symbol = lookup(symbol)['symbol'],
             price = usd(lookup(symbol)['price']))

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("missing password", 400)

        # Test password against confirmation
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords don't match", 400)

        else:
            # Insert new username and hash into users table
            rows = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                username=request.form.get("username"), hash=generate_password_hash(request.form.get("password"),
                method='pbkdf2:sha256', salt_length=8))
            if not rows:
                flash("Username is not available")
                return render_template("register.html")

        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))
        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        flash("Registered!")
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Retrieve user id
    id = session.get("user_id")

    # Check for existing stocks
    symbols = db.execute("SELECT symbol FROM display WHERE id = :id AND shares > 0 ORDER BY symbol ", id = id)

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("missing symbol", 400)
        # Ensure shares was submitted
        elif not request.form.get("shares"):
            return apology("missing shares", 400)

        else:
            symbol = request.form.get("symbol")
            shares = request.form.get("shares")

            #Ensure enough cash available
            available_shares = db.execute("SELECT shares FROM display WHERE id = :id AND symbol = :symbol", id = id, symbol = symbol)
            if int(shares) > available_shares[0]["shares"]:
                return apology("too many shares")
            else:
                flash("Sold!")
                # Retrieve latest stock price and info
                symbol = request.form.get("symbol")
                price = lookup(symbol)['price']
                company_name = lookup(symbol)['name']
                total_price = price * float(shares) * (- 1)

                # Retrieve available cash
                cash_available = db.execute("SELECT cash FROM users WHERE id = :id", id = id)
                # Update cash account for user
                db.execute("UPDATE users SET cash= :cash WHERE id = :id", id = id, cash= cash_available[0]['cash'] - total_price)
                # Insert sale transaction into relevent table
                db.execute("INSERT INTO 'portfolio' (id, symbol, name, shares, price, total) VALUES (:id, :symbol, :company_name , :shares, :price, :total_price)", id=id, symbol=symbol, company_name=company_name, shares= -int(shares), price=price, total_price=total_price)
                # Redirect user to Index page
                return redirect("/")
    else:
        return render_template("sell.html", symbols = symbols)


def errorhandler(e):
    """Handle error"""
    return apology(e.name, e.code)


# listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
