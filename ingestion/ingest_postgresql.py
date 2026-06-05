import pandas as pd
import time
from tqdm import tqdm
import psycopg

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

order_feature = [
    "numeric_id", "views", "life_time", "mature",
    "dead_account", "affiliate", "language", "created_at", "updated_at"
]
features = features[order_feature]
features["numeric_id"] = features["numeric_id"].astype("Int64")
features["views"] = features["views"].astype("Int64")
features["life_time"] = features["life_time"].astype(int)
features["mature"] = features["mature"].astype(bool)
features["dead_account"] = features["dead_account"].astype(bool)
features["affiliate"] = features["affiliate"].astype(bool)
features["language"] = features["language"].astype(str)
features["created_at"] = pd.to_datetime(features["created_at"]).dt.date
features["updated_at"] = pd.to_datetime(features["updated_at"]).dt.date
edges["src"] = edges["src"].astype("Int64")
edges["dst"] = edges["dst"].astype("Int64")

def ingest_postgresql():
    with psycopg.connect("host=localhost port=5432 dbname=twitch user=benchmark password=benchmark123") as conn:
        with conn.cursor() as cur:

            cur.execute("""
                CREATE TABLE IF NOT EXISTS users(
                    id bigint primary key,
                    views bigint not null default 0,
                    lifetime int not null default 0,
                    mature boolean not null default false,
                    dead_account boolean not null default false,
                    affiliate boolean not null default false,
                    language varchar(10) not null default 'EN',
                    created_at date not null,
                    updated_at date not null
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS friendships(
                    src_id bigint not null,
                    dst_id bigint not null,
                    
                    primary key (src_id, dst_id),
                    foreign key (src_id) references users (id) on delete cascade,
                    foreign key (dst_id) references users (id) on delete cascade
                );
            """)

            t0 = time.time()

            insert_rows_query = """
                INSERT INTO users 
                    (id, views, lifetime, mature, dead_account, affiliate, language, created_at, updated_at)
                VALUES 
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            features_rows = features.values.tolist()
            for i in tqdm(range(0, len(features_rows), BATCH_SIZE), desc="PostgreSQL nodes"):
                batch = features_rows[i : i + BATCH_SIZE]
                
                cur.executemany(insert_rows_query, batch)

            insert_edges_query = """
                INSERT INTO friendships 
                    (src_id, dst_id) 
                VALUES 
                    (%s, %s)
            """

            edge_rows = edges.values.tolist()
            for i in tqdm(range(0, len(edge_rows), BATCH_SIZE), desc="PostgreSQL edges"):
                batch = edge_rows[i : i + BATCH_SIZE]
                
                cur.executemany(insert_edges_query, batch)
            
            conn.commit()

            elapsed = time.time() - t0
            print(f"[PostgreSQL] tempo de ingestão: {elapsed: .2f}s")
    
    return elapsed    

if __name__ == "__main__":
    ingest_postgresql()
