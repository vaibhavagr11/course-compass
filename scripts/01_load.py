import duckdb

con = duckdb.connect("db/kellogg.duckdb")

files = {
    "schedule": "data/raw/schedule.csv",
    "bidstats": "data/raw/bidstats.csv",
    "tces":     "data/raw/tces.csv",
}

for table, path in files.items():
    con.execute(f"DROP TABLE IF EXISTS {table}")
    con.execute(
        f"CREATE TABLE {table} AS "
        f"SELECT * FROM read_csv_auto('{path}', header=true, all_varchar=true)"
    )
    n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"loaded {table:10s} {n:>6,} rows")

overlap = con.execute("""
    SELECT (SELECT COUNT(DISTINCT "Course Name") FROM schedule) AS schedule_courses,
           (SELECT COUNT(DISTINCT CourseName)    FROM bidstats) AS bidstats_courses,
           (SELECT COUNT(DISTINCT CourseName)    FROM tces)     AS tce_courses,
           (SELECT COUNT(*) FROM (
                SELECT DISTINCT CourseName FROM bidstats
                INTERSECT
                SELECT DISTINCT CourseName FROM tces
           )) AS bid_tce_shared_courses
""").fetchdf()
print(overlap.to_string(index=False))

con.close()
print("done -> db/kellogg.duckdb")