import os, re, duckdb
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(base_url="https://openrouter.ai/api/v1",
                api_key=os.environ["OPENROUTER_API_KEY"])
MODEL = "openai/gpt-4o-mini"   # any OpenRouter model works; this one is cheap

# Raw schema only — NO definition of "competitive", "best", or "rating".
SCHEMA = """
DuckDB tables of Kellogg MBA course data:

dim_course(course_code, course_title, area)
fct_bids(course_code, course_title, term, section, program, faculty, campus,
         phase_type, phase_num, num_bids, closing_cost, seats_available,
         total_seats, enrolled, waitlist, open_seats)
fct_tce(course_code, course_title, term, section, course_owner, faculty, campus,
        score_class, score_instructor, score_learning, score_difficulty,
        score_global, score_examples, score_workload, total_responses, num_enrollees)
"""

def ask_sql(question, temperature=1.0):
    prompt = (f"You are a data analyst. Using this schema, write ONE DuckDB SQL query "
              f"that answers the question. Return ONLY SQL, no prose, no markdown.\n"
              f"{SCHEMA}\nQuestion: {question}\nSQL:")
    r = client.chat.completions.create(
        model=MODEL, temperature=temperature,
        messages=[{"role": "user", "content": prompt}])
    sql = r.choices[0].message.content.strip()
    return re.sub(r"```sql|```", "", sql).strip()

def run_sql(con, sql):
    try:
        return con.execute(sql).fetchdf(), None
    except Exception as e:
        return None, str(e)

def first_answer(df):
    for k in ("course_title", "course_code"):
        if k in df.columns and len(df):
            return str(df.iloc[0][k])
    return str(df.iloc[0, 0]) if len(df) else "(empty)"

con = duckdb.connect("db/kellogg.duckdb")
QUESTIONS = [
    "Which course is the most competitive?",
    "What is the best course?",
]
N = 5
for q in QUESTIONS:
    print("\n" + "=" * 74)
    print("Q:", q)
    print("=" * 74)
    answers = []
    for i in range(1, N + 1):
        sql = ask_sql(q)
        df, err = run_sql(con, sql)
        print(f"\n--- Run {i} ---")
        print("SQL:", " ".join(sql.split())[:300])
        if err:
            print("  -> ERROR:", err[:120]); answers.append("ERROR")
        else:
            ans = first_answer(df)
            print("  -> Top answer:", ans); answers.append(ans)
    print(f"\nRESULT for '{q}':")
    print("  answers across", N, "runs:", answers)
    print("  DISTINCT answers:", len(set(answers)), "/", N)

con.close()