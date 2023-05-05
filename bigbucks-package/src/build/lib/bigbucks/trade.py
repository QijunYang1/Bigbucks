from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from werkzeug.exceptions import abort
from bigbucks.auth import login_required
from bigbucks.db import get_db
import requests
from datetime import datetime
import yfinance as yf
import yahooquery as yq
import pandas as pd
import numpy as np
from bigbucks.db import *
import plotly.graph_objs as go
from plotly.subplots import make_subplots
import plotly.express as px


bp = Blueprint("stock", __name__)


'''
----------------------------------------------------------------------------------------
Main Part (Cash in & Cash out & Watch List) 
----------------------------------------------------------------------------------------
'''
@bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    db = get_db()
    if request.method == 'POST':
        cursor = db.execute('SELECT user_balance FROM balance WHERE user_id = ?', (g.user['id'],))
        user_balance = cursor.fetchall()[0][0]
        print(g.user['id'], user_balance)

        # Add Cash
        if 'action' in request.form and request.form['action'] == 'add_cash':
            amount = request.form['amount']
            
            try:
                amount = float(amount)
                if amount <= 0:
                    raise ValueError
                user_balance += amount
                db.execute('UPDATE balance SET user_balance = ? WHERE user_id = ?', (user_balance, g.user['id']))
                db.commit()
                user_balance = round(user_balance, 2)
                flash('Cash added successfully.', 'success')
            except (ValueError, TypeError):
                flash('Incorrect amount.', 'error')
                return redirect(url_for('stock.index'))
            user_balance = round(user_balance, 2)
            return redirect(url_for('stock.index'))
        # Cash Out
        elif 'action' in request.form and request.form['action'] == 'cash_out':
            amount = request.form['amount']
            try:
                amount = float(amount)
                if amount <= 0 or amount == "":
                    flash('Incorrect amount.', 'error')
                if user_balance >= amount:
                    user_balance -= amount
                    db.execute('UPDATE balance SET user_balance = ? WHERE user_id = ?', (user_balance, g.user['id']))
                    db.commit()
                    user_balance = round(user_balance, 2)
                    flash('Cash out successful.', 'success')
                else:
                    flash('Insufficient funds.', 'error')
            except (ValueError, TypeError):
                flash('Incorrect amount.', 'error')

            return redirect(url_for('stock.index'))
        # Update the stock price info
        else:
            symbol = request.form['symbol']
            if symbol.strip() == "":
                flash('Stock symbol cannot be empty.', 'error')
                return redirect(url_for('stock.index'))

            try:
                fetch_info(symbol)
            except:
                flash(f"Error: could not find stock name for {symbol}", 'error')

            try:
                fetch_and_store_data(symbol)
            except:
                flash(f"{symbol}: No data found, symbol may be delisted", 'error')

            return redirect(url_for('stock.index'))

    else:
        # Construct Watch List
        db = get_db()
        rows = db.execute('SELECT * FROM watchList WHERE user_id = ?',(g.user['id'],)).fetchall()
        stocks = []
        symbols=[]
        for row in rows:
            id = row['id']
            symbol = row['symbol']
            symbols.append(symbol)

            # Fetch the current data via yfinance package fastly
            fast_info = yf.Ticker(symbol).fast_info
            price=round(fast_info['lastPrice'],2) if fast_info['lastPrice']!=None else 0
            dayHigh=round(fast_info['dayHigh'],2) if fast_info['dayHigh']!=None else 0
            dayLow=round(fast_info['dayLow'],2) if fast_info['dayLow']!=None else 0
            Volume='---' if (fast_info['lastVolume']==None or fast_info['lastVolume']==0) else (str(round(fast_info['lastVolume']/1000000,2))+' M' if fast_info['lastVolume']/1000000>1 else (str(round(fast_info['lastVolume']/1000,2))+' K' if fast_info['lastVolume']/1000>1 else str(round(fast_info['lastVolume'],2))))

            try:
                marketCap=str(round(fast_info['marketCap']/1000000000,2)) + ' B' if fast_info['marketCap']/1000000000>1 else (str(round(fast_info['marketCap']/1000000,2)) + ' M') if fast_info['marketCap']/1000000 >1 else str(round(fast_info['marketCap']/1000,2)) + ' K'
            except:
                marketCap='---'

            # Fetch stock information from the stocks table
            db = get_db()
            stcok_info = db.execute('SELECT * FROM stocks WHERE symbol = ?',(symbol,)).fetchone()

            # datetime_added = row['datetime_added']
            stocks.append({
                'id':id,
                'symbol': symbol,
                'shortName': stcok_info['shortName'],
                # 'displayName': stcok_info['displayName'],
                # 'exchange': stcok_info['exchange'],
                # 'currency': stcok_info['currency'],
                'sector': stcok_info['sector'],
                'current_price': price,
                'dayHigh': dayHigh,
                'dayLow': dayLow,
                'Volume': Volume,
                'marketCap': marketCap
                # 'name': stcok_info['name'],
                # 'current_price': price,
                # 'datetime_added': datetime_added
            })
        
        # update the balance of user
        db = get_db()
        cursor = db.execute('SELECT user_balance,user_portfolio_balance FROM balance WHERE user_id = ?', (g.user['id'],))
        row = cursor.fetchone()
        if row:
            user_balance = round(row[0],2)
            user_portfolio_balance = round(row[1],2)
        else:
            user_balance = 1000000.0
            user_portfolio_balance=0
            db.execute('INSERT OR REPLACE INTO balance (user_id, user_balance,user_portfolio_balance) VALUES (?, ?, ?)', (g.user['id'], user_balance,0))
            db.commit()
        # Plot the Price
        Price_dashboard,Price_dashboard_relative=PriceDashboard(symbols)
        # Get the User Portfolio Balance
        PortfolioBalance=round(get_user_portfolio_balance(),2)

        return render_template('index.html', stocks=stocks, user={'balance': user_balance,'portfolio_balance':user_portfolio_balance},Price_dashboard=Price_dashboard,Price_dashboard_relative=Price_dashboard_relative,PortfolioBalance=PortfolioBalance)


