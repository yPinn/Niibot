FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY twitch/ .

# 創建 data 目錄並複製數據文件
RUN mkdir -p /app/data
COPY data/ /app/data/

ENV PYTHONUNBUFFERED=1
EXPOSE 4343 4344

CMD ["python", "main.py"]
