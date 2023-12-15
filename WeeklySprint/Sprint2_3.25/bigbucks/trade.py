from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from werkzeug.exceptions import abort
from bigbucks.auth import login_required
from bigbucks.db import get_db
import requests
from datetime import datetime
import yfinance as yf
import yahooquery as yq
import pandas as pd
from bigbucks.db import *

bp = Blueprint("stock", __name__)

@bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    db = get_db()
    if request.method == 'POST':
        cursor = db.execute('SELECT user_balance FROM balance WHERE user_id = ?', (g.user['id'],))
        user_balance = cursor.fetchall()[0][0]
        print(g.user['id'], user_balance)
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
                flash('Cash added successfully.')
            except (ValueError, TypeError):
                flash('Incorrect amount.')
                return redirect(url_for('stock.index'))
            user_balance = round(user_balance, 2)
            return render_template('index.html', user={'balance': user_balance})
        elif 'action' in request.form and request.form['action'] == 'cash_out':
            amount = request.form['amount']
            try:
                amount = float(amount)
                if amount <= 0 or amount == "":
                    flash('Incorrect amount.')
                if user_balance >= amount:
                    user_balance -= amount
                    db.execute('UPDATE balance SET user_balance = ? WHERE user_id = ?', (user_balance, g.user['id']))
                    db.commit()
                    user_balance = round(user_balance, 2)
                    flash('Cash out successful.')
                else:
                    flash('Insufficient funds.')
            except (ValueError, TypeError):
                flash('Incorrect amount.')
            return render_template('index.html', user={'balance': user_balance})


        else:
            symbol = request.form['symbol']
            if symbol.strip() == "":
                flash('Stock symbol cannot be empty.')
                return redirect(url_for('stock.index'))
            # now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # print(now)
            # stock_name = get_stock_name(symbol)
            # db = get_db()
            # db.execute('INSERT INTO stocks (name, symbol,  datetime_added) VALUES (?, ?, ?)', (stock_name, symbol,  now))
            # db.commit()

            try:
                fetch_info(symbol)
            except:
                flash(f"Error: could not find stock name for {symbol}")

            try:
                fetch_and_store_data(symbol)
            except:
                flash(f"{symbol}: No data found, symbol may be delisted")

            return redirect(url_for('stock.index'))

    else:
        db = get_db()
        cursor = db.execute('SELECT * FROM watchList')
        rows = cursor.fetchall()
        stocks = []
        for row in rows:
            id = row['id']
            symbol = row['symbol']

            # Fetch the current data via yfinance package fastly
            fast_info = yf.Ticker(symbol).fast_info
            price=round(fast_info['lastPrice'],2)
            dayHigh=round(fast_info['dayHigh'],2)
            dayLow=round(fast_info['dayLow'],2)
            Volume=str(round(fast_info['lastVolume']/1000000,2)) # million
            marketCap=str(round(fast_info['marketCap']/1000000000,2)) # billion

            # datetime_added = row['datetime_added']
            stocks.append({
                'id':id,
                'symbol': symbol,
                'shortName': row['shortName'],
                'displayName': row['displayName'],
                'exchange': row['exchange'],
                'currency': row['currency'],
                'sector': row['sector'],
                'current_price': price,
                'dayHigh': dayHigh,
                'dayLow': dayLow,
                'Volume': Volume,
                'marketCap': marketCap
                # 'name': row['name'],
                # 'current_price': price,
                # 'datetime_added': datetime_added
            })
        
        # update the balance of user
        db = get_db()
        cursor = db.execute('SELECT user_balance FROM balance WHERE user_id = ?', (g.user['id'],))
        row = cursor.fetchone()
        if row:
            user_balance = row[0]
        else:
            user_balance = 1000000.0
            db.execute('INSERT OR REPLACE INTO balance (user_id, user_balance) VALUES (?, ?)', (g.user['id'], user_balance))
            db.commit()

        return render_template('index.html', stocks=stocks, user={'balance': user_balance})


def fetch_info(symbol):
    '''Fetch the infomation about the symbol via yfinace and yahooquery package'''
    db = get_db()
    info1 = yf.Ticker(symbol).info
    info2 = yq.Ticker(symbol).asset_profile
    try:
        symbolName=info1['symbol']
        shortName=info1['shortName']
        displayName=info1['displayName']
        exchange=info1['exchange']
        currency=info1['currency']
        sector=info2[symbol]['sector']
        longBusinessSummary=info2[symbol]['longBusinessSummary']
    except:
        raise ValueError(f"Error: could not find stock name for {symbol}")
    db.execute('INSERT OR IGNORE INTO watchList (symbol, shortName,  displayName, exchange, currency, sector, longBusinessSummary) VALUES (?, ?, ?, ?, ?, ?, ?)', (symbolName, shortName,  displayName,exchange,currency,sector,longBusinessSummary))
    db.commit()


def fetch_and_store_data(symbol):
    '''Fetch the 5 years historical stock data of symbol and store it in the database'''
    db = get_db()
    # Fetch the historical stock data for the symbol
    ticker=yf.Ticker(symbol)
    data = ticker.history(period='5y', interval="1d")
    data.dropna(inplace=True)
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



@bp.route("/<int:id>/delete", methods=["POST"])
@login_required
def delete(id):
    db = get_db()
    db.execute('DELETE FROM stocks WHERE id = ?', (id,))
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
        flash('Incorrect amount.')
        return redirect(url_for('stock.index'))

    db = get_db()
    cursor = db.execute('SELECT user_balance FROM balance WHERE user_id = ?', (id,))
    user_balance = cursor.fetchone()[0]

    try:
        amount = float(amount)
        if amount <= 0 or amount == "":
            flash('Incorrect amount.')
        elif user_balance >= amount:
            user_balance -= amount
            db.execute('UPDATE balance SET user_balance = ? WHERE user_id = ?', (user_balance, id))
            db.commit()
            user_balance = round(user_balance, 2)
            flash('Cash out successful.')
        else:
            flash('Insufficient funds.')
    except (ValueError, TypeError):
        flash('Incorrect amount.')

    return redirect(url_for('stock.index', id=id))
    






def get_stock_name(symbol):
    url = f"https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords={symbol}&apikey=YIGLFVRLKZZN8OV0"
    response = requests.get(url)
    if response.ok:
        data = response.json()
        if 'bestMatches' in data:
            for stock in data['bestMatches']:
                if symbol.casefold() == stock['1. symbol'].casefold():
                    return str(stock['2. name'])
                else:
                    raise ValueError(f"Error: could not find stock name for {symbol}")
        else:
            raise ValueError(f"Error: could not find stock for {symbol}")
    else:
        raise ValueError(f"Error: could not get stock for {symbol}")
        
def get_stock_price(symbol):
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey=YIGLFVRLKZZN8OV0"
    response = requests.get(url)

    if response.ok:
        data = response.json()
        if 'Global Quote' in data:
            stock_price = data['Global Quote']['05. price']
            return float(stock_price)
        else:
            return "Stock price not available at the moment."
    else:
        raise f"Error: could not get stock price for {symbol}"

