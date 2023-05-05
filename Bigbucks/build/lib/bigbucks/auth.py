import functools
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash
from .db import get_db
import yfinance as yf
import yahooquery as yq
import datetime


bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route('/register', methods=('GET', 'POST'))
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        error = None

        if not username:
            error = 'Username is required.'
        elif not password:
            error = 'Password is required.'
        elif username.lower() == 'admin':  # Add this condition to disallow 'admin' as a username
            error = "The username 'admin' is not allowed."

        if error is None:
            try:
                db.execute(
                    "INSERT INTO user (username, password) VALUES (?, ?)",
                    (username, generate_password_hash(password)),
                )
                db.commit()
            except db.IntegrityError:
                error = f"User {username} is already registered."
            else:
                return redirect(url_for("auth.login"))

        flash(error)

    return render_template('auth/register.html')
    
@bp.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        error = None
        user = db.execute(
            'SELECT * FROM user WHERE username = ?', (username,)
        ).fetchone()

        if user is None:
            error = 'Incorrect username.'
        elif not check_password_hash(user['password'], password):
            error = 'Incorrect password.'

        if error is None:
            session.clear()
            session['user_id'] = user['id']
            return redirect(url_for('stock.index'))

        flash(error)

    return render_template('auth/login.html')

@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')

    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            'SELECT * FROM user WHERE id = ?', (user_id,)
        ).fetchone()

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))

        return view(**kwargs)

    return wrapped_view

@bp.route('/users', methods=['GET', 'POST'])
@login_required
def users():
    if g.user['role'] != 'admin':
        flash("You do not have permission to view this page.", 'error')
        return redirect(url_for('auth.login'))

    db = get_db()

    transaction_startdate_filter = ""
    transaction_enddate_filter = ""
    if request.method == 'POST':
        #print(request.form.get('start_date'))
        transaction_startdate_filter = (request.form.get('start_date'))
        transaction_enddate_filter = (request.form.get('end_date'))
        print(transaction_startdate_filter)
        print(transaction_enddate_filter)
        if transaction_startdate_filter =="" or transaction_enddate_filter =="" :
            flash("Please enter both start and end dates.", 'error')
        if transaction_startdate_filter and transaction_enddate_filter and(transaction_startdate_filter > transaction_enddate_filter):
            flash("Start date cannot be greater than end date.", 'error')
        print(transaction_startdate_filter)
        print(transaction_enddate_filter)

    if transaction_startdate_filter !="" and transaction_enddate_filter !="" :
        users_query = '''SELECT user.username, transactions.*, stocks.symbol
                         FROM user
                         JOIN transactions ON user.id = transactions.user_id
                         JOIN stocks ON transactions.stock_id = stocks.id
                         WHERE (strftime('%Y-%m-%d',transactions.closing_date) >= ?) AND (strftime('%Y-%m-%d',transactions.closing_date) <= ?);
                      '''  
        users = db.execute(users_query, (transaction_startdate_filter, transaction_enddate_filter)).fetchall()

    else:
        users_query = '''SELECT user.username, transactions.*, stocks.symbol
                         FROM user
                         JOIN transactions ON user.id = transactions.user_id
                         JOIN stocks ON transactions.stock_id = stocks.id;
                      '''
        users = db.execute(users_query).fetchall()


    dbb = get_db()
    portfolio_report = dbb.execute('''SELECT DISTINCT user.id, user.username, stocks.symbol, portfolios.shares_owned, balance.user_balance as user_balance, transactions.price as price
    FROM user
    INNER JOIN portfolios ON user.id = portfolios.user_id
    INNER JOIN stocks ON portfolios.stock_id = stocks.id
    INNER JOIN balance ON user.id = balance.user_id
    INNER JOIN transactions ON portfolios.stock_id = transactions.stock_id AND portfolios.user_id = transactions.user_id
    GROUP BY user.id, stocks.symbol;
    ''').fetchall()
    dbbb = get_db()
    market_report = dbbb.execute('''SELECT stocks.symbol, SUM(portfolios.shares_owned) as total_shares_owned, transactions.price as price
    FROM portfolios
    INNER JOIN stocks ON portfolios.stock_id = stocks.id
    INNER JOIN transactions ON portfolios.stock_id = transactions.stock_id AND portfolios.user_id = transactions.user_id
    GROUP BY stocks.symbol;
    ''').fetchall()
    return render_template('users.html', users=users,portfolio_report=portfolio_report,market_report=market_report)

def check_date(data):
    try:
        date = datetime.strptime(data,'%Y-%m-%d').date()
        if date > datetime.now().date():
            flash("You can't select a date from the future! Please select a different date.", 'error')
            raise Exception
        print(date)
        return date
    except (Exception):
        redirect(url_for("auth.users"))

@bp.route('/register-admin')
def register_admin():
    db = get_db()

    # Generate a hashed password for the admin user
    password_hash = generate_password_hash('admin123')

    try:
        # Insert the admin user into the database with the hashed password
        db.execute(
            'INSERT INTO user (username, password, role) VALUES (?, ?, ?)',
            ('admin', password_hash, 'admin')
        )
        db.commit()
        flash('Admin user created!', 'success') 
    except:
        flash('Admin user has been created before!', 'error') 

    return redirect(url_for('auth.login'))

