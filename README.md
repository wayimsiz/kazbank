# KazBank Transaction API

Мини-проект по курсу CSCI2204 (Database Management Systems, KBTU).
REST API на Flask + PostgreSQL (psycopg3) с пулом соединений, транзакциями и обработкой ошибок.

## Стек
- Python 3.10+
- PostgreSQL 15+
- Flask, psycopg3, psycopg-pool, python-dotenv

## Структура
| Файл | Назначение |
|---|---|
| `setup.py` | Создаёт таблицы, заполняет данными, проверяет UNIQUE |
| `app.py` | Flask API, пул соединений, `/transfer`, `/health` |
| `load_test.py` | Нагрузочный тест (20 одновременных запросов) |
| `deadlock.sql` | Сценарий дедлока для двух сессий |
| `.env.example` | Пример настроек подключения (свой `.env` не публикуется) |

## Запуск

1. Создать виртуальное окружение и поставить библиотеки:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install "psycopg[binary]" psycopg-pool flask python-dotenv
   ```
2. Создать базу `kazbank` в PostgreSQL и файл `.env` рядом с `app.py`:
   ```
   DATABASE_URL=postgresql://postgres:ВАШ_ПАРОЛЬ@localhost:5432/kazbank
   ```
3. Создать таблицы и данные (3 таблицы, 10 клиентов, 15 счетов):
   ```bash
   python3 setup.py
   ```
   Скрипт также печатает версию PostgreSQL, `autocommit` (False) и проверяет UNIQUE на `account_number` повторной вставкой (`UNIQUE works`).
4. Запустить сервер:
   ```bash
   python3 app.py
   ```
   Сервер работает на `http://127.0.0.1:5001`. Порт 5001, потому что на macOS порт 5000 занят AirPlay.

## Эндпоинты

| Метод | Адрес | Описание |
|---|---|---|
| GET | `/customers` | Все клиенты. `?city=Almaty` фильтрует по городу |
| POST | `/customers` | Создать клиента (`full_name`, `email`, `city`) |
| GET | `/accounts?customer_id=n` | Счета клиента |
| POST | `/transactions` | Одна операция debit/credit (баланс не может стать отрицательным) |
| POST | `/transfer` | Перевод между счетами (атомарный, SERIALIZABLE) |
| GET | `/transactions?account_id=n` | Журнал операций счёта |
| GET | `/health` | Статус базы и статистика пула |

## Примеры curl

```bash
# Клиенты
curl "http://localhost:5001/customers"
curl "http://localhost:5001/customers?city=Almaty"

# Счета и журнал
curl "http://localhost:5001/accounts?customer_id=1"
curl "http://localhost:5001/transactions?account_id=1"

# Создать клиента -> 201
curl -X POST http://localhost:5001/customers \
  -H "Content-Type: application/json" \
  -d '{"full_name": "Test", "email": "t@mail.kz"}'

# Тот же запрос ещё раз -> 409 Already exists
curl -X POST http://localhost:5001/customers \
  -H "Content-Type: application/json" \
  -d '{"full_name": "Test", "email": "t@mail.kz"}'

# Без обязательного поля -> 400 Missing field: full_name
curl -X POST http://localhost:5001/customers \
  -H "Content-Type: application/json" \
  -d '{"email": "x@mail.kz"}'

# Успешный перевод -> 200
curl -X POST http://localhost:5001/transfer \
  -H "Content-Type: application/json" \
  -d '{"from": 1, "to": 2, "amount": 500}'

# Не хватает денег -> 400 Insufficient funds (в журнале появится запись failed)
curl -X POST http://localhost:5001/transfer \
  -H "Content-Type: application/json" \
  -d '{"from": 1, "to": 2, "amount": 99999999}'

# Состояние базы и пула
curl "http://localhost:5001/health"
```

## Коды ответов

| Код | Когда |
|---|---|
| 200 / 201 | Успех / создано |
| 400 | Пустое обязательное поле (NotNullViolation), неверные данные, не хватает денег |
| 404 | Счёт не найден |
| 409 | Дубликат (UniqueViolation) |
| 503 | База недоступна (OperationalError) |

## Что и где реализовано

- **Пул соединений.** `ConnectionPool(min_size=2, max_size=8, timeout=5)` создаётся один раз при старте приложения. Все запросы берут соединение через `with pool.connection()`, и оно возвращается в пул автоматически.
- **Транзакции.** Каждый блок `with pool.connection()` — это одна транзакция: COMMIT при успехе, ROLLBACK при ошибке.
- **Перевод (`/transfer`).**
  - Атомарный: списание, зачисление и записи в журнал происходят вместе или не происходят вообще.
  - Изоляция SERIALIZABLE, при `SerializationFailure` перевод повторяется до 3 раз.
  - SAVEPOINT (`with conn.transaction()`): при нехватке денег откатывается только списание, а запись `failed` в журнале сохраняется.
  - Счета блокируются всегда по возрастанию `account_id` (`FOR UPDATE`), поэтому дедлок невозможен.
- **Защита от SQL-инъекций.** Все запросы используют `%s` и передают значения отдельно от текста запроса.

## Почему SERIALIZABLE для перевода

Перевод сначала читает баланс, а потом меняет его. Если два перевода идут одновременно, они могут оба увидеть старый баланс и потратить одни и те же деньги дважды. SERIALIZABLE работает так, будто переводы выполняются по очереди. Если база обнаруживает конфликт, она выдаёт ошибку 40001 (`SerializationFailure`), и приложение повторяет перевод.

## Проверка SQL-инъекции

```bash
curl "http://localhost:5001/customers?city=x'%20OR%20'1'='1"
```
Ответ: `[]`. База воспринимает `x' OR '1'='1` как обычное название города, а не как SQL-код. Если бы запрос собирался склейкой строк, вернулись бы все клиенты.

Скриншот: _вставьте сюда_

## Дедлок

Сценарий в `deadlock.sql`. Две сессии (в pgAdmin Query Tool или psql) выполняют по очереди:

| Шаг | Сессия | Команда |
|---|---|---|
| 1 | A | `BEGIN; UPDATE accounts SET balance = balance + 1 WHERE account_id = 1;` |
| 2 | B | `BEGIN; UPDATE accounts SET balance = balance + 1 WHERE account_id = 2;` |
| 3 | A | `UPDATE accounts SET balance = balance + 1 WHERE account_id = 2;` (ждёт) |
| 4 | B | `UPDATE accounts SET balance = balance + 1 WHERE account_id = 1;` |

Одна из сессий получает ошибку (код 40P01):

```
ERROR:  deadlock detected
```
_Вставьте сюда полный текст ошибки из вашего экрана._

В обеих сессиях затем выполняется `ROLLBACK;`. В `/transfer` дедлок не возникает, потому что счета всегда блокируются в порядке возрастания `account_id`.

## Нагрузочный тест (пул соединений)

```bash
# сервер должен работать в другом терминале
python3 load_test.py
```
Тест отправляет 20 одновременных запросов и выводит статистику пула. Результат `/health` после тестов:

- `requests_num: 40`: соединение брали из пула 40 раз;
- `pool_size: 8`: открыто всего 8 соединений (не больше `max_size`);
- `requests_queued: 33`: часть запросов ждала освобождения соединения.

Запросов много, соединений мало, то есть пул переиспользует их, а не открывает новое на каждый запрос.
