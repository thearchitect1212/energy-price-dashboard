"""Tests use small made-up price tables, so they run without the internet."""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from load import clean_cpi, clean_prices
from metrics import add_changes, read_queries

SQL_PATH = Path(__file__).parent.parent / "sql" / "metrics.sql"


def test_clean_drops_missing_and_duplicate_rows():
    raw = pd.DataFrame({"Date": ["2024-01-02", "2024-01-03", "2024-01-03", "2024-01-04"],
                        "Price": [70.0, 71.0, 72.0, None]})
    clean, quality = clean_prices(raw, "wti")
    assert len(clean) == 2
    assert clean["price"].tolist() == [70.0, 72.0]  # keeps the last duplicate
    assert quality["missing_prices_dropped"] == 1
    assert quality["duplicate_dates_dropped"] == 1


def test_clean_keeps_negative_price_and_counts_it():
    raw = pd.DataFrame({"Date": ["2020-04-17", "2020-04-20"], "Price": [18.31, -36.98]})
    clean, quality = clean_prices(raw, "wti")
    assert clean["price"].min() == -36.98
    assert quality["zero_or_negative_prices_kept"] == 1


def test_clean_reports_longest_gap():
    raw = pd.DataFrame({"Date": ["2024-01-02", "2024-01-03", "2024-01-10"], "Price": [1, 2, 3]})
    _, quality = clean_prices(raw, "natural_gas")
    assert quality["longest_gap_days"] == 7


def test_alert_fires_only_above_threshold():
    latest = pd.DataFrame({
        "series": ["wti", "brent"], "date": ["2024-06-28"] * 2, "price": [106.0, 104.0],
        "price_week_ago": [100.0, 100.0], "price_month_ago": [100.0, 100.0],
        "price_year_ago": [53.0, 100.0]})
    out = add_changes(latest, alert_pct=5.0).set_index("series")
    assert out.loc["wti", "week_pct"] == 6.0
    assert bool(out.loc["wti", "alert"]) is True
    assert bool(out.loc["brent", "alert"]) is False
    assert out.loc["wti", "year_pct"] == 100.0


def make_db(tmp_path):
    """Ten trading days of WTI at 10, 11, ... 19 and Brent two dollars higher."""
    dates = pd.bdate_range("2024-01-01", periods=10).strftime("%Y-%m-%d")
    wti = pd.DataFrame({"date": dates, "series": "wti", "price": [10.0 + i for i in range(10)]})
    brent = wti.assign(series="brent", price=wti["price"] + 2)
    cpi = clean_cpi(pd.DataFrame({"Date": ["2023-12-01", "2024-01-01"], "Index": [100.0, 200.0]}))
    conn = sqlite3.connect(tmp_path / "t.db")
    pd.concat([wti, brent]).to_sql("prices", conn, index=False)
    cpi.to_sql("cpi", conn, index=False)
    return conn


def test_sql_moving_average_and_daily_change(tmp_path):
    conn = make_db(tmp_path)
    daily = pd.read_sql_query(read_queries(SQL_PATH)["daily"], conn)
    wti = daily[daily["series"] == "wti"].reset_index(drop=True)
    assert pd.isna(wti.loc[0, "change"])          # no previous day
    assert wti.loc[1, "change"] == 1.0
    assert wti.loc[1, "pct_change"] == 10.0       # 10 -> 11
    assert wti.loc[9, "avg_30d"] == 14.5          # mean of 10..19


def test_sql_spread_is_brent_minus_wti(tmp_path):
    conn = make_db(tmp_path)
    spread = pd.read_sql_query(read_queries(SQL_PATH)["spread"], conn)
    assert len(spread) == 10
    assert (spread["spread"] == 2.0).all()


def test_sql_latest_uses_last_trading_day_before_cutoff(tmp_path):
    conn = make_db(tmp_path)
    latest = pd.read_sql_query(read_queries(SQL_PATH)["latest"], conn).set_index("series")
    # Last day is Fri 2024-01-12 (price 19). Seven days earlier is Fri 2024-01-05 (price 14).
    assert latest.loc["wti", "date"] == "2024-01-12"
    assert latest.loc["wti", "price_week_ago"] == 14.0


def test_sql_real_price_uses_latest_cpi(tmp_path):
    conn = make_db(tmp_path)
    real = pd.read_sql_query(read_queries(SQL_PATH)["real_wti"], conn)
    # Only January 2024 has prices; its CPI is the latest, so real equals nominal.
    assert len(real) == 1
    assert real.loc[0, "real"] == real.loc[0, "nominal"] == 14.5
