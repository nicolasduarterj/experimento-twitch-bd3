import duckdb
import clickhouse_connect
from elasticsearch import Elasticsearch
import time
import pandas as pd
import time, statistics, csv

RUNS = 10

PEAK_DEMAND_LABEL = "peak_demand"
AIRPORT_DYNAMICS_LABEL = "airport_dynamics"
TIPPING_BEHAVIOR_LABEL = "tipping_behavior"
ROUTE_PROFITABILITY_LABEL = "route_profitability"

def measure(fn, label, db_name, results, is_remote=False):
    timings = []
    
    for i in range(RUNS):
        if is_remote:
            elapsed_ms = fn()
        else:
            start = time.perf_counter()
            fn()
            elapsed_ms = (time.perf_counter() - start) * 1000
            
        if i > 0:
            timings.append(elapsed_ms)
            
    mean = statistics.mean(timings)
    stdev = statistics.stdev(timings) if len(timings) > 1 else 0
    
    print(f"  [{db_name}] {label}: {mean:.1f}ms ± {stdev:.1f}ms")
    
    results.append({
        "db": db_name, 
        "query": label,
        "mean_ms": round(mean, 2), 
        "stdev_ms": round(stdev, 2)
    })

def run_ch_and_get_time(client, query_str):
    result = client.query(query_str)
    
    if result.summary and 'elapsed_ns' in result.summary:
        return float(result.summary['elapsed_ns']) / 1_000_000.0
        
    return 0.0

