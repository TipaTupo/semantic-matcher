FROM python:3.12-slim
USER root
WORKDIR /app

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Виртуальное окружение
RUN python -m venv /app/venv

# Установка зависимостей
COPY requirements.txt .
RUN /app/venv/bin/pip install --no-cache-dir --upgrade pip
RUN /app/venv/bin/pip install --no-cache-dir -r requirements.txt

# Создание директорий
RUN mkdir -p /app/models /app/data /app/front

# Копирование кода
COPY *.py ./
COPY /front /app/front/

# Переменные окружения
ENV PATH="/app/venv/bin:$PATH"
ENV PYTHONPATH="/app"

EXPOSE 8123

CMD ["/app/venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8123"]
