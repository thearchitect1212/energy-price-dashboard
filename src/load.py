"""Check the raw price files and load them into a SQLite database."""
import sqlite3
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw")
DB_PATH = Path("data/prices.db")
PRICE_SERIES = ["wti", "brent", "natural_gas"]


def clean_prices(df: pd.DataFrame, series: str) -> tuple[pd.DataFrame, dict]:
    """Return a clean (date, series, price) table and a record of what was fixed."""
    df = df.copy()
    df.columns = ["date", "price"]
    df["date"] = pd.to_datetime(df["date"])
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    rows_in = len(df)

    missing = int(df["price"].isna().sum())
    df = df.dropna(subset=["price"])

    duplicates = int(df["date"].duplicated().sum())
    df = df.drop_duplicates(subset="date", keep="last")

    # A negative price is real, not an error: WTI closed at -$36.98 on 2020-04-20.
    # Keep those rows, but count them so the report can call them out.
    non_positive = int((df["price"] <= 0).sum())

    df = df.sort_values("date")
    quality = {
        "series": series,
        "rows_in": rows_in,
        "rows_loaded": len(df),
        "missing_prices_dropped": missing,
        "duplicate_dates_dropped": duplicates,
        "zero_or_negative_prices_kept": non_positive,
        "longest_gap_days": int(df["date"].diff().dt.days.max()),
        "first_date": df["date"].min().strftime("%Y-%m-%d"),
        "last_date": df["date"].max().strftime("%Y-%m-%d"),
    }
    df["series"] = series
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return df[["date", "series", "price"]], quality


def clean_cpi(df: pd.DataFrame) -> pd.DataFrame:
    """Return (month, cpi) with month as YYYY-MM."""
    df = df.rename(columns={"Date": "date", "Index": "cpi"})
    df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
    return df[["month", "cpi"]].dropna()


def load(raw_dir: Path = RAW_DIR, db_path: Path = DB_PATH) -> pd.DataFrame:
    """Rebuild the database. Returns the data-quality table."""
    tables, quality = [], []
    for series in PRICE_SERIES:
        clean, q = clean_prices(pd.read_csv(raw_dir / f"{series}.csv"), series)
        tables.append(clean)
        quality.append(q)
    prices = pd.concat(tables, ignore_index=True)
    quality = pd.DataFrame(quality)
    cpi = clean_cpi(pd.read_csv(raw_dir / "cpi.csv"))

    with sqlite3.connect(db_path) as conn:
        prices.to_sql("prices", conn, if_exists="replace", index=False)
        cpi.to_sql("cpi", conn, if_exists="replace", index=False)
        quality.to_sql("data_quality", conn, if_exists="replace", index=False)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_prices ON prices (series, date)")
    return quality


if __name__ == "__main__":
    print(load().to_string(index=False))
