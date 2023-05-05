import functools
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash
from .db import get_db
import yfinance as yf
import yahooquery as yq
import datetime
import pandas as pd
import numpy as np
from scipy.optimize import minimize
import plotly.graph_objs as go
from plotly.subplots import make_subplots
import plotly.express as px


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
        #print(transaction_startdate_filter)
        #print(transaction_enddate_filter)
        if transaction_startdate_filter =="" or transaction_enddate_filter =="" :
            flash("Please enter both start and end dates.", 'error')
        if transaction_startdate_filter and transaction_enddate_filter and(transaction_startdate_filter > transaction_enddate_filter):
            flash("Start date cannot be greater than end date.", 'error')
        #print(transaction_startdate_filter)
        #print(transaction_enddate_filter)

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
    # Efficient Frontier
    EF=efficient_frontier()
    return render_template('users.html', users=users,portfolio_report=portfolio_report,market_report=market_report,data=EF)

def check_date(data):
    try:
        date = datetime.strptime(data,'%Y-%m-%d').date()
        if date > datetime.now().date():
            flash("You can't select a date from the future! Please select a different date.", 'error')
            raise Exception
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
        flash('Admin user created!','success') 
    except:
        flash('Admin user has been created before!', 'error') 

    return redirect(url_for('auth.login'))


'''
----------------------------------------------------------------------------------------
Efficient Frontier Part (Help user to figure their highest Sharpe ratio portfolio) 
----------------------------------------------------------------------------------------
'''
@bp.route('/efficient_frontier')
@login_required
def efficient_frontier():
    db=get_db()
    market_report = db.execute('''SELECT stocks.symbol, SUM(portfolios.shares_owned) as total_shares_owned, transactions.price as price
    FROM portfolios
    INNER JOIN stocks ON portfolios.stock_id = stocks.id
    INNER JOIN transactions ON portfolios.stock_id = transactions.stock_id AND portfolios.user_id = transactions.user_id
    GROUP BY stocks.symbol;
    ''').fetchall()
    symbols=[stock_info[0] for stock_info in market_report]
    shares_owned=[stock_info[1] for stock_info in market_report]
    if symbols==[]:
        return
    efficient_frontier,currentPositionInEF,pieFig = calculate_efficient_frontier(symbols,shares_owned)
    fig = create_efficient_frontier_chart(efficient_frontier,currentPositionInEF)
    ans={}
    ans['plot_div']=fig
    ans['pie_fig']=pieFig
    ans['optimal_portfolio']=efficient_frontier[-1]
    ans['current_portfolio']=currentPositionInEF
    # return render_template('efficient_frontier.html', plot_div=plot_div)
    return ans

def calculate_efficient_frontier(symbols,shares_owned):
    db = get_db()
    # risk-free rate （US Treasury 10 year bond yield）
    rf=0.036
    adj_close=[]
    for symbol in symbols:
        cursor = db.execute('SELECT date,close FROM stocks_price_data WHERE symbol = ?',(symbol,))
        close = pd.DataFrame(cursor.fetchall(),columns=['date',symbol]).set_index(['date'])
        adj_close.append(close)

    adj_close = pd.concat(adj_close,axis=1).sort_index(ascending=True)
    # Compute pairwise covariance of columns, excluding NA/null values.
    cov = adj_close.pct_change(fill_method=None).cov()*252 # Annual
    try:
        np.linalg.cholesky(cov)
    except:
        cov=pd.DataFrame(near_psd(cov.to_numpy(),np.eye(n)).psd,columns=cov.columns,index=cov.index)
    # Percentage change between the current and a prior element and fill NAN with NAN
    expected_rts = adj_close.pct_change(fill_method=None).mean()*252 # Annual
    n = expected_rts.shape[0]

    def calculate_portfolio_vol(weights):
        return np.sqrt(weights@cov@weights.T)
    
    
    bounds = [(0, 1) for i in range(n)]
    initial_weights = np.ones(n) / n
    efficient_frontier = []
    # min_rt=expected_rts.min()
    max_rt=expected_rts.max()

    # Current position in Efficient Frontier
    currentPositionInEF=[]
    # calculate the weight of current portfolio
    currentWeight=pd.DataFrame(shares_owned,index=expected_rts.index).T*(adj_close.fillna(method='ffill').iloc[-1,:])
    currentWeight=currentWeight/currentWeight.sum(axis=1)[0]
    currentRt=(currentWeight@expected_rts)[0]
    currentVol=calculate_portfolio_vol(currentWeight).iloc[0,0]
    SR=round((currentRt-rf)/currentVol,2)
    currentPositionInEF.append((currentRt,currentVol,SR))
    currentRt=str(round(currentRt*100,2))+'%'
    currentVol=str(round(currentVol*100,2))+'%'
    # current weights
    currW=currentWeight.T
    currW.columns=['weight']

    currentWeight=currentWeight.apply(lambda x: "{:.2f}%".format(x[0]*100))
    currentPositionInEF.append((currentRt,currentVol,SR,currentWeight))
    

    
    for target_return in np.linspace(0,max_rt, 50):
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1},{'type': 'eq', 'fun': lambda w: w@expected_rts - target_return}]
        result = minimize(
            calculate_portfolio_vol,
            initial_weights,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 1000},
            args=(),
        )
        # if not result.success:
        #     print(result)
        #     print('-----------------------------------')
        #     continue
        weights = result.x
        portfolio_return = weights@expected_rts
        portfolio_std_dev = calculate_portfolio_vol(weights)
        efficient_frontier.append((portfolio_return, portfolio_std_dev,(portfolio_return-rf)/portfolio_std_dev,weights))

    idx=pd.DataFrame(efficient_frontier).iloc[:,2].idxmax()
    maxSR_rt=str(round(efficient_frontier[idx][0]*100,2))+'%'
    maxSR_std=str(round(efficient_frontier[idx][1]*100,2))+'%'
    maxSR=round(efficient_frontier[idx][2],2)

    # optimal weight
    optW=pd.DataFrame(efficient_frontier[idx][3],index=expected_rts.index)
    optW.columns=['weight']

    maxSR_w=optW.T.apply(lambda x: "{:.2f}%".format(x[0]*100))
    efficient_frontier.append((maxSR_rt,maxSR_std,maxSR,maxSR_w))
    # pie chart
    pie_fig=weight_pie(optW,currW)
    
    # daily returns 
    rts=adj_close.pct_change(fill_method=None).fillna(0)
    return efficient_frontier,currentPositionInEF,pie_fig

