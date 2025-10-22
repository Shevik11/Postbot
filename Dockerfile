# Використовуємо офіційний Python образ
FROM python:3.11-slim

# Встановлюємо робочу директорію
WORKDIR /app

# Копіюємо файл залежностей
COPY requirements.txt .

# Встановлюємо залежності
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо код додатку цілком
COPY . .

# Створюємо директорію для бази даних
RUN mkdir -p /app/data

# Встановлюємо змінну середовища для Python
ENV PYTHONUNBUFFERED=1

# Відкриваємо порт (хоча для Telegram бота це не обов'язково)
EXPOSE 8000

# Команда для запуску бота
CMD ["python", "main.py"]
