FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY discord/ .

# 創建 data 目錄供 volume 掛載使用
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
