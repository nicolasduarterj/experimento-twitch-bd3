import pandas as pd
import time
from tqdm import tqdm
from cassandra.io.asyncorereactor import AsyncoreConnection
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy

EDGES_FILE = "twitch_gamers/large_twitch_edges.csv"
FEATURES_FILE = "twitch_gamers/large_twitch_features.csv"
BATCH_SIZE = 500
CONCURRENCY = 512 # uniform for both tables

print("Carregando CSVs para memória")
edges = pd.read_csv(EDGES_FILE)
features = pd.read_csv(FEATURES_FILE)

edges.columns = ["src", "dst"]
features.columns = ["views", "mature", "life_time",
                    "created_at", "updated_at", "numeric_id",
                    "dead_account", "language", "affiliate"]

def ingest_scylladb():
    cluster = Cluster(
        ["127.0.0.1"],
        load_balancing_policy=DCAwareRoundRobinPolicy(local_dc="datacenter1"),
        connection_class=AsyncoreConnection,
        connect_timeout=30,
        idle_heartbeat_interval=60,
        idle_heartbeat_timeout=30
    )
    session = cluster.connect()

    session.execute("""
        CREATE KEYSPACE IF NOT EXISTS twitch
        WITH replication = {'class':'SimpleStrategy', 'replication_factor':1}
    """, timeout=120)
    session.set_keyspace("twitch")

    session.execute("""CREATE TABLE IF NOT EXISTS users (
        numeric_id INT PRIMARY KEY, views BIGINT, mature BOOLEAN,
        life_time INT, created_at TEXT, updated_at TEXT,
        dead_account BOOLEAN, language TEXT, affiliate BOOLEAN)""", timeout=120)

    session.execute("""CREATE TABLE IF NOT EXISTS adjacency (
        src_id INT, dst_id INT, PRIMARY KEY (src_id, dst_id))""", timeout=120)

    t0 = time.time()

    # FIX 1: cast types BEFORE building the list
    features["mature"] = features["mature"].astype(bool)
    features["dead_account"] = features["dead_account"].astype(bool)
    features["affiliate"] = features["affiliate"].astype(bool)
    features["numeric_id"] = features["numeric_id"].astype(int)
    features["views"] = features["views"].astype(int)
    features["life_time"] = features["life_time"].astype(int)

    # FIX 2: column order matches the INSERT statement exactly
    insert_user = session.prepare(
        "INSERT INTO users (views, mature, life_time, created_at, "
        "updated_at, numeric_id, dead_account, language, affiliate) VALUES (?,?,?,?,?,?,?,?,?)"
    )
    col_order = ["views", "mature", "life_time", "created_at",
                 "updated_at", "numeric_id", "dead_account", "language", "affiliate"]
    rows = features[col_order].values.tolist()

    from cassandra.concurrent import execute_concurrent_with_args

    for i in tqdm(range(0, len(rows), BATCH_SIZE), desc="ScyllaDB users"):
        execute_concurrent_with_args(
            session, insert_user, rows[i:i + BATCH_SIZE], concurrency=CONCURRENCY
        )

    # FIX 3: same concurrency for edges
    insert_edges = session.prepare("INSERT INTO adjacency (src_id, dst_id) VALUES (?,?)")
    edge_rows = edges.values.tolist()
    for i in tqdm(range(0, len(edge_rows), BATCH_SIZE), desc="ScyllaDB edges"):
        execute_concurrent_with_args(
            session, insert_edges, edge_rows[i:i + BATCH_SIZE], concurrency=CONCURRENCY
        )

    elapsed = time.time() - t0
    print(f"[Cassandra] tempo de ingestão: {elapsed:.2f}s")
    cluster.shutdown()
    return elapsed

if __name__ == "__main__":
    ingest_scylladb()
