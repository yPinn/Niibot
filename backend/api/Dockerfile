FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ .
RUN mkdir -p /app/twitch
COPY twitch/config.py /app/twitch/config.py

# 創建 data 目錄供 volume 掛載使用
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
