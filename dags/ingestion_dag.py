from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import os
import json
from sodapy import Socrata
from pymongo import MongoClient

# Configuration
MONGO_USER = os.getenv("MONGO_INITDB_ROOT_USERNAME", "mongoadmin")
MONGO_PASS = os.getenv("MONGO_INITDB_ROOT_PASSWORD", "mongoadmin")
MONGO_HOST = os.getenv("MONGO_HOST", "mongodb")

SOCRATA_DOMAIN = "data.iowa.gov"
SOCRATA_APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN")
SOCRATA_APP_USER = os.getenv("SOCRATA_APP_USER")
SOCRATA_APP_PWD = os.getenv("SOCRATA_APP_PWD")

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2023, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def get_socrata_client():
    if not SOCRATA_APP_TOKEN:
        raise ValueError("SOCRATA_APP_TOKEN is missing")
    
    client = Socrata(SOCRATA_DOMAIN,
                 SOCRATA_APP_TOKEN,
                 SOCRATA_APP_USER,
                 SOCRATA_APP_PWD)
    return client

def get_mongo_collection():
    uri = f"mongodb://{MONGO_USER}:{MONGO_PASS}@{MONGO_HOST}:27017/"
    client = MongoClient(uri)
    db = client["datalake"]
    return db["iowa_liquor_sales_raw"]

def ingest_data(**kwargs):
    # Example: Ingest data for yesterday or a specific range
    # For now, we stick to the original script's logic or a default limit
    # We can pass date_query via DAG params or calculate it
    
    date_query = kwargs.get('dag_run').conf.get('date_query')
    data_limit = kwargs.get('dag_run').conf.get('limit', 2000)
    
    print(f"Starting ingestion. Limit: {data_limit}, Date Query: {date_query}")
    
    client = get_socrata_client()
    
    try:
        # If date_query is None, Socrata might return latest or all, depending on API
        # The original script expected a date_query. 
        # Let's default to a recent date if not provided, or handle it.
        # For this example, we'll just fetch recent data if no query.
        
        if date_query:
            result = client.get("m3tr-qhgy", date=date_query, limit=data_limit)
        else:
            # Just get some data
            result = client.get("m3tr-qhgy", limit=data_limit)
            
        if not result:
            print("No data from API")
            return
            
        collection = get_mongo_collection()
        collection.insert_many(result)
        print(f"Total rows inserted {len(result)}")
        
    except Exception as e:
        print(f"ERROR: {e}")
        raise e

with DAG(
    'ingest_iowa_liquors',
    default_args=default_args,
    description='Ingest Iowa Liquor Sales data to MongoDB',
    schedule_interval=timedelta(days=1),
    catchup=False,
) as dag:

    t1 = PythonOperator(
        task_id='ingest_to_mongo',
        python_callable=ingest_data,
    )
