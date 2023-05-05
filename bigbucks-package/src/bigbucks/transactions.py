import functools
import requests
from datetime import datetime
import json
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, jsonify
)
from .db import get_db
from bigbucks.auth import login_required
import yfinance as yf
import yahooquery as yq
import pandas as pd
import numpy as np
from scipy.optimize import minimize
import plotly.graph_objs as go
from plotly.subplots import make_subplots
import plotly.express as px



bp = Blueprint('transactions', __name__, url_prefix='/transactions')

'''
----------------------------------------------------------------------------------------
Transaction Part (Buy & Sell) 
----------------------------------------------------------------------------------------
'''
@bp.route('/main')
def main():
    stocks = get_transaction_history()
    return render_template('transactions/main.html',stocks=stocks)
   
def get_transaction_history():
    '''get transaction history data of our user to display in the table'''
    db = get_db()
    transactions_data = db.execute('SELECT stock_id, quantity, price, transaction_datetime, id, transaction_type, closing_date FROM transactions where user_id= ?',(g.user['id'],)).fetchall()
    stocks = []
    if transactions_data != None:
        for transaction in transactions_data:
            stocks_data = db.execute('SELECT shortName, symbol FROM stocks where id = ?', (transaction[0],)).fetchone()
            if stocks_data != None:
                stocks.append({
                    'stock_id': transaction[0],
                    'name': stocks_data[0],
                    'symbol': stocks_data[1],
                    'quantity': transaction[1],
                    'price': transaction[2],
                    'transaction_datetime': transaction[3],
                    'transaction_type': transaction[5],
                    'id': transaction[4],
                    'total_cost': transaction[1]*transaction[2],
                    'closing_date': transaction[6]
                })
    return stocks

@bp.route("/buy", methods=["POST"])
@login_required
def buy():
    if request.method == 'POST':
        stock_symbol = request.form['stock-symbol']
        date = check_date(request.form['date'])

        try:
            # Fetch the current data via yfinance package fastly
            fast_info = yf.Ticker(stock_symbol).fast_info
        except:
            flash(f"Error: could not find stock name for {stock_symbol}", 'error')
            return redirect(url_for("transactions.main"))

        # Add the stock to the watchList and stocks table
        try:
            fetch_info(stock_symbol)
        except:
            flash(f"Error: could not find stock name for {stock_symbol}", 'error')
            return redirect(url_for("transactions.main"))

        # Add the stock price to the stock_price_data table
        try:
            fetch_and_store_data(stock_symbol)
        except:
            flash(f"{stock_symbol}: No data found, symbol may be delisted", 'error')
            return redirect(url_for("transactions.main"))
    
        try:
            price = get_price(fast_info,stock_symbol, date)
        except:
            flash('Please Type a Date.', 'error')
            return redirect(url_for("transactions.main"))

        # Calculate the quantity
        amountUSD=request.form['amount']
        try:
            quantity = check_quantity(request.form['quantity']) if request.form['quantity']!='' else check_quantity(USD2Share(amountUSD,price))
        except:
            flash("Please enter a quantity greater than zero.", 'error')
            return redirect(url_for("transactions.main"))

        # Calculate the cost
        amount = float(quantity) * float(price)
            
        if not check_balance(amount):
            flash("Insufficient funds in account to complete purchase.", 'error')
            return redirect(url_for("transactions.main"))

        db = get_db()
        stock_id = db.execute('SELECT id from stocks WHERE symbol like ?', (stock_symbol,)).fetchone()[0]
        # Select quantity_owned data from the portfolios table
        quantity_prev_owned = get_quantity_owned(stock_id)
        # Insert into the transactions Table
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            "INSERT INTO transactions (user_id, stock_id, price, quantity, transaction_datetime, transaction_type, closing_date) VALUES (?, ?, ?, ?, ?, ?,?)",
            (g.user['id'], stock_id, price, quantity, now, "buy", date),
        )
        # Insert or Update balance table
        db.execute('UPDATE balance SET user_balance = user_balance - ?, user_portfolio_balance = user_portfolio_balance + ? WHERE user_id = ?', (amount,amount, g.user['id']))
        # Update the share_owned
        new_shares_owned = quantity_prev_owned + quantity
        update_portfolio_table(stock_id, new_shares_owned)
        db.commit()
        flash("Purchase completed successfully.", 'success') 
        return redirect(url_for("transactions.main"))

    return redirect(url_for("transactions.main"))

