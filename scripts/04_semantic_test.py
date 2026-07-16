from semantic import run_metric, list_metrics

print("=== Metrics defined in the semantic layer ===")
for name, desc in list_metrics().items():
    print(f"\n[{name}] {desc}")

print("\n=== TOP 5 MOST COMPETITIVE COURSES (canonical) ===")
print(run_metric("competitiveness", limit=5)[0].to_string(index=False))

print("\n=== TOP 5 BEST COURSES (canonical) ===")
print(run_metric("course_rating", limit=5)[0].to_string(index=False))

print("\n=== Determinism check: 'most competitive' x5 ===")
ans = [run_metric("competitiveness", limit=1)[0].iloc[0]["course_title"] for _ in range(5)]
print(ans, "-> distinct:", len(set(ans)))