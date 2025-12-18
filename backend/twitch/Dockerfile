FROM python:3.11-slim

WORKDIR /app

# 複製父目錄的 requirements.txt
COPY ../requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製當前目錄（twitch bot）所有文件
COPY . .

ENV PYTHONUNBUFFERED=1

# TwitchIO AutoBot uses internal port 4343 for OAuth
EXPOSE 4343

CMD ["python", "main.py"]
