import os
import json
from sodapy import Socrata
from pymongo import MongoClient


MONGO_USER = os.getenv("MONGO_INITDB_ROOT_USERNAME", "mongoadmin")
MONGO_PASS = os.getenv("MONGO_INITDB_ROOT_PASSWORD", "mongoadmin")
MONGO_HOST = os.getenv("MONGO_HOST", "mongodb")

SOCRATA_DOMAIN = "data.iowa.gov"
SOCRATA_APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN")
SOCRATA_APP_USER = os.getenv("SOCRATA_APP_USER")
SOCRATA_APP_PWD = os.getenv("SOCRATA_APP_PWD")

def get_socrata_client():
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

def run_ingestion(date_query, data_limit=99999):
    client = get_socrata_client()
    try:
        result = client.get("m3tr-qhgy", date=date_query, limit=data_limit)
        if not result:
            print("No data from API")
            return
    except Exception as e:
        print(f"API ERROR: {e}")
    
    try:
        collection = get_mongo_collection()
        collection.insert_many(result)
        print(f"Total rows inserted {len(result)}")
    except Exception as e:
        print(f"MONGO ERROR: {e}")