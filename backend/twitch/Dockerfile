FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

# TwitchIO AutoBot uses internal port 4343 for OAuth
EXPOSE 4343

CMD ["python", "main.py"]
