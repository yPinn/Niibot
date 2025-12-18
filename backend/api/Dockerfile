FROM python:3.11-slim

WORKDIR /app

# 複製共享的 requirements.txt
COPY ../requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製 API 代碼
COPY . .

ENV PYTHONUNBUFFERED=1

# FastAPI 預設運行在 8000 port
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
