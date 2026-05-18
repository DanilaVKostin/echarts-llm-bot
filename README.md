# ECharts LLM Bot

Чат-бот для генерации интерактивных графиков [Apache ECharts](https://echarts.apache.org/) с помощью LLM. Описываете нужный график текстом — получаете готовую конфигурацию ECharts.

**Возможности:**

- Генерация и доработка графиков в диалоге
- Загрузка данных из CSV / JSON файлов
- Автоматический запрос данных из PostgreSQL по описанию на естественном языке
- Выбор модели: локальная (Ollama) или облачная (OpenRouter)

---

## Требования

| Компонент | Минимальная версия            |
| --------- | ----------------------------- |
| Python    | 3.10                          |
| Node.js   | 18                            |
| Ollama    | любая (для локальных моделей) |

---

## Установка

### 1. Переменные окружения

```bash
cp .env.example .env
```

Заполните `.env`:

```env
# Нужен только если используете OpenRouter-модели
OPENROUTER_API_KEY=sk-or-v1-...

# Нужен только если хотите генерировать графики из БД
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

Все остальные значения имеют разумные дефолты и менять их не обязательно.

### 2. Бэкенд

```bash
cd backend
python -m venv .venv

# Windows (Git Bash)
source .venv/Scripts/activate

# Windows (PowerShell)
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Фронтенд

```bash
cd frontend
npm install
```

### 4. Модели Ollama (для локального режима)

```bash
ollama pull qwen2.5:7b        # основная LLM
ollama pull nomic-embed-text  # эмбеддинги для RAG
```

### 5. Сборка RAG-индекса (один раз)

Из папки `backend/` с активированным venv:

```bash
python -m scripts.build_rag
```

Индекс строится из файлов в `data/rag_sources/` и сохраняется в `backend/data/chroma_db/`.

---

## Запуск

Запускайте в **двух отдельных** терминалах.

**Терминал 1 — бэкенд** (из `backend/`, venv активирован):

```bash
# Windows (Git Bash)
./runbackend.sh

# Linux / macOS
uvicorn app.main:app --reload --port 9000
```

**Терминал 2 — фронтенд** (из `frontend/`):

```bash
npm run dev
```

| Сервис   | URL                       |
| -------- | ------------------------- |
| Фронтенд | http://localhost:3000     |
| Бэкенд   | http://localhost:9000     |

---

## Модели

В интерфейсе можно выбрать модель через выпадающее меню:

| Метка в UI                        | Требует              |
| --------------------------------- | -------------------- |
| Local · qwen2.5                   | Ollama               |
| Local · qwen3.5 9B                | Ollama               |
| Local · qwen3-coder 30B           | Ollama               |
| OpenRouter · qwen3.6-27b          | `OPENROUTER_API_KEY` |
| OpenRouter · GPT-4o               | `OPENROUTER_API_KEY` |
| OpenRouter · Gemini 2.5 Flash     | `OPENROUTER_API_KEY` |
| OpenRouter · Gemini 2.5 Flash Lite| `OPENROUTER_API_KEY` |
| OpenRouter · DeepSeek V3.2        | `OPENROUTER_API_KEY` |

---

## Работа с данными

**Загрузка файла** — нажмите 📎 в строке ввода и прикрепите `.csv` или `.json`. Бот построит график по этим данным.

**PostgreSQL** — если задан `DATABASE_URL`, бот автоматически генерирует SQL-запрос по вашему описанию и строит график из результатов. Проверить соединение с БД можно кнопкой **Test DB Query** в шапке.

---

## Структура проекта

```
echarts-llm-bot/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI приложение
│   │   ├── config.py            # Настройки (pydantic-settings)
│   │   ├── routers/             # Эндпоинты: /api/chart, /api/rag, /api/search
│   │   ├── services/            # LLM, БД, RAG, эмбеддинги
│   │   └── prompts/             # Системные промпты
│   ├── scripts/
│   │   └── build_rag.py         # Сборка ChromaDB индекса для ECharts RAG
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.tsx              # Основной UI
│       └── SearchTest.tsx       # Поиск индикаторов
├── data/
│   └── rag_sources/             # Документация ECharts для RAG
└── .env.example
```

---

## Пересборка RAG-индекса

Если добавили новые файлы в `data/rag_sources/`:

```bash
cd backend
python -m scripts.build_rag
```

## Визуальное представление "как работает проект"

<img width="2070" height="789" alt="image" src="https://github.com/user-attachments/assets/01550ac5-db5d-472e-a147-164a1c3d57d9" />
