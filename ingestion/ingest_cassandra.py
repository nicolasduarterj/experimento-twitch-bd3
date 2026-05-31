import pandas as pd
import time
from tqdm import tqdm
from cassandra.io.asyncorereactor import AsyncoreConnection
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy

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

def ingest_cassandra():
    cluster = Cluster(["127.0.0.1"],
                      load_balancing_policy=DCAwareRoundRobinPolicy(local_dc="datacenter1"),
                      connection_class=AsyncoreConnection)
    session = cluster.connect()

    session.execute("""
        CREATE KEYSPACE IF NOT EXISTS twitch
        WITH replication = {'class':'SimpleStrategy', 'replication_factor':1}
    """)
    session.set_keyspace("twitch")

    session.execute("""CREATE TABLE IF NOT EXISTS users (
        numeric_id INT PRIMARY KEY, views BIGINT, mature BOOLEAN,
        life_time INT, created_at TEXT, updated_at TEXT,
        dead_account BOOLEAN, language TEXT, affiliate BOOLEAN)""")
    
    session.execute("""CREATE TABLE IF NOT EXISTS adjacency (
        src_id INT, dst_id INT, PRIMARY KEY (src_id, dst_id))""")
    
    t0 = time.time()

    insert_user = session.prepare(
        "INSERT INTO users (views,mature,life_time,created_at,"
        "updated_at,numeric_id,dead_account,language,affiliate) VALUES (?,?,?,?,?,?,?,?,?)")
    
    from cassandra.concurrent import execute_concurrent_with_args

    rows = features.values.tolist()
    features["mature"] = features["mature"].astype(bool)
    features["dead_account"] = features["dead_account"].astype(bool)
    features["affiliate"] = features["affiliate"].astype(bool)
    features["numeric_id"] = features["numeric_id"].astype(int)
    features["views"] = features["views"].astype(int)
    features["life_time"] = features["life_time"].astype(int)
    for i in tqdm(range(0, len(rows), BATCH_SIZE), desc="Cassandra users"):
        batch = rows[i:i+BATCH_SIZE]
        execute_concurrent_with_args(session, insert_user, batch,
                                     concurrency=5000)

    insert_edges = session.prepare("INSERT INTO adjacency (src_id, dst_id) VALUES (?,?)")
    edge_rows = edges.values.tolist()
    for i in tqdm(range(0, len(edge_rows), BATCH_SIZE), desc="Cassandra edges"):
        execute_concurrent_with_args(session, insert_edges, edge_rows[i:i+BATCH_SIZE], concurrency=50)

    elapsed = time.time() - t0
    print(f"[Cassandra] tempo de ingestão: {elapsed: .2f}s")
    cluster.shutdown()
    return elapsed

if __name__ == "__main__":
    ingest_cassandra()