def get_price(fast_info, stock_symbol, date):
    if date > datetime.now().date():
        flash("You can't select a date from the future! Please select a different date.", 'error')
        raise Exception
    elif date == datetime.now().date():
        return fast_info['lastPrice']
    elif date != datetime.now().date():
        db = get_db()
        price = db.execute('SELECT close FROM stocks_price_data WHERE symbol = ? and date = ?', (stock_symbol.upper(), str(date),)).fetchone()
        if price == None:
            flash(f"Data was not found for {stock_symbol} Or Not a Trading Day", 'error')
            raise Exception
        else:
            return price[0]
         
def USD2Share(amountUSD,price):
    if amountUSD=='':
        flash("Please type a amount of USD or shares.", 'error')
        redirect(url_for("transactions.main"))
    try:
        quantity=float(amountUSD)//price
    except:
        flash('Please type a number of amount.', 'error')
        redirect(url_for("transactions.main"))
    return int(quantity)

    
@bp.route("/sell", methods=['POST','GET'])
@login_required
def sell():
    if request.method == 'POST':
        stock_symbol = request.form['stock-symbol']
        date = check_date(request.form['date'])
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        db = get_db()
        try:
            stock_id = db.execute('SELECT id from stocks WHERE symbol like ?', (stock_symbol,)).fetchone()[0]
        except:
            flash(f"{stock_symbol}: No data found, symbol may be delisted", 'error')
            return redirect(url_for("transactions.main"))

        # Fetch the current data via yfinance package fastly
        try:
            fast_info = yf.Ticker(stock_symbol).fast_info
        except:
            flash(f"Error: could not find stock name for {stock_symbol}", 'error')
            return redirect(url_for("transactions.main"))

        # Select the price given a date
        try:
            price= get_price(fast_info, stock_symbol, date)
        except:
            flash('Please Type a Date.', 'error')
            return redirect(url_for("transactions.main"))

        # Calculate the quantity
        amountUSD=request.form['amount']
        try:
            quantity = check_quantity(request.form['quantity']) if request.form['quantity']!='' else check_quantity(USD2Share(amountUSD,price))
        except:
            flash("Please enter a quantity greater than zero.", 'error')
            return redirect(url_for("transactions.main"))

        # Select quantity_owned data from the portfolios table
        quantity_owned = get_quantity_owned(stock_id)
        if quantity <= 0 or quantity > quantity_owned:
            flash(f"Please enter a quantity greater than zero and less than or equal to the number of shares you own for {stock_symbol}", 'error')
            return redirect(url_for("transactions.main"))
        
        # Calculat the new share held, new portfolio balance and amount of change
        new_shares_owned = quantity_owned - quantity
        new_user_portfolio_balance = new_shares_owned * price
        amount = quantity * price

        # Update the transactions table
        db.execute(
            "INSERT INTO transactions (user_id, stock_id, price, quantity, transaction_datetime, transaction_type, closing_date) VALUES (?, ?, ?, ?, ?, ?,?)",
            (g.user['id'], stock_id, price, quantity, now, "sell", date),
        )

        # Update the user balance
        db.execute('UPDATE balance SET user_balance = user_balance + ?,user_portfolio_balance =  ? WHERE user_id = ?', (amount,new_user_portfolio_balance, g.user['id']))

        # Update the portfolios table with the new quantity of shares owned.
        if new_shares_owned==0:
            # if the new_shares_owned is 0, then just delete the record in portfolios table
            db.execute('DELETE FROM portfolios WHERE user_id = ? AND stock_id = ?', (g.user['id'], stock_id))
        else:
            update_portfolio_table(stock_id, new_shares_owned) 
        db.commit()
        flash("Sell completed successfully.", 'success') 
        return redirect(url_for("transactions.main"))
    return redirect(url_for("transactions.main"))
    
'''
----------------------------------------------------------------------------------------
Boundary Checks
----------------------------------------------------------------------------------------
'''
    
def check_quantity(data):
    quantity = int(data)
    if quantity <= 0:
        raise ValueError
    return quantity

def check_date(data):
    try:
        date = datetime.strptime(data,'%Y-%m-%d').date()
        if date > datetime.now().date():
            flash("You can't select a date from the future! Please select a different date.", 'error')
            raise Exception
        return date
    except (Exception):
        redirect(url_for("transactions.main"))
        
def check_balance(data):
    db = get_db()
    balance = db.execute('SELECT user_balance from balance WHERE user_id = ?', (g.user['id'],)).fetchone()
    if float(balance[0]) - data >= 0:
        return True
    else:
        return False


'''
----------------------------------------------------------------------------------------
Portfolio Part (Tract the position of each asset) 
----------------------------------------------------------------------------------------
'''

