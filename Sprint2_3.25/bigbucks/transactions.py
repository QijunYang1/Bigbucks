import functools
import requests
from datetime import datetime
import json
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, jsonify
)
from .db import get_db
from bigbucks.auth import login_required

bp = Blueprint('transactions', __name__, url_prefix='/transactions')

@bp.route('/main')
def main():
    stocks = get_transaction_history()
    return render_template('transactions/main.html',stocks=stocks)
    
def get_transaction_history():
    db = get_db()
    transactions_data = db.execute('SELECT stock_id, quantity, price, transaction_datetime, id, transaction_type FROM transactions where user_id= ?',(g.user['id'],)).fetchall()
    stocks = []
    for transaction in transactions_data:
        stocks_data = db.execute('SELECT name, symbol FROM stocks where id = ?', (transaction[0],)).fetchone()
        stocks.append({
            'stock_id': transaction[0],
            'name': stocks_data[0],
            'symbol': stocks_data[1],
            'quantity': transaction[1],
            'price': transaction[2],
            'transaction_datetime': transaction[3],
            'transaction_type': transaction[5],
            'id': transaction[4]
        })
    return stocks
   
     
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
    print(f"symbol {symbol}")
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey=YIGLFVRLKZZN8OV0"
    response = requests.get(url)

    if response.ok:
        data = response.json()
        if 'Global Quote' in data and '05. price' in data['Global Quote']:
            return float(data['Global Quote']['05. price'])
       # else:
        #    return "Stock price not available at the moment."
    else:
        raise f"Error: could not get stock price for {symbol}"
    
@bp.route("/buy", methods=["POST"])
@login_required
def buy():
    if request.method == 'POST':
        stock_symbol = request.form['stock-symbol']
        quantity = int(request.form['quantity'])
        if float(quantity) >= 0:
            price = get_stock_price(stock_symbol)
            add_stock(stock_symbol)
            amount = float(quantity) * float(price)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db = get_db()
            stock_id = db.execute('SELECT id from stocks WHERE symbol like ?', (stock_symbol,)).fetchone()
            db.execute(
                        "INSERT INTO transactions (user_id, stock_id, price, quantity, transaction_datetime, transaction_type) VALUES (?, ?, ?, ?, ?, ?)",
                        (g.user['id'], stock_id[0], price, quantity, now, "buy"),
                    )
            if check_balance(amount):
                db.execute('UPDATE balance SET user_balance = user_balance - ? WHERE user_id = ?', (amount, g.user['id']))
                db.commit()
                return "Purchase completed successfully."
            else:
                return "Insufficient funds in account to complete purchase."
        else:
            return "Please enter a quantity greater than zero."
        db.commit()
    return redirect(url_for("transactions.main"))
    
def check_balance(data):
    db = get_db()
    balance = db.execute('SELECT user_balance from balance WHERE user_id = ?', (g.user['id'],)).fetchone()
    if float(balance[0]) - data >= 0:
        return True
    else:
        return False
    
@bp.route("/sell", methods=['POST','GET'])
@login_required
def sell():
    if request.method == 'GET':
        db = get_db()
        transactions = db.execute('SELECT stock_id, quantity FROM transactions WHERE user_id = ? GROUP BY stock_id',(g.user['id'],)).fetchall()
        return jsonify(format_json(transactions[0][1]))
    if request.method == 'POST':
        stock_symbol = request.form['stock-symbol']
        quantity = int(request.form['quantity'])
        db = get_db()
        stock_id = db.execute('SELECT id from stocks WHERE symbol like ?', (stock_symbol,)).fetchone()[0]
        quantity_owned = get_quantity_owned(stock_id)
        if quantity <= 0 or quantity > quantity_owned:
            return f"Please enter a quantity greater than zero and less than or equal to the number of shares you own for {stock_symbol}"
        transactions= db.execute('SELECT stock_id, quantity, price, id FROM transactions WHERE stock_id = ? GROUP BY stock_id ORDER BY price asc',(stock_id,)).fetchall()
        amount = 0
        index = 0
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        price = float(get_stock_price(stock_symbol))
        amount += quantity * price
        db.execute(
                "INSERT INTO transactions (user_id, stock_id, price, quantity, transaction_datetime, transaction_type) VALUES (?, ?, ?, ?, ?, ?)",
                (g.user['id'], stock_id, price, quantity, now, "sell"),
        )
        db.execute('UPDATE balance SET user_balance = user_balance + ? WHERE user_id = ?', (amount, g.user['id']))
        db.commit()
    return redirect(url_for("transactions.main"))
    
def format_json(data):
    message = {'message': str(data)}
    return message
    
def add_stock(symbol):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stock_name = get_stock_name(symbol)
    db = get_db()
    db.execute('INSERT INTO stocks (name, symbol,  datetime_added) SELECT ?, ?, ?  WHERE NOT EXISTS (SELECT * from stocks WHERE symbol like ?) ', (stock_name, symbol,  now, symbol))
    db.commit()

def check_quantity(current, previous):
    if current > previous:
        return False
    else:
        return True
        
@bp.route("/view_portfolio")
@login_required
def view_portfolio():
    stocks = get_user_portfolio()
    return render_template('transactions/portfolio.html',stocks=stocks)
    
def get_user_portfolio():
    db = get_db()
    all_stocks= db.execute('SELECT DISTINCT stock_id, shares_owned FROM portfolios where user_id= ?',(g.user['id'],)).fetchall()
    stocks = []
    for stock in all_stocks:
        stock_data = db.execute('SELECT name, symbol FROM stocks where id = ?', (stock[0],)).fetchone()
        stocks.append({
            'stock_id': stock[0],
            'name': stock_data[0],
            'symbol': stock_data[1],
            'shares_owned': stock[1]),
        })
    return stocks
    
def get_quantity_purchased(db, stock_id):
    bought = db.execute('SELECT SUM(quantity) FROM transactions where user_id= ? and stock_id = ? and transaction_type like ? GROUP BY stock_id',(g.user['id'], stock_id,"buy",)).fetchone()
    if bought != None:
        return float(bought[0])
    else:
        return 0
def get_quantity_sold(db, stock_id):
     sold =  db.execute('SELECT SUM(quantity) FROM transactions where user_id= ? and stock_id = ? and transaction_type like ? GROUP BY stock_id',(g.user['id'], stock_id,"sell",)).fetchone()
     if sold != None:
        return float(sold[0])
     else:
        return 0

def get_quantity_owned(stock_id):
      db = get_db()
      bought = get_quantity_purchased(db, stock_id)
      sold = get_quantity_sold(db, stock_id)
      return bought - sold
    