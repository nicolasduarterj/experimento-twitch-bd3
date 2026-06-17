import duckdb
import time
from tqdm import tqdm
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

INDEX_NAME = "yellow_taxi"
PATH_PARQUET = "nyc_taxi/yellow_tripdata_2026-04.parquet"
CHUNK_SIZE = 50000

def ingest_elasticsearch():
    es = Elasticsearch("http://localhost:9200")

    t0 = time.time()
    if es.indices.exists(index=INDEX_NAME):
        es.indices.delete(index=INDEX_NAME)
    es.indices.create(index=INDEX_NAME)

    con = duckdb.connect()
    total_records = con.execute(f"SELECT COUNT(*) FROM '{PATH_PARQUET}'").fetchone()[0]
    
    cursor = con.cursor()
    cursor.execute(f"SELECT * FROM '{PATH_PARQUET}'")
    
    columns = [desc[0] for desc in cursor.description]

    def generate_actions():
        with tqdm(total=total_records, desc="[Elasticsearch] Ingestão", unit=" docs") as pbar:
            while True:
                rows = cursor.fetchmany(CHUNK_SIZE)
                if not rows:
                    break
                
                for row in rows:
                    yield {
                        "_index": INDEX_NAME,
                        "_source": dict(zip(columns, row))
                    }
                
                pbar.update(len(rows))

    success, _ = bulk(
        client=es.options(request_timeout=120),
        actions=generate_actions(),
        chunk_size=CHUNK_SIZE
    )

    elapsed = time.time() - t0
    print(f"[Elasticsearch] tempo de ingestão: {elapsed:.2f}s | {success:,} registros")
    
    con.close()
    return elapsed

if __name__ == "__main__":
    ingest_elasticsearch()