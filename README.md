# Semantic Matcher

Микросервис для семантического поиска статей на основе пользовательских запросов. Использует векторные эмбеддинги (Sentence Transformers) и индекс FAISS для быстрого поиска семантически схожих вопросов/статей.

## Возможности

- **Семантический поиск** — поиск статей по смыслу запроса с настраиваемым порогом схожести
- **Версионирование индексов** — создание, активация, переименование, закрепление и удаление версий
- **Индексация данных** — ручное добавление через JSON и загрузка файлов (.json, .xlsx, .txt)
- **Управление статьями** — просмотр, редактирование, удаление статей, примеров (samples) и синонимов
- **Генерация синонимов через LLM** — автоматическое создание альтернативных формулировок вопросов
- **Управление стоп-словами** — настройка списка стоп-слов для препроцессинга текста
- **Фоновая обработка задач** — асинхронная очередь задач с приоритетами и отслеживанием прогресса
- **Восстановление после сбоев** — автоматическое восстановление прерванных задач при перезапуске
- **Веб-интерфейс** — встроенный UI для всех операций

## Архитектура

```
/
├── main.py              # Точка входа, FastAPI приложение
├── api.py               # REST API эндпоинты
├── config.py            # Конфигурация приложения
├── instance.py          # Глобальный state (индекс, метаданные, очередь)
├── schemas.py           # Pydantic модели запросов/ответов
├── tasks.py             # Фоновые задачи и процессор очереди
├── utils.py             # Утилиты (эмбеддинги, FAISS, работа с данными)
├── requirements.txt     # Python зависимости
├── Dockerfile           # Docker образ
├── docker-compose.yml   # Docker Compose конфигурация
├── stop-words.json      # Список стоп-слов
└── front/               # Веб-интерфейс
    ├── index.html
    ├── app.js
    └── styles/
```

## Технологический стек

| Компонент | Технология |
|-----------|-----------|
| Backend | FastAPI (Python 3.12) |
| Эмбеддинги | Sentence Transformers |
| Векторный поиск | FAISS (Facebook AI Similarity Search) |
| Обработка данных | Pandas, NumPy |
| LLM интеграция | OpenAI-совместимый API (Ollama и др.) |
| Фронтенд | Vanilla JS, HTML, CSS |
| Контейнеризация | Docker, Docker Compose |

## API

### Health Check

```http
GET /health
```

```json
{ "status": "ok" }
```

### Поиск

```http
POST /search?limit=10&threshold=0.7
Content-Type: application/json

{ "query": "Как оформить полис?" }
```

```json
{
  "articles": ["Статья 1", "Статья 2"],
  "scores": [0.92, 0.85],
  "version_used": "20260602_120000",
  "processing_time_ms": 45.2
}
```

### Индексация данных

```http
# Индексация из JSON
POST /reindex?update_current=false&activate=true&pin=false&llm=false
Content-Type: application/json

{
  "data": [
    {
      "id": "article_1",
      "title": "Оформление полиса",
      "samples": ["Как оформить полис?", "Хочу купить страховку"]
    }
  ]
}

# Индексация из файла
POST /reindex/file?activate=true&pin=false&llm=false
Content-Type: multipart/form-data

files: [<file.json или file.xlsx>]
```

Оба эндпоинта возвращают (202 Accepted):

```json
{
  "task_id": "i-20260602_120000_abcd",
  "status": "pending"
}
```

### Управление версиями

```http
GET /versions                          # Получить список версий

POST /versions/{version_id}            # Управление версией
Content-Type: application/json

{ "action": "activate" }               # activate | rename | pin | unpin | delete
{ "action": "rename", "name": "Новое имя" }
```

### Управление статьями

```http
GET /articles/{version_id}                     # Список статей
GET /articles/{version_id}/{article_id}        # Детали статьи

DELETE /articles/{version_id}/{article_id}     # Удалить статью
DELETE /articles/{version_id}/{article_id}/ids # Удалить samples/synonyms
Content-Type: application/json
{ "ids": ["smp_1", "syn_2"] }

DELETE /articles/{version_id}/{article_id}/synonyms   # Удалить все синонимы
DELETE /articles/{version_id}/{article_id}/all        # Удалить все samples и синонимы

POST /articles/{version_id}/{article_id}/convert      # Конвертировать синонимы в samples
Content-Type: application/json
{ "ids": ["syn_1", "syn_2"] }

POST /articles/{version_id}/{article_id}/synonyms     # Генерация синонимов через LLM
Content-Type: application/json
{ "ids": ["smp_1", "smp_2"] }
```

