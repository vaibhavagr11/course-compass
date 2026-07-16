import os, json, re, duckdb
from openai import OpenAI
from dotenv import load_dotenv
from semantic import list_metrics, run_metric

load_dotenv()
client = OpenAI(base_url="https://openrouter.ai/api/v1",
                api_key=os.environ["OPENROUTER_API_KEY"])
MODEL = "openai/gpt-4o-mini"

_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "db", "kellogg.duckdb")
con = duckdb.connect(_DB, read_only=True)
AREAS = [r[0] for r in con.execute("SELECT DISTINCT area FROM dim_course ORDER BY 1").fetchall()]
con.close()

METRIC_DOC = "\n".join(f"- {n}: {d}" for n, d in list_metrics().items())

SYS = f"""You translate a user's question into a SEMANTIC REQUEST against a governed metrics layer.
You do NOT write SQL. You only choose from these defined metrics:
{METRIC_DOC}

Optional 'area' filter must be one of these codes, or null: {AREAS}

Reply with ONLY a JSON object:
{{"metric": <metric name>, "area": <area code or null>, "order": "desc" or "asc", "limit": <int>}}
Use "desc" for most/best/highest, "asc" for least/worst/lowest. Default limit 1."""

def nl_to_request(question, temperature=1.0):
    r = client.chat.completions.create(
        model=MODEL, temperature=temperature,
        messages=[{"role": "system", "content": SYS},
                  {"role": "user", "content": question}])
    txt = re.sub(r"```json|```", "", r.choices[0].message.content).strip()
    return json.loads(txt)

def answer(question):
    req = nl_to_request(question)
    df, _ = run_metric(req["metric"], area=req.get("area"),
                       order=req.get("order", "desc"), limit=req.get("limit") or 1)
    top = df.iloc[0]["course_title"] if len(df) else "(none)"
    return req, top

QUESTIONS = ["Which course is the most competitive?", "What is the best course?"]
N = 5
for q in QUESTIONS:
    print("\n" + "=" * 70 + f"\nQ: {q}\n" + "=" * 70)
    tops = []
    for i in range(1, N + 1):
        try:
            req, top = answer(q)
            print(f"Run {i}: request={req} -> {top}")
            tops.append(top)
        except Exception as e:
            print(f"Run {i}: ERROR {e}"); tops.append("ERROR")
    print(f"DISTINCT answers: {len(set(tops))} / {N}")