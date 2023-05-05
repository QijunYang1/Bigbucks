import sqlite3

import click
from flask import current_app, g
import yfinance as yf
import yahooquery as yq
import pandas as pd

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row

    return g.db


def close_db(e=None):
    db = g.pop('db', None)

    if db is not None:
        db.close()


@click.command('init-db')
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo('Initialized the database.')
    fetch_and_store_data('SPY')
    click.echo('Get the info and data of S&P 500.')

def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)


def init_db():
    db = get_db()

    with current_app.open_resource('schema.sql') as f:
        db.executescript(f.read().decode('utf8'))

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