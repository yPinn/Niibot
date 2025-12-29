FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ .
RUN mkdir -p /app/twitch
COPY twitch/config.py /app/twitch/config.py

# 創建 data 目錄並複製數據文件
RUN mkdir -p /app/data
COPY data/ /app/data/

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
