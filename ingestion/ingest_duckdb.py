import duckdb
import time
from tqdm import tqdm

TABLE_NAME = "yellow_taxi"
PATH_PARQUET = "nyc_taxi/yellow_tripdata_2026-04.parquet"

def ingest_duckdb():
    con = duckdb.connect("./nyc_taxi.duckdb")
    t0  = time.time()
 
    con.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    con.execute(f"CREATE TABLE {TABLE_NAME} AS SELECT * FROM '{PATH_PARQUET}'")
 
    elapsed = time.time() - t0
    total   = con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
    print(f"[DuckDB]     tempo de ingestão: {elapsed:.2f}s | {total:,} registros")
    con.close()
    return elapsed

if __name__ == "__main__":
    ingest_duckdb()