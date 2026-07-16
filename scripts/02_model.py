import duckdb

con = duckdb.connect("db/kellogg.duckdb")

# ---- fact: bids (grain = course x term x section x phase) ----
con.execute("DROP TABLE IF EXISTS fct_bids")
con.execute("""
CREATE TABLE fct_bids AS
SELECT
    CourseName                             AS course_code,
    "Course Title"                         AS course_title,
    Term                                   AS term,
    SectionName                            AS section,
    Program                                AS program,
    TRIM(Faculty)                          AS faculty,
    Campus                                 AS campus,
    TRIM(REPLACE(Phase, Term || ' ', ''))  AS phase_type,
    CASE
        WHEN Phase LIKE '%Bid Phase 1%'     THEN 1
        WHEN Phase LIKE '%Bid Phase 2%'     THEN 2
        WHEN Phase LIKE '%Bid Phase 3%'     THEN 3
        WHEN Phase LIKE '%Pay What You Bid%' THEN 4
    END                                    AS phase_num,
    TRY_CAST("Number of Bids"  AS INT)     AS num_bids,
    TRY_CAST("Closing Cost"    AS DOUBLE)  AS closing_cost,
    TRY_CAST("Seats Available" AS INT)     AS seats_available,
    TRY_CAST("Total Seats"     AS INT)     AS total_seats,
    TRY_CAST(Enrolled          AS INT)     AS enrolled,
    TRY_CAST(Waitlist          AS INT)     AS waitlist,
    TRY_CAST("Open Seats"      AS INT)     AS open_seats
FROM bidstats
""")

# ---- fact: TCE ratings (grain = course x term x section) ----
con.execute("DROP TABLE IF EXISTS fct_tce")
con.execute("""
CREATE TABLE fct_tce AS
SELECT
    CourseName                        AS course_code,
    "Course Title"                    AS course_title,
    Term                              AS term,
    SectionName                       AS section,
    CourseOwner                       AS course_owner,
    TRIM(Faculty)                     AS faculty,
    Campus                            AS campus,
    TRY_CAST("Class"              AS DOUBLE) AS score_class,
    TRY_CAST("Instructor Overall" AS DOUBLE) AS score_instructor,
    TRY_CAST("Learning"           AS DOUBLE) AS score_learning,
    TRY_CAST("Difficulty"         AS DOUBLE) AS score_difficulty,
    TRY_CAST("Global"             AS DOUBLE) AS score_global,
    TRY_CAST("Examples"           AS DOUBLE) AS score_examples,
    TRY_CAST("WorkLoad"           AS DOUBLE) AS score_workload,
    TRY_CAST("Total Responses"    AS INT)    AS total_responses,
    TRY_CAST("Number Of Enrollees" AS INT)   AS num_enrollees
FROM tces
""")

# ---- dim: course (one row per course code) ----
con.execute("DROP TABLE IF EXISTS dim_course")
con.execute("""
CREATE TABLE dim_course AS
WITH allc AS (
    SELECT CourseName AS course_code, "Course Title" AS course_title FROM bidstats
    UNION SELECT CourseName, "Course Title" FROM tces
    UNION SELECT "Course Name", "Course Title" FROM schedule
)
SELECT course_code,
       ANY_VALUE(course_title)        AS course_title,
       SPLIT_PART(course_code, '-', 1) AS area
FROM allc
GROUP BY course_code
""")

# ---- verify ----
for t in ["dim_course", "fct_bids", "fct_tce"]:
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"{t:12s} {n:>6,} rows")

print("\nPhase distribution in fct_bids:")
print(con.execute("SELECT phase_num, phase_type, COUNT(*) n FROM fct_bids "
                  "GROUP BY 1,2 ORDER BY 1").fetchdf().to_string(index=False))

print("\nSample: ACCT-430-0 Fall 2023, Phase 1 bids joined to ratings:")
print(con.execute("""
    SELECT b.section, b.closing_cost, b.num_bids,
           t.score_global, t.score_difficulty, t.total_responses
    FROM fct_bids b
    JOIN fct_tce t USING (course_code, term, section)
    WHERE b.phase_num = 1 AND b.course_code = 'ACCT-430-0' AND b.term = 'Fall 2023'
    ORDER BY b.section
""").fetchdf().to_string(index=False))

con.close()
print("\ndone -> clean tables built")