import clickhouse_connect
import pandas as pd
import time
from tqdm import tqdm

TABLE_NAME   = "yellow_taxi"
PATH_PARQUET = "nyc_taxi/yellow_tripdata_2026-04.parquet"
BATCH_SIZE   = 50000

print("Carregando PARQUET para memória")
df = pd.read_parquet(PATH_PARQUET)

df = df.rename(columns={"Airport_fee": "airport_fee"})
df["tpep_pickup_datetime"]  = pd.to_datetime(df["tpep_pickup_datetime"],  errors="coerce", utc=False)
df["tpep_dropoff_datetime"] = pd.to_datetime(df["tpep_dropoff_datetime"], errors="coerce", utc=False)
df["passenger_count"] = df["passenger_count"].astype("Int64")
df["RatecodeID"]      = df["RatecodeID"].astype("Int64")
df["store_and_fwd_flag"] = df["store_and_fwd_flag"].astype("string")
money_cols = [
    "fare_amount", "extra", "mta_tax", "tip_amount", "tolls_amount",
    "improvement_surcharge", "total_amount", "congestion_surcharge",
    "airport_fee", "cbd_congestion_fee",
]
for col in money_cols:
    df[col] = df[col].round(2)

def ingest_clickhouse():
    client = clickhouse_connect.get_client(
        host="localhost",
        port=8123,
        username="benchmark",
        password="benchmark123",
        database="benchmark",
    )

    t0 = time.time()

    client.command(f"DROP TABLE IF EXISTS benchmark.{TABLE_NAME}")
    client.command(f"""
        CREATE TABLE benchmark.{TABLE_NAME}
        (
            VendorID              Int32,
            tpep_pickup_datetime  DateTime,
            tpep_dropoff_datetime DateTime,
            passenger_count       Nullable(Int64),
            trip_distance         Float64,
            RatecodeID            Nullable(Int64),
            store_and_fwd_flag    Nullable(String),
            PULocationID          Int32,
            DOLocationID          Int32,
            payment_type          Int64,
            fare_amount           Nullable(Float64),
            extra                 Nullable(Float64),
            mta_tax               Nullable(Float64),
            tip_amount            Nullable(Float64),
            tolls_amount          Nullable(Float64),
            improvement_surcharge Nullable(Float64),
            total_amount          Nullable(Float64),
            congestion_surcharge  Nullable(Float64),
            airport_fee           Nullable(Float64),
            cbd_congestion_fee    Nullable(Float64)
        )
        ENGINE = MergeTree()
        ORDER BY (tpep_pickup_datetime, PULocationID)
    """)

    for i in tqdm(range(0, len(df), BATCH_SIZE), desc="ClickHouse insert"):
        batch = df.iloc[i:i + BATCH_SIZE]
        client.insert_df(TABLE_NAME, batch)

    elapsed = time.time() - t0
    total   = client.command(f"SELECT COUNT(*) FROM benchmark.{TABLE_NAME}")
    print(f"\n[ClickHouse] tempo de ingestão: {elapsed:.2f}s | {total:,} registros")

    client.close()
    return elapsed


if __name__ == "__main__":
    ingest_clickhouse()