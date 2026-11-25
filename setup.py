import os, psycopg
from dotenv import load_dotenv

load_dotenv()
url = os.environ["DATABASE_URL"]

DDL = """
DROP TABLE IF EXISTS transactions, accounts, customers CASCADE;
CREATE TABLE customers (
    customer_id SERIAL PRIMARY KEY,
    full_name   TEXT NOT NULL,
    city        TEXT DEFAULT 'Almaty',
    email       TEXT UNIQUE
);
CREATE TABLE accounts (
    account_id     SERIAL PRIMARY KEY,
    customer_id    INTEGER REFERENCES customers(customer_id),
    account_number TEXT UNIQUE NOT NULL,
    balance        NUMERIC(15,2) DEFAULT 0 CHECK (balance >= 0)
);
CREATE TABLE transactions (
    tx_id      SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(account_id),
    amount     NUMERIC(15,2) NOT NULL,
    tx_type    TEXT NOT NULL CHECK (tx_type IN ('debit','credit','failed')),
    created_at TIMESTAMP DEFAULT now()
);
"""

names = ["Arman Bekov", "Zarina Seiit", "Daniyar Nurlan", "Aigerim Sadykova",
         "Timur Kassym", "Madina Oral", "Nurlan Abay", "Dana Yessen",
         "Askar Omar", "Aliya Tolegen"]
cities = ["Almaty", "Astana", "Shymkent"]

customers = [(n, cities[i % 3], f"user{i+1}@mail.kz") for i, n in enumerate(names)]
accounts = [(i % 10 + 1, f"KZ{1000+i}", 100000) for i in range(15)]

with psycopg.connect(url) as conn:
    # Step 1
    print(conn.execute("SELECT version()").fetchone()[0])
    print("autocommit =", conn.autocommit)          # False

    # Step 2
    conn.execute(DDL)
    cur = conn.cursor()
    cur = conn.cursor()
    cur.executemany("INSERT INTO customers (full_name, city, email) VALUES (%s,%s,%s)", customers)
    cur.executemany("INSERT INTO accounts (customer_id, account_number, balance) VALUES (%s,%s,%s)", accounts)
    conn.commit()

    # UNIQUE check: this must fail
    try:
        conn.execute("INSERT INTO accounts (customer_id, account_number) VALUES (1, 'KZ1000')")
    except psycopg.errors.UniqueViolation:
        print("UNIQUE works: duplicate account_number rejected")
        conn.rollback()
