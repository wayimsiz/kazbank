# KazBank API
```
pip install "psycopg[binary]" psycopg-pool flask python-dotenv
python setup.py      # create tables + seed data
python app.py        # run API on :5000
```
Sample curl:
```
curl localhost:5000/customers
curl "localhost:5000/customers?city=Almaty"
curl -X POST localhost:5000/customers -d '{"full_name":"Test","email":"t@mail.kz"}'
curl -X POST localhost:5000/customers -d '{"full_name":"Test","email":"t@mail.kz"}'   # 409
curl -X POST localhost:5000/customers -d '{"email":"x@mail.kz"}'                      # 400
curl "localhost:5000/accounts?customer_id=1"
curl -X POST localhost:5000/transfer -d '{"from":1,"to":2,"amount":500}'
curl -X POST localhost:5000/transfer -d '{"from":1,"to":2,"amount":99999999}'         # 400
curl "localhost:5000/transactions?account_id=1"
curl localhost:5000/health
# SQL injection test (returns [], nothing is broken):
curl "localhost:5000/customers?city=x'%20OR%20'1'='1"
```
