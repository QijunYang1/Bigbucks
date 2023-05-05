-- Initialize the database.
-- Drop any existing data and create empty tables.

DROP TABLE IF EXISTS balance;
DROP TABLE IF EXISTS stocks;
DROP TABLE IF EXISTS user;
DROP TAbLE IF EXISTS transactions;
DROP TAbLE IF EXISTS watchList;
DROP TAbLE IF EXISTS portfolios;
DROP TAbLE IF EXISTS stocks_price_data;

CREATE TABLE user (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL,
  role TEXT DEFAULT 'user'
);

CREATE TABLE stocks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL UNIQUE,
  shortName TEXT NOT NULL,
  sector TEXT NOT NULL,
  longBusinessSummary TEXT NOT NULL
);

CREATE TABLE watchList (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  symbol TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES user(id)
  FOREIGN KEY(symbol) REFERENCES stocks(symbol)
  UNIQUE(user_id, symbol)
);

CREATE TABLE balance (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  user_balance DECIMAL NOT NULL,
  user_portfolio_balance DECIMAL NOT NULL,
  FOREIGN KEY(user_id) REFERENCES user(id)
);

CREATE TABLE transactions(
	id INTEGER PRIMARY KEY AUTOINCREMENT,
	user_id INTEGER NOT NULL,
	stock_id INTEGER NOT NULL,
	price DECIMAL NOT NULL,
	quantity INTEGER NOT NULL,
	transaction_datetime TIMESTAMP NOT NULL,
	closing_date DATE NOT NULL,
	transaction_type TEXT NOT NULL,
	FOREIGN KEY(user_id) REFERENCES user(id),
	FOREIGN KEY(stock_id) REFERENCES stocks(id)
);

CREATE TABLE portfolios (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  stock_id INTEGER NOT NULL,
  shares_owned INTEGER NOT NULL CHECK (shares_owned >= 0),
  FOREIGN KEY(user_id) REFERENCES user(id),
  FOREIGN KEY(stock_id) REFERENCES stocks(id),
  UNIQUE(user_id, stock_id)
);

CREATE TABLE stocks_price_data (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    PRIMARY KEY (symbol, date)
);
