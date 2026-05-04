"""
seed_db.py — Создать и заполнить базу данных сотрудников.

Запускать из директории backend/:
    python scripts/seed_db.py

Требует наличия DATABASE_URL в .env (backend/ или корень репозитория).
"""

import asyncio
import os
import sys
from datetime import date
from pathlib import Path

# Разрешить импорты из app/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

# ─────────────────────────────────────────────────────────────────────────────
# Схема
# ─────────────────────────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS departments (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS positions (
    id    SERIAL PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    grade VARCHAR(20)   -- junior | mid | senior | manager | director
);

CREATE TABLE IF NOT EXISTS workers (
    id            SERIAL PRIMARY KEY,
    first_name    VARCHAR(50)  NOT NULL,
    last_name     VARCHAR(50)  NOT NULL,
    department_id INTEGER      REFERENCES departments(id),
    position_id   INTEGER      REFERENCES positions(id),
    hire_date     DATE         NOT NULL,
    is_active     BOOLEAN      DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS salaries (
    id        SERIAL PRIMARY KEY,
    worker_id INTEGER        REFERENCES workers(id),
    year      INTEGER        NOT NULL,
    month     INTEGER        NOT NULL,
    amount    DECIMAL(10,2)  NOT NULL,
    UNIQUE(worker_id, year, month)
);

CREATE TABLE IF NOT EXISTS performance_reviews (
    id          SERIAL PRIMARY KEY,
    worker_id   INTEGER      REFERENCES workers(id),
    year        INTEGER      NOT NULL,
    quarter     INTEGER      NOT NULL,
    score       DECIMAL(3,1),
    reviewer_id INTEGER      REFERENCES workers(id),
    UNIQUE(worker_id, year, quarter)
);
"""

# ─────────────────────────────────────────────────────────────────────────────
# Тестовые данные
# ─────────────────────────────────────────────────────────────────────────────

DEPARTMENTS = ["IT", "HR", "Finance", "Security", "Marketing", "Engineering"]

# (title, grade, base_monthly_salary_2023)
POSITIONS = [
    ("Junior Developer",           "junior",   4500),
    ("Developer",                  "mid",      6500),
    ("Senior Developer",           "senior",   9000),
    ("DevOps Engineer",            "mid",      7200),
    ("Junior HR Specialist",       "junior",   3800),
    ("HR Specialist",              "mid",      5500),
    ("HR Manager",                 "manager",  8500),
    ("Financial Analyst",          "mid",      6200),
    ("Senior Financial Analyst",   "senior",   8800),
    ("Finance Manager",            "manager",  11000),
    ("Security Analyst",           "mid",      6800),
    ("Security Engineer",          "senior",   9500),
    ("Security Manager",           "manager",  12000),
    ("Marketing Specialist",       "mid",      5800),
    ("Digital Marketing Specialist","mid",     6100),
    ("Marketing Manager",          "manager",  9200),
    ("Junior Engineer",            "junior",   4800),
    ("Engineer",                   "mid",      7000),
    ("Senior Engineer",            "senior",   10000),
    ("Engineering Manager",        "manager",  13000),
]

# (first_name, last_name, department, position_title, hire_date)
WORKERS = [
    # ── IT (8 workers) ────────────────────────────────────────────────
    ("Frank",   "Davis",    "IT", "Senior Developer",    date(2018, 6, 1)),
    ("Grace",   "Lee",      "IT", "DevOps Engineer",     date(2019, 9, 14)),
    ("Henry",   "Wilson",   "IT", "Junior Developer",    date(2022, 3, 7)),
    ("Ivy",     "Taylor",   "IT", "Senior Developer",    date(2020, 1, 20)),
    ("Jack",    "Anderson", "IT", "Developer",           date(2021, 8, 11)),
    ("Kate",    "Martinez", "IT", "Junior Developer",    date(2023, 5, 16)),
    ("Liam",    "Garcia",   "IT", "DevOps Engineer",     date(2021, 2, 28)),
    ("Maya",    "Johnson",  "IT", "Developer",           date(2022, 10, 5)),
    # ── HR (4 workers) ────────────────────────────────────────────────
    ("Noah",    "Williams", "HR", "HR Manager",          date(2017, 4, 3)),
    ("Olivia",  "Brown",    "HR", "HR Specialist",       date(2019, 11, 25)),
    ("Paul",    "Jones",    "HR", "HR Specialist",       date(2021, 6, 14)),
    ("Quinn",   "Davis",    "HR", "Junior HR Specialist",date(2022, 9, 20)),
    # ── Finance (4 workers) ───────────────────────────────────────────
    ("Rachel",  "White",    "Finance", "Financial Analyst",        date(2018, 8, 12)),
    ("Samuel",  "Harris",   "Finance", "Senior Financial Analyst", date(2020, 3, 17)),
    ("Tina",    "Martin",   "Finance", "Finance Manager",          date(2016, 12, 1)),
    ("Uma",     "Thompson", "Finance", "Financial Analyst",        date(2023, 7, 25)),
    # ── Security (5 workers) ─────────────────────────────────────────
    ("Alice",   "Johnson",  "Security", "Security Manager",  date(2019, 3, 15)),
    ("Bob",     "Chen",     "Security", "Security Analyst",  date(2020, 7, 22)),
    ("Carol",   "Smith",    "Security", "Security Engineer", date(2021, 11, 5)),
    ("David",   "Kim",      "Security", "Security Analyst",  date(2022, 4, 18)),
    ("Emma",    "Brown",    "Security", "Security Analyst",  date(2023, 1, 30)),
    # ── Marketing (5 workers) ────────────────────────────────────────
    ("Victor",  "Garcia",   "Marketing", "Marketing Manager",           date(2019, 5, 8)),
    ("Wendy",   "Lee",      "Marketing", "Marketing Specialist",         date(2020, 10, 14)),
    ("Xavier",  "Moore",    "Marketing", "Marketing Specialist",         date(2021, 12, 1)),
    ("Yara",    "Jackson",  "Marketing", "Digital Marketing Specialist", date(2022, 8, 22)),
    ("Zack",    "Taylor",   "Marketing", "Marketing Specialist",         date(2023, 3, 11)),
    # ── Engineering (5 workers) ──────────────────────────────────────
    ("Aaron",   "Wilson",   "Engineering", "Engineering Manager", date(2017, 7, 19)),
    ("Bella",   "Anderson", "Engineering", "Senior Engineer",     date(2019, 2, 6)),
    ("Chris",   "Martinez", "Engineering", "Senior Engineer",     date(2020, 11, 30)),
    ("Diana",   "Roberts",  "Engineering", "Engineer",            date(2022, 6, 27)),
    ("Ethan",   "Thompson", "Engineering", "Junior Engineer",     date(2023, 9, 4)),
]

# Yearly salary growth per grade
GRADE_RAISE = {
    "junior":   0.05,   # 5 % per year
    "mid":      0.04,
    "senior":   0.035,
    "manager":  0.03,
    "director": 0.025,
}

# Performance scores (worker first+last name → {year: {quarter: score}})
# Anything not listed defaults to 3.5
SCORES: dict[str, dict[int, dict[int, float]]] = {
    "Alice Johnson":  {2023: {1:4.8,2:4.9,3:4.7,4:4.9}, 2024: {1:5.0,2:4.8,3:4.9,4:5.0}, 2025: {1:4.9,2:5.0,3:None,4:None}},
    "Carol Smith":    {2023: {1:4.5,2:4.6,3:4.4,4:4.7}, 2024: {1:4.8,2:4.7,3:4.9,4:4.8}, 2025: {1:4.9,2:4.8,3:None,4:None}},
    "Bob Chen":       {2023: {1:3.8,2:3.9,3:4.0,4:4.1}, 2024: {1:4.2,2:4.3,3:4.1,4:4.2}, 2025: {1:4.3,2:4.2,3:None,4:None}},
    "Frank Davis":    {2023: {1:4.5,2:4.6,3:4.5,4:4.7}, 2024: {1:4.8,2:4.7,3:4.8,4:4.9}, 2025: {1:5.0,2:4.9,3:None,4:None}},
    "Aaron Wilson":   {2023: {1:4.7,2:4.8,3:4.6,4:4.8}, 2024: {1:4.9,2:4.8,3:4.9,4:5.0}, 2025: {1:5.0,2:4.9,3:None,4:None}},
    "Tina Martin":    {2023: {1:4.6,2:4.5,3:4.7,4:4.6}, 2024: {1:4.7,2:4.8,3:4.7,4:4.8}, 2025: {1:4.8,2:4.9,3:None,4:None}},
}


def _monthly_salary(base: float, grade: str, year: int, month: int) -> float:
    """Apply yearly raise and a small monthly variation (±2 %)."""
    raise_rate = GRADE_RAISE.get(grade, 0.04)
    # 2023 is the base year
    years_elapsed = year - 2023
    annual = base * ((1 + raise_rate) ** years_elapsed)
    # tiny deterministic variation by month
    variation = 1 + (((month * 7 + years_elapsed * 3) % 5) - 2) * 0.005
    return round(annual * variation, 2)


async def seed(conn: asyncpg.Connection) -> None:
    print("Creating schema …")
    await conn.execute(DDL)

    print("Clearing existing data …")
    for table in ("performance_reviews", "salaries", "workers", "positions", "departments"):
        await conn.execute(f"TRUNCATE {table} RESTART IDENTITY CASCADE")

    # ── departments ──────────────────────────────────────────────────────────
    dept_ids: dict[str, int] = {}
    for name in DEPARTMENTS:
        row = await conn.fetchrow(
            "INSERT INTO departments (name) VALUES ($1) RETURNING id", name
        )
        dept_ids[name] = row["id"]
    print(f"  Inserted {len(dept_ids)} departments.")

    # ── positions ────────────────────────────────────────────────────────────
    pos_ids: dict[str, int] = {}
    pos_grades: dict[str, str] = {}
    pos_bases: dict[str, float] = {}
    for title, grade, base in POSITIONS:
        row = await conn.fetchrow(
            "INSERT INTO positions (title, grade) VALUES ($1, $2) RETURNING id",
            title, grade,
        )
        pos_ids[title] = row["id"]
        pos_grades[title] = grade
        pos_bases[title] = float(base)
    print(f"  Inserted {len(pos_ids)} positions.")

    # ── workers ──────────────────────────────────────────────────────────────
    worker_ids: dict[str, int] = {}   # "First Last" → id
    for first, last, dept, pos_title, hire in WORKERS:
        row = await conn.fetchrow(
            "INSERT INTO workers (first_name, last_name, department_id, position_id, hire_date) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING id",
            first, last, dept_ids[dept], pos_ids[pos_title], hire,
        )
        worker_ids[f"{first} {last}"] = row["id"]
    print(f"  Inserted {len(worker_ids)} workers.")

    # ── salaries (monthly, 2023-2025) ────────────────────────────────────────
    salary_rows: list[tuple] = []
    for first, last, _, pos_title, hire in WORKERS:
        wid = worker_ids[f"{first} {last}"]
        grade = pos_grades[pos_title]
        base  = pos_bases[pos_title]
        for year in (2023, 2024, 2025):
            for month in range(1, 13):
                # Skip months before hire date
                if date(year, month, 1) < date(hire.year, hire.month, 1):
                    continue
                # Don't generate future salaries (beyond April 2026 = now)
                if year == 2025 and month > 12:
                    continue
                amount = _monthly_salary(base, grade, year, month)
                salary_rows.append((wid, year, month, amount))

    await conn.executemany(
        "INSERT INTO salaries (worker_id, year, month, amount) VALUES ($1, $2, $3, $4) "
        "ON CONFLICT DO NOTHING",
        salary_rows,
    )
    print(f"  Inserted {len(salary_rows)} salary records.")

    # ── performance reviews (quarterly, 2023-2025) ───────────────────────────
    review_rows: list[tuple] = []
    # Find a default reviewer per worker (their manager if same dept, else worker 1)
    manager_by_dept: dict[str, int] = {}
    for first, last, dept, pos_title, _ in WORKERS:
        if pos_grades[pos_title] == "manager":
            manager_by_dept[dept] = worker_ids[f"{first} {last}"]

    for first, last, dept, pos_title, hire in WORKERS:
        wid = worker_ids[f"{first} {last}"]
        name = f"{first} {last}"
        reviewer = manager_by_dept.get(dept, list(worker_ids.values())[0])
        for year in (2023, 2024, 2025):
            max_q = 2 if year == 2025 else 4  # only Q1–Q2 available in 2025
            for q in range(1, max_q + 1):
                # Skip quarters entirely before hire
                approx_quarter_start = date(year, (q - 1) * 3 + 1, 1)
                if approx_quarter_start < date(hire.year, hire.month, 1):
                    continue
                score = (
                    SCORES.get(name, {}).get(year, {}).get(q)
                    if name in SCORES
                    else None
                )
                if score is None:
                    # deterministic default based on worker+year+quarter
                    score = round(3.0 + ((wid + year + q) % 20) / 10, 1)
                    score = min(5.0, score)
                review_rows.append((wid, year, q, score, reviewer if reviewer != wid else None))

    await conn.executemany(
        "INSERT INTO performance_reviews (worker_id, year, quarter, score, reviewer_id) "
        "VALUES ($1, $2, $3, $4, $5) ON CONFLICT DO NOTHING",
        review_rows,
    )
    print(f"  Inserted {len(review_rows)} performance review records.")
    print("Done.")


async def main() -> None:
    url = settings.DATABASE_URL.strip()
    if not url:
        print(
            "ERROR: DATABASE_URL is not set.\n"
            "Add it to .env:\n"
            "  DATABASE_URL=postgresql://user:password@localhost:5432/echarts_workers"
        )
        sys.exit(1)

    print(f"Connecting to {url!r} …")
    conn = await asyncpg.connect(url)
    try:
        await seed(conn)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
