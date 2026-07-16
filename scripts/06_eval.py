import os, re, json, duckdb
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from openai import OpenAI
from dotenv import load_dotenv
from semantic import run_metric, list_metrics

load_dotenv()
client = OpenAI(base_url="https://openrouter.ai/api/v1",
                api_key=os.environ["OPENROUTER_API_KEY"])
MODEL = "openai/gpt-4o-mini"
_HERE = os.path.dirname(os.path.abspath(__file__))
_DB = os.path.join(_HERE, "..", "db", "kellogg.duckdb")

# ---- V1 naive text-to-SQL ----
SCHEMA = """DuckDB tables:
dim_course(course_code, course_title, area)
fct_bids(course_code, course_title, term, section, program, faculty, campus, phase_type,
         phase_num, num_bids, closing_cost, seats_available, total_seats, enrolled, waitlist, open_seats)
fct_tce(course_code, course_title, term, section, course_owner, faculty, campus, score_class,
        score_instructor, score_learning, score_difficulty, score_global, score_examples,
        score_workload, total_responses, num_enrollees)"""

def v1_answer(question, con):
    prompt = (f"You are a data analyst. Using this schema, write ONE DuckDB SQL query that "
              f"answers the question. Return ONLY SQL.\n{SCHEMA}\nQuestion: {question}\nSQL:")
    r = client.chat.completions.create(model=MODEL, temperature=1.0,
            messages=[{"role": "user", "content": prompt}])
    sql = re.sub(r"```sql|```", "", r.choices[0].message.content).strip()
    try:
        df = con.execute(sql).fetchdf()
    except Exception:
        return "ERROR"
    if len(df) == 0:
        return "(empty)"
    for k in ("course_title", "course_code"):
        if k in df.columns:
            return str(df.iloc[0][k]).strip()
    return str(df.iloc[0, 0]).strip()

# ---- V2 semantic agent ----
_c = duckdb.connect(_DB, read_only=True)
AREAS = [r[0] for r in _c.execute("SELECT DISTINCT area FROM dim_course ORDER BY 1").fetchall()]
_c.close()
METRIC_DOC = "\n".join(f"- {n}: {d}" for n, d in list_metrics().items())
SYS = f"""Translate the question into a semantic request. Do NOT write SQL. Metrics:
{METRIC_DOC}
Optional 'area' is one of these codes or null (infer from the subject: marketing->MKTG,
finance->FINC, accounting->ACCT, strategy->STRT): {AREAS}
Reply ONLY JSON: {{"metric":..,"area":..,"order":"desc" or "asc","limit":1}}.
Use desc for most/best/highest, asc for least/worst/lowest."""

def v2_answer(question):
    r = client.chat.completions.create(model=MODEL, temperature=1.0,
            messages=[{"role": "system", "content": SYS},
                      {"role": "user", "content": question}])
    try:
        req = json.loads(re.sub(r"```json|```", "", r.choices[0].message.content).strip())
        df, _ = run_metric(req["metric"], area=req.get("area"),
                           order=req.get("order", "desc"), limit=1)
        return str(df.iloc[0]["course_title"]).strip() if len(df) else "(empty)"
    except Exception:
        return "ERROR"

# ---- golden set: (question, metric, area, order) ----
GOLDEN = [
    ("Which course is the most competitive?",         "competitiveness", None,   "desc"),
    ("What is the best course?",                       "course_rating",   None,   "desc"),
    ("Which course is the least competitive?",         "competitiveness", None,   "asc"),
    ("What is the lowest rated course?",               "course_rating",   None,   "asc"),
    ("Which marketing course is the most competitive?","competitiveness", "MKTG", "desc"),
    ("What is the best finance course?",               "course_rating",   "FINC", "desc"),
    ("Which strategy course is the most competitive?", "competitiveness", "STRT", "desc"),
    ("What is the best accounting course?",            "course_rating",   "ACCT", "desc"),
]

N = 5
rows = []
con = duckdb.connect(_DB, read_only=True)
for q, metric, area, order in GOLDEN:
    exp = run_metric(metric, area=area, order=order, limit=1)[0]
    gold = str(exp.iloc[0]["course_title"]).strip() if len(exp) else "(empty)"
    v1s = [v1_answer(q, con) for _ in range(N)]
    v2s = [v2_answer(q) for _ in range(N)]
    score = lambda ans: (sum(a == gold for a in ans) / N, 1 if len(set(ans)) == 1 else 0)
    v1c, v1d = score(v1s); v2c, v2d = score(v2s)
    rows.append(dict(question=q, gold=gold, v1_correct=v1c, v1_det=v1d,
                     v2_correct=v2c, v2_det=v2d))
    print(f"\nQ: {q}\n  gold: {gold}")
    print(f"  V1: correct={v1c*100:.0f}% det={v1d}  {v1s}")
    print(f"  V2: correct={v2c*100:.0f}% det={v2d}  {v2s}")
con.close()

df = pd.DataFrame(rows)
v1c, v2c = df.v1_correct.mean()*100, df.v2_correct.mean()*100
v1d, v2d = df.v1_det.mean()*100, df.v2_det.mean()*100
print("\n" + "=" * 60)
print(f"OVERALL correctness: V1 {v1c:.0f}%  ->  V2 {v2c:.0f}%")
print(f"OVERALL determinism: V1 {v1d:.0f}%  ->  V2 {v2d:.0f}%")

reports = os.path.join(_HERE, "..", "reports")
os.makedirs(reports, exist_ok=True)
labels = ["Correctness\n(vs canonical)", "Determinism\n(same answer 5x)"]
x = range(len(labels)); w = 0.35
fig, ax = plt.subplots(figsize=(7, 4.5))
b1 = ax.bar([i - w/2 for i in x], [v1c, v1d], w, label="V1: naive text-to-SQL", color="#C0504D")
b2 = ax.bar([i + w/2 for i in x], [v2c, v2d], w, label="V2: semantic layer", color="#4472C4")
ax.set_ylim(0, 108); ax.set_ylabel("%"); ax.set_xticks(list(x)); ax.set_xticklabels(labels)
ax.set_title("AI course-analytics agent: before vs after a semantic layer\n"
             "Kellogg bid & TCE data — 8 questions x 5 runs")
ax.legend()
for bars in (b1, b2):
    for bar in bars:
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+1.5,
                f"{bar.get_height():.0f}%", ha="center", fontsize=10)
plt.tight_layout()
plt.savefig(os.path.join(reports, "before_after.png"), dpi=150)
df.to_csv(os.path.join(reports, "eval_results.csv"), index=False)
print("saved -> reports/before_after.png and reports/eval_results.csv")