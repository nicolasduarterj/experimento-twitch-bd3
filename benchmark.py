# benchmark.py
import time, statistics, psutil, csv
from pymongo import MongoClient
from cassandra.cluster import Cluster
from cassandra.io.asyncorereactor import AsyncoreConnection
from cassandra.policies import DCAwareRoundRobinPolicy, AddressTranslator
from neo4j import GraphDatabase
import psycopg

PG_DSN = "host=localhost port=5432 dbname=twitch user=benchmark password=benchmark123"
RUNS = 10

class DockerTranslator(AddressTranslator):
    def translate(self, addr):
        return "127.0.0.1"

def measure(fn, label, db_name, results):
    timings = []
    for i in range(RUNS):
        start = time.perf_counter()
        fn()
        elapsed = time.perf_counter() - start
        if i > 0:
            timings.append(elapsed * 1000)
    mean = statistics.mean(timings)
    stdev = statistics.stdev(timings) if len(timings) > 1 else 0
    print(f"  [{db_name}] {label}: {mean:.1f}ms ± {stdev:.1f}ms")
    results.append({"db": db_name, "query": label,
                    "mean_ms": round(mean, 2), "stdev_ms": round(stdev, 2)})

def run_benchmarks():
    results = []

    # ── MongoDB ───────────────────────────────────────────────────────────────
    print("\n=== MongoDB ===")
    try:
        client = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=5000)
        db = client["twitch"]
        db.command("ping")  # fail fast if not reachable

        measure(lambda: db.users.find_one({"_id": 42}),
                "point_lookup", "MongoDB", results)
        measure(lambda: db.users.count_documents({"language": "EN", "affiliate": True}),
                "filtered_scan_EN_affiliates", "MongoDB", results)
        measure(lambda: list(db.users.aggregate([
            {"$group": {"_id": "$language", "avg": {"$avg": "$views"}}},
            {"$sort": {"avg": -1}}
        ])), "avg_views_by_language", "MongoDB", results)
        measure(lambda: list(db.users.find({}, {"views": 1}).sort("views", -1).limit(10)),
                "top10_by_views", "MongoDB", results)
        measure(lambda: list(db.edges.find({"src": 42}, {"dst": 1, "_id": 0})),
                "1hop_neighbors", "MongoDB", results)
        measure(lambda: list(db.edges.aggregate([
            {"$match": {"src_id": 100}},
            {"$lookup": {
                "from": "edges",
                "localField": "dest_id",
                "foreignField": "src_id",
                "as": "next_hop"
            }},
            {"$unwind": "$next_hop"},
            {"$match": {"next_hop.dest_id": 50000}},
            {"$project": {"_id": 0, "node_a": "$src_id", "node_x": "$dest_id", "node_b": "$next_hop.dest_id"}},
            {"$limit": 1}
        ])), "shortest_indirect_path", "MongoDB", results)
        client.close()
    except Exception as e:
        print(f"  [MongoDB] SKIPPED — {e}")

    # ── ScyllaDB ──────────────────────────────────────────────────────────────
    print("\n=== ScyllaDB ===")
    try:
        cluster = Cluster(
            ["127.0.0.1"],
            port=9042,
            load_balancing_policy=DCAwareRoundRobinPolicy(local_dc="datacenter1"),
            connection_class=AsyncoreConnection,
            connect_timeout=30,
            idle_heartbeat_interval=60,
            idle_heartbeat_timeout=30,
        )
        session = cluster.connect("twitch")
        session.default_timeout = 60

        measure(lambda: session.execute(
            "SELECT * FROM users WHERE numeric_id = %s", [42]).one(),
            "point_lookup", "ScyllaDB", results)
        measure(lambda: list(session.execute(
            "SELECT * FROM users_by_language WHERE language = %s", ["EN"])),
            "filtered_scan_EN_affiliates", "ScyllaDB", results)
        measure(lambda: list(session.execute(
            "SELECT dst_id FROM adjacency WHERE src_id = %s", [42])),
            "1hop_neighbors", "ScyllaDB", results)
        cluster.shutdown()
    except Exception as e:
        print(f"  [ScyllaDB] SKIPPED — {e}")

    # ── Neo4j ─────────────────────────────────────────────────────────────────
    print("\n=== Neo4j ===")
    try:
        driver = GraphDatabase.driver("bolt://localhost:7687",
                                      auth=("neo4j", "benchmark123"))
        driver.verify_connectivity()  # fail fast if not reachable

        with driver.session() as s:
            measure(lambda: s.run("MATCH (u:User {numeric_id:42}) RETURN u").single(),
                    "point_lookup", "Neo4j", results)
            measure(lambda: s.run(
                "MATCH (u:User {language:'EN', affiliate:true}) RETURN count(u)"
                ).single()[0],
                "filtered_scan_EN_affiliates", "Neo4j", results)
            measure(lambda: s.run(
                "MATCH (u:User) RETURN u.language, avg(u.views) ORDER BY avg(u.views) DESC"
                ).data(),
                "avg_views_by_language", "Neo4j", results)
            measure(lambda: s.run(
                "MATCH (u:User) RETURN u.numeric_id, u.views ORDER BY u.views DESC LIMIT 10"
                ).data(),
                "top10_by_views", "Neo4j", results)
            measure(lambda: s.run(
                "MATCH (u:User {numeric_id:42})-[:FOLLOWS]-(n) RETURN n.numeric_id"
                ).data(),
                "1hop_neighbors", "Neo4j", results)
            measure(lambda: s.run(
                "MATCH (u:User {numeric_id:42})-[:FOLLOWS*2]-(n) "
                "RETURN DISTINCT n.numeric_id"
                ).data(),
                "2hop_neighbors", "Neo4j", results)
            measure(lambda: s.run("""
                MATCH p = shortestPath(
                  (a:User {numeric_id:100})-[:FOLLOWS*]-(b:User {numeric_id:50000}))
                RETURN length(p)
                """).single(),
                "shortest_path", "Neo4j", results)
            measure(lambda: s.run("""
                MATCH (a:User {numeric_id:100})-[:FOLLOWS]->(x)-[:FOLLOWS]->(b:User {numeric_id:50000})
                RETURN a.numeric_id AS node_a, x.numeric_id AS node_x, b.numeric_id AS node_b
                LIMIT 1
                """).single(),
                "shortest_indirect_path", "Neo4j", results)
        driver.close()
    except Exception as e:
        print(f"  [Neo4j] SKIPPED — {e}")

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    print("\n=== PostgreSQL ===")
    try:
        conn = psycopg.connect(PG_DSN)
        cur  = conn.cursor()

        measure(lambda: cur.execute("SELECT * FROM users WHERE id = %s", (42,)) or cur.fetchone(),
                "point_lookup", "PostgreSQL", results)
        measure(lambda: cur.execute(
            "SELECT COUNT(*) FROM users WHERE language = %s AND affiliate = %s", ("EN", True)
            ) or cur.fetchone(),
            "filtered_scan_EN_affiliates", "PostgreSQL", results)
        measure(lambda: cur.execute(
            "SELECT language, AVG(views) AS avg_views FROM users "
            "GROUP BY language ORDER BY avg_views DESC"
            ) or cur.fetchall(),
            "avg_views_by_language", "PostgreSQL", results)
        measure(lambda: cur.execute(
            "SELECT id, views FROM users ORDER BY views DESC LIMIT 10"
            ) or cur.fetchall(),
            "top10_by_views", "PostgreSQL", results)
        measure(lambda: cur.execute("""
            SELECT dst_id AS neighbor FROM friendships WHERE src_id = %s
            UNION
            SELECT src_id AS neighbor FROM friendships WHERE dst_id = %s
            """, (42, 42)) or cur.fetchall(),
            "1hop_neighbors", "PostgreSQL", results)
        measure(lambda: cur.execute("""
            WITH hop1 AS (
                SELECT dst_id AS nbr FROM friendships WHERE src_id = %s
                UNION
                SELECT src_id AS nbr FROM friendships WHERE dst_id = %s
            ),
            hop2 AS (
                SELECT f.dst_id AS nbr FROM friendships f JOIN hop1 h ON f.src_id = h.nbr
                UNION
                SELECT f.src_id AS nbr FROM friendships f JOIN hop1 h ON f.dst_id = h.nbr
            )
            SELECT DISTINCT nbr FROM hop2
            WHERE nbr <> %s AND nbr NOT IN (SELECT nbr FROM hop1)
            """, (42, 42, 42)) or cur.fetchall(),
            "2hop_neighbors", "PostgreSQL", results)
        measure(lambda: cur.execute("""
            SELECT e1.src_id AS node_a, e1.dst_id AS node_x, e2.dst_id AS node_b
            FROM friendships e1
            JOIN friendships e2 ON e1.dst_id = e2.src_id
            WHERE e1.src_id = %s AND e2.dst_id = %s
            LIMIT 1
            """, (100, 50000)) or cur.fetchone(),
            "shortest_indirect_path", "PostgreSQL", results)

        cur.close()
        conn.close()
    except Exception as e:
        print(f"  [PostgreSQL] SKIPPED — {e}")

    # ── Save results ──────────────────────────────────────────────────────────
    with open("benchmark_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["db", "query", "mean_ms", "stdev_ms"])
        w.writeheader()
        w.writerows(results)
    print("\nResults saved to benchmark_results.csv")
    return results

if __name__ == "__main__":
    run_benchmarks()
