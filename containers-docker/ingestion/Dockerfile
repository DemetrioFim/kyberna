FROM python:latest

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ingest_iowa_liquors.py .

CMD ["python", "ingest_iowa_liquors.py"]