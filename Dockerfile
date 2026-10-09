# クラウド（Fly.io など）で動かすためのコンテナ。手順は DEPLOY.md
FROM python:3.14-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8080 EVE_DATA_DIR=/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["python", "app.py", "--no-browser"]