@bp.route("/view_portfolio")
@login_required
def view_portfolio():
    stocks = get_user_portfolio()
    data=efficient_frontier()
    PortfolioBalance = round(get_user_portfolio_balance(),2)
    return render_template('transactions/portfolio.html',stocks=stocks,data=data,PortfolioBalance=PortfolioBalance)
    
def get_user_portfolio():
    db = get_db()
    all_stocks= db.execute('SELECT DISTINCT stock_id, shares_owned FROM portfolios where user_id= ?',(g.user['id'],)).fetchall()
    stocks = []
    if all_stocks != None:
        for stock in all_stocks:
            stock_data = db.execute('SELECT shortName, symbol FROM stocks where id = ?', (stock[0],)).fetchone()
            if stock_data != None:
                #print(f"{stock_data[0]} from portfolios quantity owned {stock[1]}")
                stocks.append({
                    'stock_id': stock[0],
                    'name': stock_data[0],
                    'symbol': stock_data[1],
                    'shares_owned': get_quantity_owned(stock[0]),
                })
    return stocks
    
def fetch_info(symbol):
    '''Fetch the infomation about the symbol via yfinace and yahooquery package'''
    db = get_db()
    info1 = yf.Ticker(symbol).info
    info2 = yq.Ticker(symbol).asset_profile
    try:
        symbolName=info1['symbol']
        shortName=info1['shortName']
        # displayName=info1['displayName']
        # exchange=info1['exchange']
        # currency=info1['currency']
        sector= info2[symbol]['sector']  if ('sector' in info2[symbol]) else "---"
        longBusinessSummary=info2[symbol]['longBusinessSummary'] if 'longBusinessSummary' in info2[symbol] else "---"
    except:
        raise ValueError(f"Error: could not find stock name for {symbol}")
    # Insert the stocks info to the stocks
    db.execute('INSERT OR IGNORE INTO stocks (symbol, shortName, sector, longBusinessSummary) VALUES (?, ?, ?, ?)', (symbolName, shortName,sector,longBusinessSummary))
    # add the stock to the watchList
    db.execute('INSERT OR IGNORE INTO watchList (user_id, symbol) VALUES (?, ?)', (g.user['id'], symbolName))
    db.commit()


def fetch_and_store_data(symbol):
    '''Fetch the 5 years historical stock data of symbol and store it in the database'''
    db = get_db()
    # Fetch the historical stock data for the symbol
    ticker=yf.Ticker(symbol)
    data = ticker.history(period='5y', interval="1d")
    data.dropna(inplace=True)
    symbol=ticker.info['symbol']
    try:
        data.index=data.index.date
    except:
        raise ValueError("No data found, symbol may be delisted")
    def store_data(dailyData):
        db.execute('INSERT OR IGNORE INTO stocks_price_data (symbol, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)', (
            symbol, str(dailyData.name), float(dailyData['Open']), float(dailyData['High']), float(dailyData['Low']),
            float(dailyData['Close']), dailyData['Volume']
        ))
    data.apply(store_data,axis=1)
    db.commit()

def get_quantity_owned(stock_id):
    db = get_db()
    quantity_owned = db.execute('SELECT shares_owned from portfolios WHERE stock_id = ? and user_id = ?', (stock_id,g.user['id'],)).fetchone()
    if quantity_owned == None:
        return 0
    else:
        return quantity_owned[0]
      
def update_portfolio_table(stock_id, new_shares_owned):
    # Update the portfolios table with the new quantity of shares owned.
    db = get_db()
    db.execute('INSERT INTO portfolios (user_id, stock_id, shares_owned) VALUES (?, ?, ?) ON CONFLICT (user_id, stock_id) DO UPDATE SET shares_owned = ?', (g.user['id'], stock_id, new_shares_owned, new_shares_owned))
    db.commit()          