### Очередь задач

```http
GET /queue                    # Статус очереди
DELETE /queue                 # Очистить очередь
GET /queue/restart            # Перезапустить прерванные задачи
GET /task/{task_id}           # Статус задачи
DELETE /task/{task_id}        # Удалить/отменить задачу
```

### Настройки

```http
GET /stopwords                      # Получить стоп-слова
PUT /stopwords                      # Обновить стоп-слова
Content-Type: application/json
{ "stop_words": ["и", "в", "на"] }

GET /llm/config                     # Получить конфиг LLM
PUT /llm/config                      # Обновить конфиг LLM
Content-Type: application/json
{
  "llm_url": "https://api.example.com/v1",
  "llm_model": "gpt-3.5-turbo",
  "llm_temperature": 0.4
}
```

### Статические файлы

```
GET /              # Веб-интерфейс
GET /front/*       # Статические файлы фронтенда
```

## Формат данных

### JSON

```json
[
  {
    "id": "article_001",
    "title": "Оформление полиса ОСАГО",
    "samples": [
      "Как оформить полис ОСАГО?",
      "Хочу купить страховку на авто",
      "Где можно сделать ОСАГО?"
    ]
  }
]
```

### XLSX

| id        | title                  | samples                                        |
|-----------|------------------------|------------------------------------------------|
| article_1 | Оформление полиса ОСАГО | `["Как оформить?", "Хочу купить страховку"]`   |
| article_2 | Уплата взносов          | Как внести payment                             |

В столбце `samples` может быть как JSON-массив строк, так и единичная строка.

## Переменные окружения

| Переменная | Описание | По умолчанию |
|-----------|----------|-------------|
| `DATA_DIR` | Директория для хранения данных | `""` |
| `MODEL_NAME` | Название модели эмбеддингов | `""` |
| `DEFAULT_LIMIT` | Макс. результатов поиска | `10` |
| `SIMILARITY_THRESHOLD` | Порог схожести | `0.7` |
| `SYNONYM_VALIDATION_THRESHOLD` | Порог валидации синонимов | `0.75` |
| `BATCH_SIZE` | Размер батча при индексации | `32` |
| `MAX_QUEUE_SIZE` | Макс. размер очереди задач | `5` |
| `STALE_LOCK_TIMEOUT_MINUTES` | Таймаут заблокированных задач | `10` |
| `MAX_VERSIONS` | Макс. кол-во версий | `10` |
| `LLM_URL` | URL LLM API | `""` |
| `LLM_API_KEY` | API ключ LLM | `""` |
| `LLM_AUTH_TOKEN` | Auth токен LLM | `""` |
| `LLM_MODEL` | Модель LLM | `""` |
| `LLM_TEMPERATURE` | Temperature | `0.4` |
| `LLM_TOP_P` | Top P | `0.7` |
| `LLM_FREQUENCY_PENALTY` | Frequency Penalty | `0.2` |
| `LLM_REPEAT_PENALTY` | Repeat Penalty | `1.1` |
| `LLM_PRESENCE_PENALTY` | Presence Penalty | `0.1` |

## Структура данных

```
data/
├── versions/
│   └── {timestamp}/
│       ├── index.faiss          # FAISS векторный индекс
│       └── metadata.json        # Метаданные версии
├── active_version.json          # Текущая активная версия
├── pin_versions.json            # Закреплённые версии
├── tasks.json                   # Активные задачи
├── done_tasks.json              # Завершённые задачи
└── {task_id}/                   # Временные данные задачи
    └── data.json
```

## Приоритеты эндпоинтов

Система использует приоритетную очередь для обработки запросов:

- **Приоритет 1 (высший)** — `/health`, `/search` — всегда обрабатываются немедленно
- **Приоритет 2 (средний)** — управление версиями, статьями, задачами, настройками
- **Приоритет 3 (низший)** — индексация данных (фоновая обработка)
