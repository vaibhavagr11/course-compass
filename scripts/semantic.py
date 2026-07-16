import os, yaml, duckdb

_HERE = os.path.dirname(os.path.abspath(__file__))
_YML  = os.path.join(_HERE, "..", "semantic_layer", "metrics.yml")
_DB   = os.path.join(_HERE, "..", "db", "kellogg.duckdb")

with open(_YML) as f:
    MODEL = yaml.safe_load(f)
METRICS = MODEL["metrics"]

# Chronological rank for a "Season Year" term string.
TERM_RANK = ("CAST(split_part(term, ' ', 2) AS INT) * 100 + "
             "CASE split_part(term, ' ', 1) "
             "WHEN 'Winter' THEN 1 WHEN 'Spring' THEN 4 "
             "WHEN 'Summer' THEN 7 WHEN 'Fall' THEN 10 END")

def list_metrics():
    return {n: " ".join(m["description"].split()) for n, m in METRICS.items()}

def compile_metric(metric, area=None, order="desc", limit=None):
    if metric not in METRICS:
        raise ValueError(f"Unknown metric '{metric}'. Known: {list(METRICS)}")
    m = METRICS[metric]
    measure, agg, weight = m["measure"], m["aggregation"], m.get("weight")
    where = (" WHERE " + " AND ".join(m["filters"])) if m.get("filters") else ""
    sel = f"{measure} AS m" + (f", {weight} AS w" if weight else "")
    if agg == "avg":
        value_expr = "AVG(m)"
    elif agg == "response_weighted_avg":
        value_expr = "SUM(m * w) / NULLIF(SUM(w), 0)"
    else:
        raise ValueError(f"Unsupported aggregation '{agg}'")
    area_filter = f" WHERE c.area = '{area}'" if area else ""
    order_dir = "DESC" if order == "desc" else "ASC"
    lim = f" LIMIT {int(limit)}" if limit else ""
    sql = f"""
    WITH base AS (
        SELECT course_code, term, {sel}, {TERM_RANK} AS trank
        FROM {m['source']}{where}
    ),
    latest AS (SELECT course_code, MAX(trank) AS mt FROM base GROUP BY course_code),
    scoped AS (
        SELECT b.* FROM base b JOIN latest l
        ON b.course_code = l.course_code AND b.trank = l.mt
    ),
    agg AS (SELECT course_code, {value_expr} AS value FROM scoped GROUP BY course_code)
    SELECT course_code, c.course_title, c.area, ROUND(a.value, 2) AS {metric}
    FROM agg a JOIN dim_course c USING (course_code){area_filter}
    ORDER BY a.value {order_dir}, course_code ASC{lim}
    """
    return " ".join(sql.split())

def run_metric(metric, **kw):
    sql = compile_metric(metric, **kw)
    con = duckdb.connect(_DB, read_only=True)
    try:
        return con.execute(sql).fetchdf(), sql
    finally:
        con.close()