def run_benchmarks():
    results = []

    print("\n=== DuckDB ===")
    DUCKDB_LABEL = "DuckDB"
    con_duck = duckdb.connect("./nyc_taxi.duckdb")

    measure(lambda: con_duck.execute(
        """SELECT 
                dayofweek(tpep_pickup_datetime) AS dia_semana,
                hour(tpep_pickup_datetime) AS hora_dia,
                COUNT(*) AS total_viagens,
                avg(trip_distance) AS distancia_media,
                avg(total_amount) AS ticket_medio
            FROM yellow_taxi
            GROUP BY 
                dia_semana, 
                hora_dia
            ORDER BY 
                total_viagens DESC
            LIMIT 20;
        """).fetchall(),
        PEAK_DEMAND_LABEL, DUCKDB_LABEL, results)
    

    measure(lambda: con_duck.execute(
        """SELECT 
                DOLocationID AS zona_destino,
                COUNT(*) AS volume_viagens,
                AVG(trip_distance) AS distancia_media,
                AVG(total_amount) AS custo_medio_passageiro
            FROM yellow_taxi
            WHERE RatecodeID IN (2, 3)
            GROUP BY DOLocationID
            ORDER BY volume_viagens DESC
            LIMIT 15;
        """).fetchall(),
        AIRPORT_DYNAMICS_LABEL, DUCKDB_LABEL, results)
    
    measure(lambda: con_duck.execute(
        """SELECT 
                passenger_count,
                COUNT(*) AS total_viagens_cartao,
                AVG(tip_amount) AS gorjeta_media_absoluta,
                (SUM(tip_amount) / NULLIF(SUM(fare_amount), 0)) * 100 AS percentual_medio_gorjeta
            FROM yellow_taxi
            WHERE payment_type = 1
            AND fare_amount > 0
            AND passenger_count IS NOT NULL
            GROUP BY passenger_count
            ORDER BY passenger_count ASC;
        """).fetchall(),
        TIPPING_BEHAVIOR_LABEL, DUCKDB_LABEL, results)
    
    measure(lambda: con_duck.execute(
        """WITH MetricasCorredor AS (
            SELECT
                PULocationID AS zona_origem,
                DOLocationID AS zona_destino,
                COUNT(*) AS volume_viagens,
                SUM(trip_distance) AS distancia_total_milhas,
                AVG(trip_distance) AS distancia_media,
                AVG(tip_amount) AS gorjeta_media,
                SUM(
                    total_amount
                    - COALESCE(mta_tax, 0)
                    - COALESCE(tolls_amount, 0)
                    - COALESCE(improvement_surcharge, 0)
                    - COALESCE(congestion_surcharge, 0)
                    - COALESCE(airport_fee, 0)
                    - COALESCE(cbd_congestion_fee, 0)
                ) AS receita_liquida_total
            FROM yellow_taxi
            WHERE trip_distance > 0.5
              AND total_amount > 0
              AND passenger_count > 0
            GROUP BY
                zona_origem,
                zona_destino
            HAVING volume_viagens > 100
        ),
        Rentabilidade AS (
            SELECT
                zona_origem,
                zona_destino,
                volume_viagens,
                distancia_media,
                gorjeta_media,
                (receita_liquida_total / distancia_total_milhas) AS lucro_por_milha,
                RANK() OVER (
                    PARTITION BY zona_origem
                    ORDER BY (receita_liquida_total / distancia_total_milhas) DESC
                ) AS rank_lucratividade
            FROM MetricasCorredor
        )
        SELECT
            zona_origem,
            rank_lucratividade,
            zona_destino,
            volume_viagens,
            ROUND(distancia_media, 2) AS dist_media_milhas,
            ROUND(lucro_por_milha, 2) AS lucro_por_milha_usd,
            ROUND(gorjeta_media, 2) AS gorjeta_media_usd
        FROM Rentabilidade
        WHERE rank_lucratividade <= 3
        ORDER BY
            zona_origem ASC,
            rank_lucratividade ASC
        """).fetchall(),
        ROUTE_PROFITABILITY_LABEL, DUCKDB_LABEL, results)

    con_duck.close()

    print("\n=== ClickHouse ===")
    CLICKHOUSE_LABEL = "ClickHouse"

    ch_client = clickhouse_connect.get_client(
        host="localhost",
        port=8123,
        username="benchmark",
        password="benchmark123",
        database="benchmark",
    )

    measure(lambda: run_ch_and_get_time(ch_client, """
        SELECT 
            toDayOfWeek(tpep_pickup_datetime) AS dia_semana,
            toHour(tpep_pickup_datetime) AS hora_dia,
            count() AS total_viagens,
            avg(trip_distance) AS distancia_media,
            avg(total_amount) AS ticket_medio
        FROM benchmark.yellow_taxi
        GROUP BY 
            dia_semana, 
            hora_dia
        ORDER BY 
            total_viagens DESC
        LIMIT 20
        """
    ),
        PEAK_DEMAND_LABEL, CLICKHOUSE_LABEL, results, True)
    
    measure(lambda: run_ch_and_get_time(ch_client, """
        SELECT 
            DOLocationID AS zona_destino,
            count() AS volume_viagens,
            avg(trip_distance) AS distancia_media,
            avg(total_amount) AS custo_medio_passageiro
        FROM yellow_taxi
        WHERE RatecodeID IN (2, 3)
        GROUP BY 
            zona_destino
        ORDER BY 
            volume_viagens DESC
        LIMIT 15
        """
    ),
        AIRPORT_DYNAMICS_LABEL, CLICKHOUSE_LABEL, results, True)
    
    measure(lambda: run_ch_and_get_time(ch_client, """
        SELECT 
            passenger_count,
            count() AS total_viagens_cartao,
            avg(tip_amount) AS gorjeta_media_absoluta,
            (sum(tip_amount) / sum(fare_amount)) * 100 AS percentual_medio_gorjeta
        FROM yellow_taxi
        WHERE payment_type = 1
          AND fare_amount > 0
          AND passenger_count IS NOT NULL
        GROUP BY 
            passenger_count
        ORDER BY 
            passenger_count ASC
        """
    ),
        TIPPING_BEHAVIOR_LABEL, CLICKHOUSE_LABEL, results, True)
    
    measure(lambda: run_ch_and_get_time(ch_client, """
        WITH MetricasCorredor AS (
            SELECT
                PULocationID AS zona_origem,
                DOLocationID AS zona_destino,
                count() AS volume_viagens,
                sum(trip_distance) AS distancia_total_milhas,
                avg(trip_distance) AS distancia_media,
                avg(tip_amount) AS gorjeta_media,
                sum(
                    total_amount
                    - coalesce(mta_tax, 0)
                    - coalesce(tolls_amount, 0)
                    - coalesce(improvement_surcharge, 0)
                    - coalesce(congestion_surcharge, 0)
                    - coalesce(airport_fee, 0)
                    - coalesce(cbd_congestion_fee, 0)
                ) AS receita_liquida_total
            FROM benchmark.yellow_taxi
            WHERE trip_distance > 0.5
              AND total_amount > 0
              AND passenger_count > 0
            GROUP BY
                zona_origem,
                zona_destino
            HAVING volume_viagens > 100
        ),
        Rentabilidade AS (
            SELECT
                zona_origem,
                zona_destino,
                volume_viagens,
                distancia_media,
                gorjeta_media,
                (receita_liquida_total / distancia_total_milhas) AS lucro_por_milha,
                rank() OVER (
                    PARTITION BY zona_origem
                    ORDER BY (receita_liquida_total / distancia_total_milhas) DESC
                ) AS rank_lucratividade
            FROM MetricasCorredor
        )
        SELECT
            zona_origem,
            rank_lucratividade,
            zona_destino,
            volume_viagens,
            round(distancia_media, 2) AS dist_media_milhas,
            round(lucro_por_milha, 2) AS lucro_por_milha_usd,
            round(gorjeta_media, 2) AS gorjeta_media_usd
        FROM Rentabilidade
        WHERE rank_lucratividade <= 3
        ORDER BY
            zona_origem ASC,
            rank_lucratividade ASC
        """
    ),
        ROUTE_PROFITABILITY_LABEL, CLICKHOUSE_LABEL, results, True)
    
    ch_client.close()

    print("\n=== ElasticSearch ===")
    ELASTICSEARCH_LABEL = "ElasticSearch"
    INDEX_NAME = "yellow_taxi"
    es_client = Elasticsearch("http://localhost:9200")

    measure(lambda: es_client.search(
        index=INDEX_NAME,
        request_cache=False,
        body={
            "size": 0,
            "aggs": {
                "agrupamento_dia_hora": {
                "terms": {
                    "script": {
                        "source": "doc['tpep_pickup_datetime'].value.dayOfWeekEnum.getValue() + '_' + doc['tpep_pickup_datetime'].value.hour",
                        "lang": "painless"
                    },
                    "size": 20,
                    "order": {
                        "_count": "desc"
                    }
                },
                "aggs": {
                    "distancia_media": {
                        "avg": {
                            "field": "trip_distance"
                        }
                    },
                    "ticket_medio": {
                        "avg": {
                            "field": "total_amount"
                        }
                    }
                }
                }
            }
        }
    )["took"],
        PEAK_DEMAND_LABEL, ELASTICSEARCH_LABEL, results, is_remote=True)
    
    measure(lambda: es_client.search(
        index=INDEX_NAME,
        request_cache=False,
        body={
            "size": 0,
            "query": {
                "terms": {
                    "RatecodeID": [2, 3]
                }
            },
            "aggs": {
                "agrupamento_zona_destino": {
                    "terms": {
                        "field": "DOLocationID",
                        "size": 15
                    },
                    "aggs": {
                        "distancia_media": {
                            "avg": {
                                "field": "trip_distance"
                            }
                        },
                        "custo_medio_passageiro": {
                            "avg": {
                                "field": "total_amount"
                            }
                        }
                    }
                }
            }
        }
    )["took"], 
        AIRPORT_DYNAMICS_LABEL, ELASTICSEARCH_LABEL, results, is_remote=True)
    
    measure(lambda: es_client.search(
        index=INDEX_NAME,
        request_cache=False,
        body={
            "size": 0,
            "query": {
                "bool": {
                    "filter": [
                        {
                        "term": {
                            "payment_type": 1
                        }
                        },
                        {
                        "range": {
                            "fare_amount": {
                            "gt": 0
                            }
                        }
                        },
                        {
                        "exists": {
                            "field": "passenger_count"
                        }
                        }
                    ]
                }
            },
            "aggs": {
                "passenger_count_groups": {
                    "terms": {
                        "field": "passenger_count",
                        "order": {
                            "_key": "asc"
                        },
                        "size": 100
                    },
                    "aggs": {
                        "gorjeta_media_absoluta": {
                            "avg": {
                                "field": "tip_amount"
                            }
                        },
                        "sum_tip_amount": {
                            "sum": {
                                "field": "tip_amount"
                            }
                        },
                        "sum_fare_amount": {
                            "sum": {
                                "field": "fare_amount"
                            }
                        },
                        "percentual_medio_gorjeta": {
                            "bucket_script": {
                                "buckets_path": {
                                    "totalTip": "sum_tip_amount",
                                    "totalFare": "sum_fare_amount"
                                },
                                "script": "params.totalFare > 0 ? (params.totalTip / params.totalFare) * 100 : null"
                            }
                        }
                    }
                }
            }
        }
    )["took"],
        TIPPING_BEHAVIOR_LABEL, ELASTICSEARCH_LABEL, results, is_remote=True)

    measure(lambda: es_client.search(
        index=INDEX_NAME,
        request_cache=False,
        body={
            "size": 0,
            "query": {
                "bool": {
                "filter": [
                    {
                    "range": {
                        "trip_distance": { "gt": 0.5 }
                    }
                    },
                    {
                    "range": {
                        "total_amount": { "gt": 0 }
                    }
                    },
                    {
                    "range": {
                        "passenger_count": { "gt": 0 }
                    }
                    }
                ]
                }
            },
            "aggs": {
                "zonas_origem": {
                "terms": {
                    "field": "PULocationID",
                    "order": { "_key": "asc" },
                    "size": 10000
                },
                "aggs": {
                    "zonas_destino": {
                    "terms": {
                        "field": "DOLocationID",
                        "min_doc_count": 101,
                        "size": 10000
                    },
                    "aggs": {
                        "distancia_total_milhas": {
                        "sum": { "field": "trip_distance" }
                        },
                        "distancia_media": {
                        "avg": { "field": "trip_distance" }
                        },
                        "gorjeta_media": {
                        "avg": { "field": "tip_amount" }
                        },
                        "receita_liquida_total": {
                        "sum": {
                            "script": {
                            "source": "double total = doc['total_amount'].size() > 0 ? doc['total_amount'].value : 0; double mta = doc['mta_tax'].size() > 0 ? doc['mta_tax'].value : 0; double tolls = doc['tolls_amount'].size() > 0 ? doc['tolls_amount'].value : 0; double imp = doc['improvement_surcharge'].size() > 0 ? doc['improvement_surcharge'].value : 0; double cong = doc['congestion_surcharge'].size() > 0 ? doc['congestion_surcharge'].value : 0; double air = doc['Airport_fee'].size() > 0 ? doc['Airport_fee'].value : 0; double cbd = doc['cbd_congestion_fee'].size() > 0 ? doc['cbd_congestion_fee'].value : 0; return total - mta - tolls - imp - cong - air - cbd;"
                            }
                        }
                        },
                        "lucro_por_milha": {
                        "bucket_script": {
                            "buckets_path": {
                            "receita": "receita_liquida_total",
                            "distancia": "distancia_total_milhas"
                            },
                            "script": "params.distancia > 0 ? params.receita / params.distancia : null"
                        }
                        },
                        "top_3_lucratividade": {
                        "bucket_sort": {
                            "sort": [
                            { "lucro_por_milha": { "order": "desc" } }
                            ],
                            "size": 3
                        }
                        }
                    }
                    }
                }
                }
            }
        }
    )["took"],
        ROUTE_PROFITABILITY_LABEL, ELASTICSEARCH_LABEL, results, is_remote=True)
    
    with open("benchmark_olap_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["db", "query", "mean_ms", "stdev_ms"])
        w.writeheader()
        w.writerows(results)
    print("\nResults saved to benchmark_olap_results.csv")
    return results

if __name__ == "__main__":
    run_benchmarks()