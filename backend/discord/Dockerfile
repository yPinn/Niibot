FROM python:3.11-slim

WORKDIR /app

# 複製共享的 requirements.txt
COPY ../requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製 Discord bot 代碼
COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
