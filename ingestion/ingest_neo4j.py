import pandas as pd
import time
from neo4j import GraphDatabase
from tqdm import tqdm

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

def ingest_neo4j():
    driver = GraphDatabase.driver("bolt://localhost:7687",
                                  auth=("neo4j", "benchmark123"))
    
    t0 = time.time()

    with driver.session() as session:
        session.run("CREATE INDEX user_id IF NOT EXISTS FOR (u:User) ON (u.numeric_id)")
        session.run("CREATE INDEX user_lang IF NOT EXISTS FOR (u:User) ON (u.language)")
        session.run("CREATE INDEX user_aff IF NOT EXISTS FOR (u:User) ON (u.affiliate)")

        user_records = features.to_dict("records")
        for i in tqdm(range(0, len(user_records), BATCH_SIZE), desc="Neo4J nodes"):
            batch = user_records[i:i+BATCH_SIZE]
            session.run("""
                UNWIND $batch AS row
                CREATE (:User {
                    numeric_id:  row.numeric_id,
                    views:       row.views,
                    mature:      row.mature,
                    life_time:   row.life_time,
                    dead_account:row.dead_account,
                    language:    row.language,
                    affiliate:   row.affiliate
                })
            """, batch=batch)

        edge_records = edges.to_dict("records")
        for i in tqdm(range(0, len(edge_records), BATCH_SIZE), desc="Neo4j edges"):
            batch = edge_records[i:i+BATCH_SIZE]
            session.run("""
                UNWIND $batch AS row
                MATCH (a:User {numeric_id: row.src})
                MATCH (b:User {numeric_id: row.dst})
                MERGE (a)-[:FOLLOWS]-(b)
            """, batch=batch)
    
    elapsed = time.time() - t0
    print(f"[Neo4J] tempo de ingestão: {elapsed: .2f}s")
    driver.close()
    return elapsed

if __name__ == "__main__":
    ingest_neo4j()
