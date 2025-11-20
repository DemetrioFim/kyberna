FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ingest_iowa.py .

CMD ["python", "ingest_iowa_liquors.py"]