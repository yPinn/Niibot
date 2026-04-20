FROM python:3.12-slim

WORKDIR /app

COPY scrapling/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium --with-deps

COPY scrapling/main.py ./

ENV PYTHONUNBUFFERED=1 \
    PORT=3001

EXPOSE 3001
ENTRYPOINT ["python"]
CMD ["main.py"]
