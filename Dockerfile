FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

RUN useradd --create-home --uid 10001 dashboard
USER 10001

EXPOSE 8080
ENTRYPOINT ["python", "-m", "app.server", "--host", "0.0.0.0", "--port", "8080", "--config", "/app/config/config.yml"]
