FROM ghcr.io/d4vinci/scrapling:latest

WORKDIR /app

# Only add the web framework on top — Scrapling + Chromium already in base image
COPY scrapling/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY scrapling/main.py ./

ENV PYTHONUNBUFFERED=1 \
    PORT=3001

EXPOSE 3001
CMD ["python", "main.py"]