'''
----------------------------------------------------------------------------------------
Efficient Frontier Part (Help user to figure their highest Sharpe ratio portfolio) 
----------------------------------------------------------------------------------------
'''
@bp.route('/efficient_frontier')
@login_required
def efficient_frontier():
    db=get_db()
    all_stocks= db.execute('SELECT DISTINCT stock_id,shares_owned FROM portfolios where user_id= ?',(g.user['id'],)).fetchall()
    symbols = []
    shares_owned=[]
    for stock in all_stocks:
        symbol = db.execute('SELECT symbol FROM stocks where id = ?', (stock[0],)).fetchone()
        symbols.append(symbol[0])
        shares_owned.append(stock[1])
    if symbols==[]:
        return
    efficient_frontier,currentPositionInEF,pieFig,pg_fig,pat_fig = calculate_efficient_frontier(symbols,shares_owned)
    fig = create_efficient_frontier_chart(efficient_frontier,currentPositionInEF)
    ans={}
    ans['plot_div']=fig
    ans['pie_fig']=pieFig
    ans['portfolio_growth_fig']=pg_fig
    ans['portfolio_annual_return_fig']=pat_fig
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
    # Portfolio Growth
    pg_fig=portfolioGrowth(optW,currW,rts)
    # Portfolio Annual Return
    pat_fig=annualReturns(optW,currW,rts)
    return efficient_frontier,currentPositionInEF,pie_fig,pg_fig,pat_fig

def portfolioGrowth(optWeight,currentWeight,rts):
    # initial Portfolio Value
    initialValue=1000000
    # Stocks' Cumulative Growth
    stockGrowth=(rts+1).cumprod()*initialValue
    # Optimal Portfolio Growth
    optGrowth=(stockGrowth*optWeight.T.to_numpy()).sum(axis=1)
    # Current Portfolio Growth
    currGrowth=(stockGrowth*currentWeight.T.to_numpy()).sum(axis=1)
    # Put them together
    pGrowth=pd.concat([optGrowth,currGrowth],axis=1)
    pGrowth.columns=['OptimalGrowth','CurrentGrowth']
    pGrowth.index=pd.to_datetime(pGrowth.index)
    # plot
    fig = px.line(pGrowth)
    fig.update_layout(
        title='Portfolio Gowth',
        xaxis_title='Date',
        yaxis_title='Portfolio Balance',
        autosize=True,
        title_x=0.5,
        paper_bgcolor="rgba(244, 243, 243, 0.8)", 
        plot_bgcolor="rgba(0,0,0,0)"
    )
    growth=fig.to_html(full_html=False)
    return growth

def annualReturns(optWeight,currentWeight,rts):
    # Returns plus 1
    rtsP1=(rts+1)
    rtsP1.index=pd.to_datetime(rtsP1.index)
    # Calculate the Annual returns of each stock
    yearlyReturns=rtsP1.resample('Y').apply(lambda x: x.product())
    # Adjust the weight of each stocks yearly -- Optimal Weight
    newOptW=yearlyReturns.cumprod()*optWeight.T.to_numpy()
    newOptW=newOptW.div(newOptW.sum(axis=1),axis=0)
    # Adjust the weight of each stocks yearly -- Current Weight
    newCurrW=yearlyReturns.cumprod()*currentWeight.T.to_numpy()
    newCurrW=newCurrW.div(newCurrW.sum(axis=1),axis=0)
    # Calculate the each year's portfolio return
    optAnnualReturn=(newOptW*yearlyReturns).sum(axis=1)
    currAnnualReturn=(newCurrW*yearlyReturns).sum(axis=1)
    # put them together
    annualReturn=pd.concat([optAnnualReturn,currAnnualReturn],axis=1)-1
    annualReturn.columns=['OptimalAnnualRt','CurrentAnnualRt']
    # plot the bar chart
    fig = px.bar(annualReturn,barmode='group')
    fig.update_layout(
        title='Annual Returns',
        xaxis_title='Date',
        yaxis_title='Annual Return',
        yaxis=dict(tickformat='.2%'),
        autosize=True,
        title_x=0.5,
        paper_bgcolor="rgba(244, 243, 243, 0.8)", 
        plot_bgcolor="rgba(0,0,0,0)"
    )
    annualReturn=fig.to_html(full_html=False)
    return annualReturn



def weight_pie(optWeight,currentWeight):
    pie_fig={}
    # Current
    fig=px.pie(currentWeight, values='weight',names=currentWeight.index,color_discrete_sequence=px.colors.sequential.Brwnyl)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",font=dict(  color="white"))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",font=dict(  color="white"),
        # margin=dict(l=0, r=0, t=0, b=0), # adjust the margins here
        legend=dict(
            orientation='h', # set the orientation to horizontal
            yanchor='bottom', # set the anchor point to the bottom of the chart
            xanchor='center', # set the x anchor point to the right of the chart
            x=0.5 # set the x position to be inside the right margin
        ),
        title={'text': 'Current Portfolio', 'x': 0.5,'font': {'size': 24}}
    )
    fig_div = f'<div class="pie">{fig.to_html(full_html=False)}</div>'
    pie_fig['currentFig']=fig_div

    # Optimal
    fig=px.pie(optWeight, values='weight',names=optWeight.index,color_discrete_sequence=px.colors.sequential.Brwnyl)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",font=dict(  color="white"),
        # margin=dict(l=0, r=0, t=0, b=0), # adjust the margins here
        legend=dict(
            orientation='h', # set the orientation to horizontal
            yanchor='bottom', # set the anchor point to the bottom of the chart
            xanchor='center', # set the x anchor point to the right of the chart
            x=0.5 # set the x position to be inside the right margin
        ),
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




