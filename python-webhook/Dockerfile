FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY webhook.py .
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "webhook:app"]