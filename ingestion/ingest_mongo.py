import pandas as pd
import time
from tqdm import tqdm
from pymongo import MongoClient, InsertOne

EDGES_FILE = "twitch_gamers/large_twitch_edges.csv"
FEATURES_FILE = "twitch_gamers/large_twitch_features.csv"
BATCH_SIZE = 5000

print("Carregando CSVs para memória")
edges = pd.read_csv(EDGES_FILE)
features = pd.read_csv(FEATURES_FILE)

# Normalização dos nomes de coluna
edges.columns = ["src", "dst"]
features.columns = ["views", "mature", "life_time", 
                    "created_at", "updated_at", "numeric_id",
                    "dead_account", "language", "affiliate"]

def ingest_mongo():
    client = MongoClient("mongodb://localhost:27017")
    db = client["twitch"]

    t0 = time.time()

    docs = features.to_dict("records")
    for d in docs:
        d["_id"] = d.pop("numeric_id")

    for i in tqdm(range(0, len(docs), BATCH_SIZE), desc="Mongo users"):
        db.users.bulk_write([InsertOne(d) for d in docs[i:i+BATCH_SIZE]], ordered=False)
    
    edge_docs = edges.to_dict("records")
    for i in tqdm(range(0, len(edge_docs), BATCH_SIZE), desc="Mongo edges"):
        db.edges.bulk_write([InsertOne(e) for e in edge_docs[i:i+BATCH_SIZE]], ordered=False)

    db.users.create_index([("language", 1)])
    db.users.create_index([("affiliate", 1)])
    db.users.create_index([("views", -1)])
    db.edges.create_index([("src", 1)])
    db.edges.create_index([("dst", 1)])

    elapsed = time.time() - t0
    print(f"[MongoDB]   tempo de ingestão: {elapsed: .2f}s")
    client.close()
    return elapsed

if __name__ == "__main__":
    ingest_mongo()
