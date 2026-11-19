"""Run the SQL metrics and add the weekly-move alert."""
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path("data/prices.db")
SQL_PATH = Path("sql/metrics.sql")
ALERT_PCT = 5.0  # flag a series when its price moved more than this in a week

LABELS = {"wti": "WTI crude oil", "brent": "Brent crude oil", "natural_gas": "Natural gas"}
UNITS = {"wti": "$/barrel", "brent": "$/barrel", "natural_gas": "$/MMBtu"}


def read_queries(sql_path: Path = SQL_PATH) -> dict[str, str]:
    """Split metrics.sql into {name: query} using the '-- name:' markers."""
    queries, name, lines = {}, None, []
    for line in sql_path.read_text().splitlines():
        if line.startswith("-- name:"):
            if name:
                queries[name] = "\n".join(lines).strip()
            name, lines = line.split(":", 1)[1].strip(), []
        elif name:
            lines.append(line)
    if name:
        queries[name] = "\n".join(lines).strip()
    return queries


def pct(new: float, old: float) -> float:
    return round(100.0 * (new - old) / old, 1)


def add_changes(latest: pd.DataFrame, alert_pct: float = ALERT_PCT) -> pd.DataFrame:
    """Add percent changes and the alert flag to the 'latest' query result."""
    out = latest.copy()
    out["week_pct"] = [pct(n, o) for n, o in zip(out["price"], out["price_week_ago"])]
    out["month_pct"] = [pct(n, o) for n, o in zip(out["price"], out["price_month_ago"])]
    out["year_pct"] = [pct(n, o) for n, o in zip(out["price"], out["price_year_ago"])]
    out["alert"] = out["week_pct"].abs() > alert_pct
    out["label"] = out["series"].map(LABELS)
    out["unit"] = out["series"].map(UNITS)
    order = {s: i for i, s in enumerate(LABELS)}
    return out.sort_values("series", key=lambda s: s.map(order)).reset_index(drop=True)


def run_all(db_path: Path = DB_PATH) -> dict[str, pd.DataFrame]:
    with sqlite3.connect(db_path) as conn:
        results = {name: pd.read_sql_query(sql, conn) for name, sql in read_queries().items()}
        results["data_quality"] = pd.read_sql_query("SELECT * FROM data_quality", conn)
    results["latest"] = add_changes(results["latest"])
    return results


if __name__ == "__main__":
    cols = ["label", "date", "price", "week_pct", "month_pct", "year_pct", "alert"]
    print(run_all()["latest"][cols].to_string(index=False))
