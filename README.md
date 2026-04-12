# Finance Tracker

REST API для учёта личных финансов: регистрация пользователей, категории,
транзакции и аналитика (прогноз бюджета, фильтрация/сортировка транзакций,
детекция аномальных расходов).

## Содержание

- [Возможности](#возможности)
- [Стек](#стек)
- [Структура проекта](#структура-проекта)
- [Установка и запуск](#установка-и-запуск)
- [Тесты](#тесты)
- [Структура БД](#структура-бд)
- [Формат ошибок](#формат-ошибок)
- [Эндпоинты](#эндпоинты)
- [Примеры запросов](#примеры-запросов)
- [Автор](#автор)

## Возможности

- Регистрация и JWT-авторизация (OAuth2 password flow, bcrypt для паролей)
- CRUD категорий (изолированы по пользователю)
- CRUD транзакций с типами `income` / `expense`
- Прогноз бюджета на следующий месяц (взвешенное скользящее среднее)
- Фильтрация и сортировка транзакций по дате, категории, типу и сумме
- Детекция аномальных расходов (`total > mean + 2·σ`)
- Единый формат ошибок для 401 / 404 / 422 и пр.
- Swagger UI из коробки по адресу `/docs`

## Стек

- Python 3.11+
- FastAPI
- SQLAlchemy 2.0 (ORM)
- Pydantic v2
- SQLite
- python-jose[cryptography] + passlib[bcrypt] (JWT + хэши паролей)
- pytest + httpx (тесты через `TestClient`)

## Структура проекта

```
finance-tracker/
├── main.py                   # сборка FastAPI-приложения и глобальные error handlers
├── database.py               # engine, Base, get_db, init_db
├── models.py                 # SQLAlchemy-модели
├── schemas.py                # Pydantic-схемы
├── crud.py                   # CRUD-функции для категорий и транзакций
├── auth.py                   # регистрация, логин, JWT, get_current_user
├── routers_categories.py     # /categories/*
├── routers_transactions.py   # /transactions/*
├── routers_analytics.py      # /analytics/budget-plan, /analytics/transactions, /analytics/anomalies
├── tests/
│   ├── conftest.py           # фикстуры: отдельная тестовая SQLite + TestClient
│   ├── test_auth.py
│   ├── test_categories.py
│   ├── test_transactions.py
│   ├── test_analytics.py
│   ├── test_analytics_extra.py
│   └── test_errors.py
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

# 4. Инициализировать БД (создаёт finance.db и все таблицы)
python -c "from database import init_db; init_db()"

# 5. Запустить сервер разработки
uvicorn main:app --reload
```

После запуска:

- API: <http://127.0.0.1:8000>
- Swagger UI: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>

### Переменные окружения

`SECRET_KEY` для подписи JWT в `auth.py` сейчас задан как заглушка. В проде
обязательно вынеси его в переменную окружения и читай оттуда.

## Тесты

Тесты используют **отдельную in-memory SQLite** (подмена `get_db` через
`app.dependency_overrides`), реальная `finance.db` не затрагивается.

```bash
# Запустить все тесты
pytest

# С отчётом о покрытии
pip install pytest-cov
pytest --cov=. --cov-report=term-missing
```

Состав тестов:

| Файл | Что покрывает |
|---|---|
| `test_auth.py` | регистрация (успех, дубликаты username/email), логин (успех, неверный пароль, неизвестный юзер) |
| `test_categories.py` | CRUD, 404, 401 без токена, изоляция между пользователями |
| `test_transactions.py` | CRUD, валидация amount/type (422), чужие категории (400/404), изоляция |
| `test_analytics.py` | `/analytics/budget-plan`: rising/falling тренд, взвешенный бюджет, income-фильтр |
| `test_analytics_extra.py` | `/analytics/transactions` (фильтры, сортировка, даты), `/analytics/anomalies` (спайки, σ=0) |
| `test_errors.py` | форма payload для 401 / 404 / 422 |

## Структура БД

### Таблица `users`

| Поле          | Тип          | Ограничения             | Описание            |
|---------------|--------------|-------------------------|---------------------|
| id            | INTEGER      | PK                      | Идентификатор       |
| username      | VARCHAR(50)  | UNIQUE, NOT NULL        | Уникальный логин    |
| email         | VARCHAR(120) | UNIQUE, NOT NULL        | Уникальный email    |
| password_hash | VARCHAR(128) | NOT NULL                | bcrypt-хэш пароля   |
| created_at    | DATETIME     | DEFAULT `now()`         | Время регистрации   |

### Таблица `categories`

| Поле    | Тип          | Ограничения            | Описание                    |
|---------|--------------|------------------------|-----------------------------|
| id      | INTEGER      | PK                     | Идентификатор               |
| name    | VARCHAR(100) | NOT NULL               | Название                    |
| user_id | INTEGER      | FK → `users.id`, NOT NULL | Владелец                 |

### Таблица `transactions`

| Поле        | Тип           | Ограничения                     | Описание                              |
|-------------|---------------|---------------------------------|---------------------------------------|
| id          | INTEGER       | PK                              | Идентификатор                         |
| amount      | NUMERIC(10,2) | NOT NULL, > 0 (на уровне схемы) | Сумма                                 |
| description | VARCHAR(255)  | NULL                            | Комментарий                           |
| type        | VARCHAR(7)    | NOT NULL                        | `income` / `expense`                  |
| created_at  | DATETIME      | DEFAULT `now()`                 | Время создания                        |
| user_id     | INTEGER       | FK → `users.id`, NOT NULL       | Владелец                              |
| category_id | INTEGER       | FK → `categories.id`, NOT NULL  | Категория                             |

### Связи

```
users (1) ────< (N) categories
  │
  └──< (N) transactions >── (N) (1) categories
```

- `User 1 — N Category` — категории принадлежат пользователю.
- `User 1 — N Transaction` — транзакции принадлежат пользователю.
- `Category 1 — N Transaction` — каждая транзакция привязана к одной категории.
- Все ресурсы строго изолированы: пользователь не видит и не может
  модифицировать чужие данные. Проверка владения категорией выполняется
  при создании и обновлении транзакций.

## Формат ошибок

Все исключения проходят через глобальные handler'ы и возвращают единый JSON.

**Обычная ошибка (401/404/400 и т.п.):**
```json
{
  "error": "not_found",
  "status_code": 404,
  "detail": "Category not found or does not belong to the current user"
}
```

**Ошибка валидации (422):**
```json
{
  "error": "validation_error",
  "status_code": 422,
  "detail": "Request validation failed",
  "errors": [
    {"field": "amount", "message": "Input should be greater than 0", "type": "greater_than"},
    {"field": "email",  "message": "value is not a valid email address", "type": "value_error"}
  ]
}
```

## Эндпоинты

Базовый URL: `http://127.0.0.1:8000`

### Авторизация

| Метод | Путь         | Описание                          | Auth |
|-------|--------------|-----------------------------------|------|
| POST  | `/register`  | Регистрация пользователя          | нет  |
| POST  | `/login`     | Получение JWT (OAuth2 form)       | нет  |

### Категории

| Метод  | Путь                  | Описание                   | Auth |
|--------|-----------------------|----------------------------|------|
| POST   | `/categories`         | Создать категорию          | да   |
| GET    | `/categories`         | Список категорий           | да   |
| GET    | `/categories/{id}`    | Получить категорию по id   | да   |
| PATCH  | `/categories/{id}`    | Обновить категорию         | да   |
| DELETE | `/categories/{id}`    | Удалить категорию          | да   |

### Транзакции

| Метод  | Путь                     | Описание                       | Auth |
|--------|--------------------------|--------------------------------|------|
| POST   | `/transactions`          | Создать транзакцию             | да   |
| GET    | `/transactions`          | Список транзакций              | да   |
| GET    | `/transactions/{id}`     | Получить транзакцию по id      | да   |
| PATCH  | `/transactions/{id}`     | Обновить транзакцию            | да   |
| DELETE | `/transactions/{id}`     | Удалить транзакцию             | да   |

### Аналитика

| Метод | Путь                         | Описание                                                 | Auth |
|-------|------------------------------|----------------------------------------------------------|------|
| GET   | `/analytics/budget-plan`     | Прогноз бюджета на следующий месяц по категориям         | да   |
| GET   | `/analytics/transactions`    | Фильтрация и сортировка транзакций                       | да   |
| GET   | `/analytics/anomalies`       | Категории с аномальными расходами (> mean + 2·σ)         | да   |

## Примеры запросов

Авторизация: после `/login` сохрани полученный `access_token` и отправляй
в заголовке `Authorization: Bearer <token>`.

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

Сохрани токен в переменную:
```bash
TOKEN="eyJhbGciOiJIUzI1NiIs..."
```

### 3. CRUD категорий

```bash
# Создать
curl -X POST http://127.0.0.1:8000/categories \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Food"}'

# Список
curl http://127.0.0.1:8000/categories \
  -H "Authorization: Bearer $TOKEN"

# По id
curl http://127.0.0.1:8000/categories/1 \
  -H "Authorization: Bearer $TOKEN"

# Обновить
curl -X PATCH http://127.0.0.1:8000/categories/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Groceries"}'

# Удалить
curl -X DELETE http://127.0.0.1:8000/categories/1 \
  -H "Authorization: Bearer $TOKEN"
```

### 4. CRUD транзакций

```bash
# Создать
curl -X POST http://127.0.0.1:8000/transactions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "42.50",
    "description": "lunch",
    "type": "expense",
    "category_id": 1
  }'

# Список
curl http://127.0.0.1:8000/transactions \
  -H "Authorization: Bearer $TOKEN"

# По id
curl http://127.0.0.1:8000/transactions/1 \
  -H "Authorization: Bearer $TOKEN"

# Обновить
curl -X PATCH http://127.0.0.1:8000/transactions/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"amount": "45.00", "description": "team lunch"}'

# Удалить
curl -X DELETE http://127.0.0.1:8000/transactions/1 \
  -H "Authorization: Bearer $TOKEN"
```

### 5. Прогноз бюджета

```bash
curl "http://127.0.0.1:8000/analytics/budget-plan?months=3&transaction_type=expense" \
  -H "Authorization: Bearer $TOKEN"
```

Query-параметры:
- `months` — сколько последних месяцев анализировать (2–12, default `3`)
- `transaction_type` — `expense` или `income` (default `expense`)

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

**Алгоритм:**
- **Среднее** — простое арифметическое помесячных тоталов.
- **Тренд** — сравнение среднего второй половины окна с первой:
  `|Δ| < 5%` → `stable`, иначе `rising` / `falling`.
- **Рекомендуемый бюджет** — взвешенное скользящее среднее с линейными
  весами `[1, 2, …, N]` (свежие месяцы важнее):
  ```
  suggested = Σ(totalᵢ · (i+1)) / Σ(i+1)
  ```

### 6. Фильтрация транзакций

```bash
# По дате и категории, с сортировкой по сумме убыв.
curl "http://127.0.0.1:8000/analytics/transactions\
?date_from=2026-01-01\
&date_to=2026-03-31\
&category_id=1\
&transaction_type=expense\
&sort_by=amount\
&order=desc" \
  -H "Authorization: Bearer $TOKEN"
```

Query-параметры:
- `date_from`, `date_to` — диапазон дат, включительно (`YYYY-MM-DD`)
- `category_id` — только категория текущего пользователя
- `transaction_type` — `expense` / `income`
- `sort_by` — `date` (default) / `amount`
- `order` — `desc` (default) / `asc`

Ошибки:
- `422` — `date_from > date_to`, неверный `sort_by`/`order`
- `404` — категория не существует или чужая

### 7. Аномальные расходы

```bash
curl "http://127.0.0.1:8000/analytics/anomalies?months=6&transaction_type=expense" \
  -H "Authorization: Bearer $TOKEN"
```

Query-параметры:
- `months` — окно анализа (3–24, default `6`)
- `transaction_type` — `expense` / `income` (default `expense`)

Ответ:
```json
{
  "months_analyzed": 6,
  "transaction_type": "expense",
  "anomalies": [
    {
      "category_id": 3,
      "category_name": "Entertainment",
      "mean_monthly": "250.00",
      "stdev_monthly": "335.41",
      "threshold": "920.82",
      "anomalous_months": [
        {"month": "2026-03", "total": "1000.00", "deviation_sigmas": 2.24}
      ]
    }
  ]
}
```

**Алгоритм:**
Для каждой категории строится массив помесячных тоталов (пустые месяцы = 0),
вычисляется среднее `μ` и population standard deviation `σ`. Если для
какого-либо месяца `total > μ + 2·σ`, он попадает в `anomalous_months` с
указанием `deviation_sigmas = (total − μ) / σ`. Категории сортируются
по максимальному отклонению по убыванию. Категории с `σ = 0`
(полностью константные расходы) не проверяются — аномалий в них быть не может.

## Безопасность

- Пароли хранятся как bcrypt-хэши.
- JWT подписывается `HS256`, TTL — 60 минут.
- `SECRET_KEY` — заглушка, вынеси в переменную окружения перед деплоем.
- Все пользовательские ресурсы (категории, транзакции) изолированы по
  `user_id` — пользователь не видит и не может модифицировать чужие данные.
- 404-сообщения не раскрывают, существует ли ресурс у другого пользователя.

## Автор

**Nikolay Butrin**

## Лицензия

MIT
