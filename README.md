# Finance Tracker

REST API для учёта личных финансов: пользователи, категории, транзакции и
аналитика с прогнозом бюджета на следующий месяц.

**Автор:** Nikolay Butrin

## Стек

- Python 3.11+
- FastAPI
- SQLAlchemy 2.0 (ORM)
- Pydantic v2 (валидация)
- SQLite (хранилище)
- python-jose + passlib[bcrypt] (JWT + хэши паролей)
- pytest + httpx (тесты)

## Возможности

- Регистрация и JWT-авторизация (OAuth2 password flow)
- CRUD категорий (изолированы по пользователю)
- CRUD транзакций с типами `income` / `expense`
- Аналитика: средние расходы, тренд (растёт/падает/стабильно) и рекомендованный
  бюджет на следующий месяц по алгоритму взвешенного скользящего среднего

## Структура проекта

```
finance-tracker/
├── main.py                   # сборка FastAPI-приложения
├── database.py               # engine, Base, get_db
├── models.py                 # SQLAlchemy-модели
├── schemas.py                # Pydantic-схемы
├── crud.py                   # CRUD-функции для категорий и транзакций
├── auth.py                   # регистрация, логин, JWT
├── routers_categories.py     # /categories/*
├── routers_transactions.py   # /transactions/*
├── routers_analytics.py      # /analytics/budget-plan
├── tests/
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_categories.py
│   ├── test_transactions.py
│   └── test_analytics.py
├── requirements.txt
└── README.md
```

## Установка и запуск

```bash
# 1. Клонировать репозиторий
git clone <repo-url>
cd finance-tracker

# 2. Создать и активировать виртуальное окружение
python -m venv venv
# Windows
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Инициализировать БД (создаёт finance.db и таблицы)
python -c "from database import init_db; init_db()"

# 5. Запустить сервер
uvicorn main:app --reload
```

Сервер поднимется на `http://127.0.0.1:8000`. Интерактивная документация
Swagger UI доступна по адресу `http://127.0.0.1:8000/docs`.

## Тесты

```bash
pytest
```

Тесты используют отдельную in-memory SQLite, реальная `finance.db` не
затрагивается.

## Структура БД

### `users`
| Поле          | Тип          | Описание                  |
|---------------|--------------|---------------------------|
| id            | INTEGER PK   | Идентификатор             |
| username      | VARCHAR(50)  | Уникальный логин          |
| email         | VARCHAR(120) | Уникальный email          |
| password_hash | VARCHAR(128) | bcrypt-хэш пароля         |
| created_at    | DATETIME     | Время регистрации         |

### `categories`
| Поле    | Тип          | Описание                   |
|---------|--------------|----------------------------|
| id      | INTEGER PK   | Идентификатор              |
| name    | VARCHAR(100) | Название                   |
| user_id | INTEGER FK   | Владелец → `users.id`      |

### `transactions`
| Поле        | Тип           | Описание                             |
|-------------|---------------|--------------------------------------|
| id          | INTEGER PK    | Идентификатор                        |
| amount      | NUMERIC(10,2) | Сумма (> 0)                          |
| description | VARCHAR(255)  | Комментарий, может быть NULL         |
| type        | VARCHAR(7)    | `income` / `expense`                 |
| created_at  | DATETIME      | Время создания                       |
| user_id     | INTEGER FK    | Владелец → `users.id`                |
| category_id | INTEGER FK    | Категория → `categories.id`          |

### Связи

```
users (1) ──< (N) categories
users (1) ──< (N) transactions
categories (1) ──< (N) transactions
```

## Примеры запросов

Базовый URL: `http://127.0.0.1:8000`

### 1. Регистрация

```bash
curl -X POST http://127.0.0.1:8000/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "email": "alice@example.com",
    "password": "password123"
  }'
```

Ответ `201 Created`:
```json
{
  "id": 1,
  "username": "alice",
  "email": "alice@example.com",
  "created_at": "2026-04-12T10:00:00"
}
```

### 2. Логин (получение JWT)

```bash
curl -X POST http://127.0.0.1:8000/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=alice&password=password123"
```

Ответ `200 OK`:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

Дальше во всех запросах используй заголовок:
```
Authorization: Bearer <access_token>
```

### 3. Создать категорию

```bash
curl -X POST http://127.0.0.1:8000/categories \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Food"}'
```

### 4. Список категорий

```bash
curl http://127.0.0.1:8000/categories \
  -H "Authorization: Bearer $TOKEN"
```

### 5. Обновить / удалить категорию

```bash
curl -X PATCH http://127.0.0.1:8000/categories/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Groceries"}'

curl -X DELETE http://127.0.0.1:8000/categories/1 \
  -H "Authorization: Bearer $TOKEN"
```

### 6. Создать транзакцию

```bash
curl -X POST http://127.0.0.1:8000/transactions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "42.50",
    "description": "lunch",
    "type": "expense",
    "category_id": 1
  }'
```

Ответ `201 Created`:
```json
{
  "id": 1,
  "amount": "42.50",
  "description": "lunch",
  "type": "expense",
  "created_at": "2026-04-12T10:15:00",
  "user_id": 1,
  "category_id": 1
}
```

### 7. Список транзакций

```bash
curl http://127.0.0.1:8000/transactions \
  -H "Authorization: Bearer $TOKEN"
```

### 8. План бюджета на следующий месяц

```bash
curl "http://127.0.0.1:8000/analytics/budget-plan?months=3&transaction_type=expense" \
  -H "Authorization: Bearer $TOKEN"
```

Query-параметры:
- `months` — сколько последних месяцев анализировать (2–12, по умолчанию `3`)
- `transaction_type` — `expense` или `income` (по умолчанию `expense`)

Ответ:
```json
{
  "months_analyzed": 3,
  "period_start": "2026-02-01",
  "period_end": "2026-04-12",
  "transaction_type": "expense",
  "total_suggested_budget": "233.33",
  "categories": [
    {
      "category_id": 1,
      "category_name": "Food",
      "monthly_totals": ["100.00", "200.00", "300.00"],
      "average": "200.00",
      "trend": "rising",
      "trend_pct": 100.0,
      "suggested_budget": "233.33"
    }
  ]
}
```

### Алгоритм расчёта бюджета

- **Среднее** — простое арифметическое по месячным тоталам.
- **Тренд** — сравнение среднего второй половины окна с первой:
  `|Δ| < 5%` → `stable`, иначе `rising` / `falling`.
- **Рекомендуемый бюджет** — взвешенное скользящее среднее с линейными
  весами `[1, 2, ..., N]` (свежие месяцы важнее):

  ```
  suggested = Σ(totalᵢ · (i+1)) / Σ(i+1)
  ```

## Безопасность

- Пароли хранятся как bcrypt-хэши.
- JWT подписывается `HS256`, срок жизни — 60 минут.
- `SECRET_KEY` в `auth.py` — заглушка. В продакшне вынеси в переменную
  окружения и читай из неё.
- Все пользовательские ресурсы (категории, транзакции) изолированы по
  `user_id` — пользователь не видит и не может модифицировать чужие данные.

## Лицензия

MIT