def weight_pie(optWeight,currentWeight):
    pie_fig={}
    # Current
    fig=px.pie(currentWeight, values='weight',names=currentWeight.index,color_discrete_sequence=px.colors.sequential.Brwnyl)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",font=dict(  color="white"))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",font=dict(  color="white"),
        # margin=dict(l=0, r=0, t=0, b=0), # adjust the margins here
        # legend=dict(
        #     orientation='h', # set the orientation to horizontal
        #     yanchor='bottom', # set the anchor point to the bottom of the chart
        #     xanchor='center', # set the x anchor point to the right of the chart
        #     x=0.5 # set the x position to be inside the right margin
        # ),
        title={'text': 'Current Portfolio', 'x': 0.5,'font': {'size': 24}}
    )
    fig_div = f'<div class="pie">{fig.to_html(full_html=False)}</div>'
    pie_fig['currentFig']=fig_div

    # Optimal
    fig=px.pie(optWeight, values='weight',names=optWeight.index,color_discrete_sequence=px.colors.sequential.Brwnyl)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",font=dict(  color="white"),
        # margin=dict(l=0, r=0, t=0, b=0), # adjust the margins here
        # legend=dict(
        #     orientation='h', # set the orientation to horizontal
        #     yanchor='bottom', # set the anchor point to the bottom of the chart
        #     xanchor='center', # set the x anchor point to the right of the chart
        #     x=0.5 # set the x position to be inside the right margin
        # ),
        title={'text': 'Optimal Portfolio', 'x': 0.5,'font': {'size': 24}}
    )
    fig_div = f'<div class="pie">{fig.to_html(full_html=False)}</div>'
    pie_fig['optimalFig']=fig_div
    return pie_fig


def create_efficient_frontier_chart(efficient_frontier,currentPositionInEF):
    rf=0.025
    # optimal portfolio
    optVol=float(efficient_frontier[-1][1].split('%')[0])/100
    optRt=float(efficient_frontier[-1][0].split('%')[0])/100
    # current portfolio
    currVol=str(currentPositionInEF[0][1])+'%'
    currRt=str(currentPositionInEF[0][0])+'%'

    volRange=[p[1] for p in efficient_frontier[:-1]]
    rtRange=[p[0] for p in efficient_frontier[:-1]]
    maxVol = 1.05*max(volRange)
    minVol = 0.95*min(volRange)
    volCMLRange = np.linspace(minVol, maxVol,20)
    SR=(optRt-rf)/optVol
    rtCMLRange = rf+SR*volCMLRange

    fig = make_subplots(rows=1, cols=1, specs=[[{"type": "scatter"}]])
    fig.add_trace(
        go.Scatter(
            x=volRange,
            y=rtRange,
            mode='lines',
            name='Efficient Frontier'
        ),
        row=1,
        col=1
    )

    fig.add_trace(
        go.Scatter(
            x=volCMLRange,
            y=rtCMLRange,
            mode='lines',
            name='Captial Market Line'
        ),
        row=1,
        col=1
    )

    fig.add_trace(
        go.Scatter(
            x=[optVol],
            y=[ optRt ],
            mode='markers',
            name='Super Efficient Portfolio'
        ),
        row=1,
        col=1
    )

    fig.add_trace(
        go.Scatter(
            x=[currVol],
            y=[ currRt ],
            mode='markers',
            name='Current Portfolio'
        ),
        row=1,
        col=1
    )

    fig.update_layout(
        title='Efficient Frontier',
        xaxis_title='Risk (Standard Deviation)',
        yaxis_title='Return',
        autosize=True,
        title_x=0.5,
    )

    fig.update_layout(paper_bgcolor="rgba(244, 243, 243, 0.8)", plot_bgcolor="rgba(0,0,0,0)")

    return fig.to_html(full_html=False)



