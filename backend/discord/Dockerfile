FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY discord/ .

# 創建 data 目錄並複製數據文件
RUN mkdir -p /app/data
COPY data/ /app/data/

ENV PYTHONUNBUFFERED=1

# 暴露 HTTP 服務器埠口（用於 Render Web Service）
EXPOSE 8080

CMD ["python", "bot.py"]
