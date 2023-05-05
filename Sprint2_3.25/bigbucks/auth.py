import functools
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash
from .db import get_db
import yfinance as yf
import yahooquery as yq


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

@bp.route('/users')
@login_required
def users():
    if g.user['role'] != 'admin':
        flash("You do not have permission to view this page.", 'error')
        return redirect(url_for('auth.login'))
    db = get_db()
    users = db.execute('''SELECT user.username, transactions.*, stocks.symbol
                          FROM user
                          JOIN transactions ON user.id = transactions.user_id
                          JOIN stocks ON transactions.stock_id = stocks.id;
''').fetchall()
    dbb = get_db()
    portfolio_report = dbb.execute('''SELECT user.id, user.username, stocks.symbol, portfolios.shares_owned, balance.user_balance, transactions.price
FROM user
INNER JOIN portfolios ON user.id = portfolios.user_id
INNER JOIN stocks ON portfolios.stock_id = stocks.id
INNER JOIN balance ON user.id = balance.user_id
INNER JOIN transactions ON portfolios.stock_id = transactions.stock_id AND portfolios.user_id = transactions.user_id;
''').fetchall()
    dbbb = get_db()
    market_report = dbbb.execute('''SELECT stocks.symbol, SUM(portfolios.shares_owned) as total_shares_owned, transactions.price as price
FROM portfolios
INNER JOIN stocks ON portfolios.stock_id = stocks.id
INNER JOIN transactions ON portfolios.stock_id = transactions.stock_id AND portfolios.user_id = transactions.user_id
GROUP BY stocks.symbol;


''').fetchall()
    return render_template('users.html', users=users,portfolio_report=portfolio_report,market_report=market_report)


@bp.route('/register-admin')
def register_admin():
    db = get_db()

    # Generate a hashed password for the admin user
    password_hash = generate_password_hash('admin123')

    # Insert the admin user into the database with the hashed password
    db.execute(
        'INSERT INTO user (username, password, role) VALUES (?, ?, ?)',
        ('admin', password_hash, 'admin')
    )
    db.commit()

    print('Admin user created!') 
    return redirect(url_for('auth.login'))
