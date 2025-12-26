FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY twitch/ .

ENV PYTHONUNBUFFERED=1
EXPOSE 4343

CMD ["python", "main.py"]