'''
----------------------------------------------------------------------------------------
Helper function to store the info and price data of stocks
----------------------------------------------------------------------------------------
'''
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

'''
----------------------------------------------------------------------------------------
Specific Route for Cash in, Cash out and delete the element of Watch List
----------------------------------------------------------------------------------------
'''
@bp.route("/<int:id>/delete", methods=["POST"])
@login_required
def delete(id):
    db = get_db()
    db.execute('DELETE FROM watchList WHERE id = ?', (id,))
    db.commit()
    return redirect(url_for('stock.index'))

@bp.route("/<int:id>/add_cash", methods=['POST'])
@login_required
def add_cash(id):
    amount = request.form['amount']
    db = get_db()
    db.execute('UPDATE balance SET user_balance = user_balance + ? WHERE user_id = ?', (amount, id))
    db.commit()
    return redirect(url_for('stock.index'))

@bp.route("/<int:id>/cash_out", methods=['POST'])
@login_required
def cash_out(id):
    amount = request.form['amount']
    if not amount:
        flash('Incorrect amount.', 'error')
        return redirect(url_for('stock.index'))

    db = get_db()
    cursor = db.execute('SELECT user_balance FROM balance WHERE user_id = ?', (id,))
    user_balance = cursor.fetchone()[0]

    try:
        amount = float(amount)
        if amount <= 0 or amount == "":
            flash('Incorrect amount.', 'error')
        elif user_balance >= amount:
            user_balance -= amount
            db.execute('UPDATE balance SET user_balance = ? WHERE user_id = ?', (user_balance, id))
            db.commit()
            user_balance = round(user_balance, 2)
            flash('Cash out successful.', 'success')
        else:
            flash('Insufficient funds.', 'error')
    except (ValueError, TypeError):
        flash('Incorrect amount.', 'error')

    return redirect(url_for('stock.index', id=id))


