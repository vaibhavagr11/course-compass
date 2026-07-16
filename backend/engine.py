import os, re, json, duckdb, yaml
from openai import OpenAI
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB   = os.path.join(ROOT, "db", "kellogg.duckdb")
YML  = os.path.join(ROOT, "semantic_layer", "metrics.yml")

load_dotenv(os.path.join(ROOT, ".env"))
client = OpenAI(base_url="https://openrouter.ai/api/v1",
                api_key=os.environ["OPENROUTER_API_KEY"])
MODEL = "openai/gpt-4o-mini"

with open(YML) as f:
    METRICS = yaml.safe_load(f)["metrics"]

TERM_RANK = ("CAST(split_part(term, ' ', 2) AS INT) * 100 + "
             "CASE split_part(term, ' ', 1) "
             "WHEN 'Winter' THEN 1 WHEN 'Spring' THEN 4 "
             "WHEN 'Summer' THEN 7 WHEN 'Fall' THEN 10 END")

def metric_defs():
    return {n: " ".join(m["description"].split()) for n, m in METRICS.items()}

def compile_metric(metric, area=None, order="desc", limit=None):
    m = METRICS[metric]
    measure, agg, weight = m["measure"], m["aggregation"], m.get("weight")
    where = (" WHERE " + " AND ".join(m["filters"])) if m.get("filters") else ""
    sel = f"{measure} AS m" + (f", {weight} AS w" if weight else "")
    value_expr = "AVG(m)" if agg == "avg" else "SUM(m * w) / NULLIF(SUM(w), 0)"
    area_filter = f" WHERE c.area = '{area}'" if area else ""
    order_dir = "DESC" if order == "desc" else "ASC"
    lim = f" LIMIT {int(limit)}" if limit else ""
    sql = f"""
    WITH base AS (
        SELECT course_code, term, {sel}, {TERM_RANK} AS trank
        FROM {m['source']}{where}),
    latest AS (SELECT course_code, MAX(trank) AS mt FROM base GROUP BY course_code),
    scoped AS (SELECT b.* FROM base b JOIN latest l
               ON b.course_code=l.course_code AND b.trank=l.mt),
    agg AS (SELECT course_code, {value_expr} AS value FROM scoped GROUP BY course_code)
    SELECT course_code, c.course_title, c.area, ROUND(a.value,2) AS {metric}
    FROM agg a JOIN dim_course c USING (course_code){area_filter}
    ORDER BY a.value {order_dir}, course_code ASC{lim}"""
    return " ".join(sql.split())

def _rows(df, n=10):
    return json.loads(df.head(n).to_json(orient="records"))

def _llm(messages, temperature=1.0):
    return client.chat.completions.create(
        model=MODEL, temperature=temperature, messages=messages
    ).choices[0].message.content

# ---------------- V1: naive text-to-SQL ----------------
SCHEMA = """DuckDB tables:
dim_course(course_code, course_title, area)
fct_bids(course_code, course_title, term, section, program, faculty, campus, phase_type,
         phase_num, num_bids, closing_cost, seats_available, total_seats, enrolled, waitlist, open_seats)
fct_tce(course_code, course_title, term, section, course_owner, faculty, campus, score_class,
        score_instructor, score_learning, score_difficulty, score_global, score_examples,
        score_workload, total_responses, num_enrollees)"""

def v1_ask(question):
    prompt = (f"You are a data analyst. Using this schema, write ONE DuckDB SQL query that "
              f"answers the question. Return ONLY SQL.\n{SCHEMA}\nQuestion: {question}\nSQL:")
    sql = re.sub(r"```sql|```", "", _llm([{"role": "user", "content": prompt}])).strip()
    con = duckdb.connect(DB, read_only=True)
    try:
        df = con.execute(sql).fetchdf()
        ans = None
        if len(df):
            for k in ("course_title", "course_code"):
                if k in df.columns:
                    ans = str(df.iloc[0][k]); break
            if ans is None:
                ans = str(df.iloc[0, 0])
        return {"answer": ans, "sql": sql, "table": _rows(df), "error": None}
    except Exception as e:
        return {"answer": None, "sql": sql, "table": [], "error": str(e)}
    finally:
        con.close()

# ---------------- V2: semantic layer ----------------
_c = duckdb.connect(DB, read_only=True)
AREAS = [r[0] for r in _c.execute("SELECT DISTINCT area FROM dim_course ORDER BY 1").fetchall()]
_c.close()
_DOC = "\n".join(f"- {n}: {d}" for n, d in metric_defs().items())
SYS = f"""Translate the question into a semantic request. Do NOT write SQL. Metrics:
{_DOC}
Optional 'area' is one of these codes or null (infer from subject: marketing->MKTG,
finance->FINC, accounting->ACCT, strategy->STRT): {AREAS}
Reply ONLY JSON: {{"metric":..,"area":..,"order":"desc" or "asc","limit":1}}.
Use desc for most/best/highest, asc for least/worst/lowest."""

def v2_ask(question):
    req = None
    try:
        raw = _llm([{"role": "system", "content": SYS},
                    {"role": "user", "content": question}])
        req = json.loads(re.sub(r"```json|```", "", raw).strip())
        sql = compile_metric(req["metric"], area=req.get("area"),
                             order=req.get("order", "desc"), limit=req.get("limit") or 5)
        con = duckdb.connect(DB, read_only=True)
        df = con.execute(sql).fetchdf(); con.close()
        ans = str(df.iloc[0]["course_title"]) if len(df) else None
        return {"answer": ans, "request": req, "sql": sql,
                "definition": metric_defs().get(req["metric"]), "table": _rows(df), "error": None}
    except Exception as e:
        return {"answer": None, "request": req, "sql": None,
                "definition": None, "table": [], "error": str(e)}

def consistency(question, mode, runs=5):
    fn = v1_ask if mode == "v1" else v2_ask
    answers = [(fn(question).get("answer") or "ERROR") for _ in range(runs)]
    return {"answers": answers, "distinct": len(set(answers))}