'''
----------------------------------------------------------------------------------------
Non-Positive Definite Matrix Fix Method (Rebonato and Jackel's Method)
----------------------------------------------------------------------------------------
'''

class Weighted_F_norm:
    '''
    Given the weight matrix, calculate the Weighted Frobenius Norm. (Assume it's diagonal)
    '''
    def compare_F(self,mat_a,mat_b,mat_w):
        '''Give two matrix, use Weighted Frobenius Norm to calculate how close they are'''
        err = mat_a-mat_b #difference
        weighted_err = np.sqrt(mat_w) @ err @ np.sqrt(mat_w) 
        w_F_norm = np.sqrt(np.square(weighted_err).sum())
        return w_F_norm
    
    def calculate_F(self,mat,mat_w):
        "Given one matrix, calculate its Weighted Frobenius Norm"
        weighted_err = np.sqrt(mat_w) @ mat @ np.sqrt(mat_w)
        w_F_norm = np.sqrt(np.square(weighted_err).sum())
        return w_F_norm

class near_psd(Weighted_F_norm):
    '''
    Rebonato and Jackel's Method to get acceptable PSD matrix 
    
    Parameters:
        not_psd -- the matrix which is not positive semi-definite matrix
        weight  -- used for calculating the Weighted Frobenius Norm (Assume it's diagonal)

    Usage:
        near_psd_model=near_psd(non_psd,weight)
        psd=near_psd_model.psd
    '''
    # initialization
    def __init__(self,not_psd,weight):
        self.__not_psd=not_psd
        self.__weight=weight
        self.run() # main function
        self.F_compare_norm(weight) # Weighted Frobenius Norm
        
    def run(self):
        n=self.__not_psd.shape[0]
        # Set the weight matrix to be identity matrix
        invSD = np.eye(n)
        corr=self.__not_psd
        # if the matrix is not correlation matrix, convert it to the correlation matrix
        if not np.allclose(np.diag(self.__not_psd),np.ones(n)):
            invSD=np.diag(1/np.sqrt(np.diag(self.__not_psd)))
            corr=invSD @ self.__not_psd @ invSD
        eig_val,eig_vec=np.linalg.eigh(corr) # eigenvalues & eigenvectors 
        eig_val[eig_val<0]=0 # adjust the negative value to 0
        # get the scale matrix
        scale_mat = np.diag(1/(eig_vec * eig_vec @ eig_val))
        B = np.sqrt(scale_mat) @ eig_vec @ np.sqrt(np.diag(eig_val))
        corr=B @ B.T
        # convert it back into original form
        SD=np.diag(1/np.diag(invSD))
        psd = SD @ corr @ SD
        self.__psd = psd

    # Weighted Frobenius Norm of the difference between near_psd and ono_psd
    def F_compare_norm(self,weight):
        self.__F = self.compare_F(self.__psd,self.__not_psd,weight)

    @property
    def psd(self):
        return self.__psd
    
    @property
    def F(self):
        return self.__F 


'''
----------------------------------------------------------------------------------------
Portfolio Balance
----------------------------------------------------------------------------------------
'''

def get_user_portfolio_balance():
    db = get_db()
    all_stocks= db.execute('SELECT DISTINCT stock_id FROM portfolios where user_id= ?',(g.user['id'],)).fetchall()
    stocks = []
    portfolioBalance=0
    if all_stocks != None:
        for stock in all_stocks:
            stock_data = db.execute('SELECT shortName, symbol FROM stocks where id = ?', (stock[0],)).fetchone()
            if stock_data != None:
                stocks.append({
                    'stock_id': stock[0],
                    'name': stock_data[0],
                    'symbol': stock_data[1],
                    'shares_owned': get_quantity_owned(stock[0]),
                })
        for stock in stocks:
            fast_info = yf.Ticker(stock['symbol']).fast_info
            price=round(fast_info['lastPrice'],2) if fast_info['lastPrice']!=None else 0
            portfolioBalance+=stock['shares_owned']*price
    else: 
        return portfolioBalance 
    return portfolioBalance