'''
----------------------------------------------------------------------------------------
More infomation about a specific stock
----------------------------------------------------------------------------------------
'''

@bp.route('/info/<ssymbol>')
def plot_stock(ssymbol):
    db=get_db()
    symbols = ['SPY', ssymbol]
    query = "SELECT symbol, date, close FROM stocks_price_data WHERE symbol IN ({seq})".format(seq=','.join(['?']*len(symbols)))
    data=db.execute(query,symbols).fetchall()
    df=pd.DataFrame(data,columns=['symbol','date','close'])
    df.set_index('date',inplace=True)
    data=[]
    for symbol in symbols:
        temp=df.query("symbol==@symbol")['close']
        temp.name=symbol
        data.append(temp)
    df=pd.concat(data,axis=1)
    df.sort_index(ascending=True,inplace=True)
    rts=df.apply(lambda price: price.pct_change().fillna(0))
    rts.columns=[symbol+'_rt' for symbol in symbols]
    cum_rts=(rts+1).cumprod()
    cum_rts.columns=[symbol+'_cum_rt' for symbol in symbols]
    df=pd.concat([df,rts,cum_rts],axis=1)
    df['pre_rt']=df[ symbols[1]+'_rt' ].shift().fillna(0)
    df['date']=df.index

    completeData=db.execute("SELECT * FROM stocks_price_data WHERE symbol = '{}'".format(ssymbol)).fetchall()
    completeDf=pd.DataFrame(completeData,columns=['symbol','date','open','high','low','close','volume'])


    # Plot the price
    fig = go.Figure(data=[go.Candlestick(x=completeDf['date'],
                open=completeDf['open'],
                high=completeDf['high'],
                low=completeDf['low'],
                close=completeDf['close'])])
    fig.update_layout(
        title='Historical Candlestick of {}'.format(ssymbol),
        xaxis_title='Date',
        yaxis_title='Price',
        autosize=True,
        title_x=0.5,
    )
    fig.update_xaxes(
    rangeslider_visible=True,
    rangeselector=dict(
        buttons=list([
            dict(count=1, label="1m", step="month", stepmode="backward"),
            dict(count=6, label="6m", step="month", stepmode="backward"),
            dict(count=1, label="YTD", step="year", stepmode="todate"),
            dict(count=1, label="1y", step="year", stepmode="backward"),
            dict(step="all")
            ])
        )
    )
    fig.update_layout(paper_bgcolor="rgba(244, 243, 243, 0.8)", plot_bgcolor="rgba(0,0,0,0)")
    PlotPrice=fig.to_html(full_html=False)

    # Plot ssymbol Vs. S&P500
    fig = px.line(df, x='date', y=symbols,
                hover_data={"date": "|%B %d, %Y"},
                title='custom tick labels with ticklabelmode="period"')
    fig.update_layout(
        title=ssymbol+' Vs. S&P 500',
        xaxis_title='Date',
        yaxis_title='Price',
        autosize=True,
        title_x=0.5,
    )
    fig.update_xaxes(
    rangeslider_visible=True,
    rangeselector=dict(
        buttons=list([
            dict(count=1, label="1m", step="month", stepmode="backward"),
            dict(count=6, label="6m", step="month", stepmode="backward"),
            dict(count=1, label="YTD", step="year", stepmode="todate"),
            dict(count=1, label="1y", step="year", stepmode="backward"),
            dict(step="all")
            ])
        )
    )
    fig.update_layout(paper_bgcolor="rgba(244, 243, 243, 0.8)", plot_bgcolor="rgba(0,0,0,0)")
    stockVSindex=fig.to_html(full_html=False)

    # Plot ssymbol Vs. S&P 500 Cumulative Reutrns
    fig = px.line(df, x='date', y=cum_rts.columns,
                hover_data={"date": "|%B %d, %Y"},
                title='custom tick labels with ticklabelmode="period"')
    fig.update_layout(
        title=ssymbol+' Vs. S&P 500 (Cumulative Reutrns)',
        xaxis_title='Date',
        yaxis_title='Relative Price',
        autosize=True,
        title_x=0.5,
    )
    fig.update_xaxes(
    rangeslider_visible=True,
    rangeselector=dict(
        buttons=list([
            dict(count=1, label="1m", step="month", stepmode="backward"),
            dict(count=6, label="6m", step="month", stepmode="backward"),
            dict(count=1, label="YTD", step="year", stepmode="todate"),
            dict(count=1, label="1y", step="year", stepmode="backward"),
            dict(step="all")
            ])
        )
    )
    fig.update_layout(paper_bgcolor="rgba(244, 243, 243, 0.8)", plot_bgcolor="rgba(0,0,0,0)")
    cumReturn=fig.to_html(full_html=False)


    # Plot the daily simply return
    fig = px.scatter(df, x='date', y=symbols[1]+'_rt')
    fig.update_layout(
        title='Daily Simply Return of {}'.format(ssymbol),
        xaxis_title='Date',
        yaxis_title='Return',
        autosize=True,
        title_x=0.5,
    )
    fig.update_layout(paper_bgcolor="rgba(244, 243, 243, 0.8)", plot_bgcolor="rgba(0,0,0,0)")
    PlotReturn=fig.to_html(full_html=False)


    # Plot the Today's return vs. Yesterday's return
    fig = px.scatter(df, x='pre_rt', y=symbols[1]+'_rt')
    fig.update_layout(
        title="Today's return vs. Yesterday's return ({})".format(ssymbol),
        xaxis_title='Date',
        yaxis_title='Return',
        autosize=True,
        title_x=0.5,
    )
    fig.update_layout(paper_bgcolor="rgba(244, 243, 243, 0.8)", plot_bgcolor="rgba(0,0,0,0)")
    todayVsyestoday=fig.to_html(full_html=False)

    # Plot the histogram of daily returns
    fig = px.histogram(df, x=symbols[1]+'_rt')
    fig.update_layout(
        title="{}'s Histogram of Daily Returns ".format(ssymbol),
        xaxis_title='Return',
        yaxis_title='Count',
        autosize=True,
        title_x=0.5,
    )
    fig.update_layout(paper_bgcolor="rgba(244, 243, 243, 0.8)", plot_bgcolor="rgba(0,0,0,0)")
    hist_rt=fig.to_html(full_html=False)


    # Plot the stock's return vs. S&P500's return over time
    fig = px.line(df, x='date', y=rts.columns)
    fig.update_layout(
        title="{}'s return vs. S&P 500's return over time".format(ssymbol),
        xaxis_title='Date',
        yaxis_title='Return',
        autosize=True,
        title_x=0.5,
    )
    fig.update_xaxes(
    rangeslider_visible=True,
    rangeselector=dict(
        buttons=list([
            dict(count=1, label="1m", step="month", stepmode="backward"),
            dict(count=6, label="6m", step="month", stepmode="backward"),
            dict(count=1, label="YTD", step="year", stepmode="todate"),
            dict(count=1, label="1y", step="year", stepmode="backward"),
            dict(step="all")
            ])
        )
    )
    fig.update_layout(paper_bgcolor="rgba(244, 243, 243, 0.8)", plot_bgcolor="rgba(0,0,0,0)")
    stockVSindex_rt_overtime=fig.to_html(full_html=False)


    # Plot the stock's return vs. S&P500's return
    fig = px.scatter(df, x=symbols[0]+'_rt', y=symbols[1]+'_rt',trendline="ols",trendline_color_override="red")
    fig.update_layout(
        title="{}'s return vs. S&P 500's return ".format(ssymbol),
        xaxis_title='Date',
        yaxis_title='Return',
        autosize=True,
        title_x=0.5,
    )
    fig.update_layout(paper_bgcolor="rgba(244, 243, 243, 0.8)", plot_bgcolor="rgba(0,0,0,0)")
    stockVSindex_rt=fig.to_html(full_html=False)
    results = px.get_trendline_results(fig)
    OLS_params=results.px_fit_results.iloc[0].params
    OLS_params[0]*=252*100 # Annual Alpha
    OLS_params=[str(round(i,2)) for i in OLS_params]+[str(round(results.px_fit_results.iloc[0].rsquared*100,2))]

    return render_template('stock_plot.html', symbol=ssymbol,PlotPrice=PlotPrice,PlotReturn=PlotReturn,stockVSindex=stockVSindex,todayVsyestoday=todayVsyestoday,stockVSindex_rt=stockVSindex_rt,hist_rt=hist_rt,OLS_params=OLS_params,cumReturn=cumReturn,stockVSindex_rt_overtime=stockVSindex_rt_overtime)

