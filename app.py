import os, time
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from psycopg import errors, OperationalError
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

load_dotenv()
app = Flask(__name__)

# the pool is created ONCE, when the app starts
pool = ConnectionPool(os.environ["DATABASE_URL"], min_size=2, max_size=8,
                      timeout=5.0, kwargs={"row_factory": dict_row}, open=True)


def read(sql, args=()):
    with pool.connection() as conn:
        return conn.execute(sql, args).fetchall()


# ---------- error -> HTTP code ----------
@app.errorhandler(errors.UniqueViolation)
def e409(e): return jsonify(error="Already exists"), 409

@app.errorhandler(errors.NotNullViolation)
def e400(e): return jsonify(error=f"Missing field: {e.diag.column_name}"), 400

@app.errorhandler(errors.CheckViolation)
def e400b(e): return jsonify(error="Balance cannot be negative"), 400

@app.errorhandler(errors.ForeignKeyViolation)
def e400c(e): return jsonify(error="Related row does not exist"), 400

@app.errorhandler(OperationalError)
def e503(e): return jsonify(error="Database unavailable"), 503


# ---------- customers ----------
@app.get("/customers")
def list_customers():
    city = request.args.get("city")
    if city:
        rows = read("SELECT * FROM customers WHERE city = %s ORDER BY customer_id", (city,))
    else:
        rows = read("SELECT * FROM customers ORDER BY customer_id")
    return jsonify(rows)


@app.post("/customers")
def create_customer():
    d = request.get_json(force=True)
    with pool.connection() as conn:          # COMMIT on success, ROLLBACK on error
        row = conn.execute(
            "INSERT INTO customers (full_name, city, email) VALUES (%s,%s,%s) RETURNING customer_id",
            (d.get("full_name"), d.get("city", "Almaty"), d.get("email"))).fetchone()
    return jsonify(customer_id=row["customer_id"]), 201


# ---------- accounts / transactions ----------
@app.get("/accounts")
def list_accounts():
    return jsonify(read("SELECT * FROM accounts WHERE customer_id = %s ORDER BY account_id",
                        (request.args.get("customer_id", type=int),)))


@app.get("/transactions")
def list_transactions():
    return jsonify(read("SELECT * FROM transactions WHERE account_id = %s ORDER BY tx_id",
                        (request.args.get("account_id", type=int),)))


@app.post("/transactions")                    # one debit or credit
def add_transaction():
    d = request.get_json(force=True)
    if d.get("tx_type") not in ("debit", "credit") or not d.get("amount", 0) > 0:
        return jsonify(error="tx_type must be debit/credit, amount > 0"), 400
    sign = 1 if d["tx_type"] == "credit" else -1
    with pool.connection() as conn:
        # CHECK (balance >= 0) rejects an overdraft -> CheckViolation -> 400
        cur = conn.execute("UPDATE accounts SET balance = balance + %s WHERE account_id = %s",
                           (sign * d["amount"], d.get("account_id")))
        if cur.rowcount == 0:
            return jsonify(error="Account not found"), 404
        conn.execute("INSERT INTO transactions (account_id, amount, tx_type) VALUES (%s,%s,%s)",
                     (d["account_id"], d["amount"], d["tx_type"]))
    return jsonify(status="ok"), 201


# ---------- transfer ----------
def with_retry(fn, tries=3):
    for i in range(tries):
        try:
            return fn()
        except errors.SerializationFailure:
            if i == tries - 1:
                raise
            time.sleep(0.05 * (i + 1))


def do_transfer(src, dst, amount):
    with pool.connection() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        # lock both accounts, ALWAYS lowest id first -> no deadlock
        locked = conn.execute("SELECT 1 FROM accounts WHERE account_id IN (%s,%s) "
                              "ORDER BY account_id FOR UPDATE", (src, dst)).fetchall()
        if len(locked) < 2:
            return {"error": "Account not found"}, 404
        try:
            with conn.transaction():          # = SAVEPOINT
                conn.execute("UPDATE accounts SET balance = balance - %s WHERE account_id = %s", (amount, src))
                conn.execute("UPDATE accounts SET balance = balance + %s WHERE account_id = %s", (amount, dst))
                conn.execute("INSERT INTO transactions (account_id, amount, tx_type) VALUES (%s,%s,'debit')", (src, amount))
                conn.execute("INSERT INTO transactions (account_id, amount, tx_type) VALUES (%s,%s,'credit')", (dst, amount))
        except errors.CheckViolation:
            # only the savepoint part was undone; we can still log the failure and commit
            conn.execute("INSERT INTO transactions (account_id, amount, tx_type) VALUES (%s,%s,'failed')", (src, amount))
            return {"error": "Insufficient funds"}, 400
    return {"status": "ok"}, 200


@app.post("/transfer")
def transfer():
    d = request.get_json(force=True)
    src, dst, amount = d.get("from"), d.get("to"), d.get("amount", 0)
    if src == dst or not amount > 0:
        return jsonify(error="Need different accounts and amount > 0"), 400
    body, code = with_retry(lambda: do_transfer(src, dst, amount))
    return jsonify(body), code


# ---------- health ----------
@app.get("/health")
def health():
    try:
        pool.check()
        return jsonify(status="ok", pool=pool.get_stats())
    except Exception as e:
        return jsonify(status="error", detail=str(e)), 503


if __name__ == "__main__":
    app.run(port=5001)
    