'''
----------------------------------------------------------------------------------------
Dashboard of Stock Price
----------------------------------------------------------------------------------------
'''
def PriceDashboard(symbols):
    if symbols==[]:
        return "Please Add Some Stocks to the Watch List.","Please Add Some Stocks to the Watch List."
    db=get_db()
    query = "SELECT symbol, date, close FROM stocks_price_data WHERE symbol IN ({seq})".format(seq=','.join(['?']*len(symbols)))
    data=db.execute(query,symbols).fetchall()
    df=pd.DataFrame(data,columns=['symbol','date','close'])
    df.set_index('date',inplace=True)
    data=[]
    for symbol in symbols:
        temp=df.query("symbol==@symbol")['close']
        temp.name=symbol
        data.append(temp)
    df=pd.concat(data,axis=1)
    df.sort_index(ascending=True,inplace=True)
    df.columns.name='Company'
    df_relative=(df.pct_change(fill_method=None).fillna(0)+1).cumprod()

    # Plot the price
    if df.shape[1]>8:
        df=df.iloc[:,:8]
    height=400*df.shape[1] if df.shape[1]<2 else 200*df.shape[1]
    # fig = px.area(df, facet_col="Company", facet_col_wrap=2)
    fig = px.area(df, facet_col="Company", facet_col_wrap=2,height=height)
    fig.update_layout(paper_bgcolor="rgba(244, 243, 243, 0.8)", plot_bgcolor="rgba(0,0,0,0)")
    Price_dashboard=fig.to_html(full_html=False)

    rows=int(np.ceil(df.shape[1]/2))
    fig = make_subplots(rows, 2)
    for i in range(1, df.shape[1]+1):
        row=int(np.ceil(i/2))
        column=2 if i%2==0 else 1
        fig.add_trace(go.Scatter(x=df_relative.index, y=df_relative.iloc[:,i-1].values,name=df.iloc[:,i-1].name), row, column)
        # fig.update_layout(title_text=df.iloc[:,i-1].name)
        fig.update_layout(title_text=df.iloc[:,i-1].name,height=height)
        
    fig.update_xaxes(matches='x')
    fig.update_layout(title_text="Relative Price")
    fig.add_hline(y=1, line_dash="dot",
            annotation_text="Start Point",
            annotation_position="bottom right")
    fig.update_layout(paper_bgcolor="rgba(244, 243, 243, 0.8)", plot_bgcolor="rgba(0,0,0,0)")
    Price_dashboard_relative = fig.to_html(full_html=False)

    return Price_dashboard,Price_dashboard_relative


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

    return portfolioBalance


def get_quantity_owned(stock_id):
    db = get_db()
    quantity_owned = db.execute('SELECT shares_owned from portfolios WHERE stock_id like ? and user_id = ?', (stock_id,g.user['id'],)).fetchone()
    if quantity_owned == None:
        return 0
    else:
        return quantity_owned[0]