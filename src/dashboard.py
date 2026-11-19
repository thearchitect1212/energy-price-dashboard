"""Build the interactive dashboard (docs/index.html) and reports/summary.md."""
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from metrics import ALERT_PCT, LABELS, run_all

OUT_HTML = Path("docs/index.html")
OUT_MD = Path("reports/summary.md")

# One fixed color per series, used everywhere that series appears.
COLOR = {"wti": "#2a78d6", "brent": "#eb6834", "natural_gas": "#1baf7a"}
MUTED = "#8a8985"
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e7e6e2", "#fcfcfb"


def base_layout(fig: go.Figure, y_title: str, range_buttons: bool = True) -> go.Figure:
    fig.update_layout(
        template="none", height=380, margin=dict(l=56, r=16, t=16, b=40),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, hovermode="x unified",
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=13, color=INK_2),
        legend=dict(orientation="h", y=1.12, x=0, font=dict(color=INK)),
        yaxis=dict(title=y_title, gridcolor=GRID, zeroline=False),
        xaxis=dict(showgrid=False, linecolor=GRID),
    )
    if range_buttons:
        fig.update_xaxes(rangeselector=dict(
            x=1, xanchor="right", y=1.12, bgcolor=SURFACE, activecolor=GRID,
            buttons=[dict(count=1, label="1Y", step="year", stepmode="backward"),
                     dict(count=5, label="5Y", step="year", stepmode="backward"),
                     dict(count=10, label="10Y", step="year", stepmode="backward"),
                     dict(label="All", step="all")]))
    return fig


def last_years(df: pd.DataFrame, years: int, col: str = "date") -> list[str]:
    """Initial x-axis window: the last N years of the data."""
    end = pd.to_datetime(df[col]).max()
    return [(end - pd.DateOffset(years=years)).strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")]


def crude_chart(daily: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for series in ["wti", "brent"]:
        d = daily[daily["series"] == series]
        fig.add_trace(go.Scatter(x=d["date"], y=d["price"], name=LABELS[series], mode="lines",
                                 line=dict(color=COLOR[series], width=2),
                                 hovertemplate="$%{y:.2f}"))
    fig = base_layout(fig, "Dollars per barrel")
    fig.update_xaxes(range=last_years(daily, 5))
    return fig


def gas_chart(daily: pd.DataFrame) -> go.Figure:
    d = daily[daily["series"] == "natural_gas"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["date"], y=d["price"], name="Daily price", mode="lines",
                             line=dict(color=COLOR["natural_gas"], width=2), hovertemplate="$%{y:.2f}"))
    fig.add_trace(go.Scatter(x=d["date"], y=d["avg_90d"], name="90-day average", mode="lines",
                             line=dict(color=MUTED, width=2, dash="dot"), hovertemplate="$%{y:.2f}"))
    fig = base_layout(fig, "Dollars per million BTU")
    fig.update_xaxes(range=last_years(d, 5))
    return fig


def spread_chart(spread: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Scatter(x=spread["date"], y=spread["spread"], mode="lines",
                               line=dict(color=COLOR["brent"], width=2),
                               hovertemplate="$%{y:.2f}", name="Brent minus WTI"))
    fig.add_hline(y=0, line_color=INK_2, line_width=1)
    fig = base_layout(fig, "Dollars per barrel")
    fig.update_layout(showlegend=False)
    fig.update_xaxes(range=last_years(spread, 5))
    return fig


def real_chart(real: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=real["month"], y=real["real"], name="In today's dollars", mode="lines",
                             line=dict(color=COLOR["wti"], width=2), hovertemplate="$%{y:.2f}"))
    fig.add_trace(go.Scatter(x=real["month"], y=real["nominal"], name="Price at the time", mode="lines",
                             line=dict(color=MUTED, width=2, dash="dot"), hovertemplate="$%{y:.2f}"))
    return base_layout(fig, "Dollars per barrel, monthly average", range_buttons=False)


def money(value: float) -> str:
    """Format dollars with the minus sign before the dollar sign: -$36.98."""
    return f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"


def arrow(value: float) -> str:
    return "▲" if value > 0 else "▼" if value < 0 else "–"


def tiles(latest: pd.DataFrame) -> str:
    cards = []
    for r in latest.itertuples():
        flag = (f'<div class="flag">⚠ Moved more than {ALERT_PCT:.0f}% in a week</div>'
                if r.alert else "")
        cards.append(f"""
      <div class="tile">
        <div class="tile-name"><span class="dot" style="background:{COLOR[r.series]}"></span>{escape(r.label)}</div>
        <div class="tile-value">${r.price:,.2f}<span class="unit"> {r.unit.split('/')[1]}</span></div>
        <div class="tile-changes">
          <span>{arrow(r.week_pct)} {abs(r.week_pct)}% week</span>
          <span>{arrow(r.month_pct)} {abs(r.month_pct)}% month</span>
          <span>{arrow(r.year_pct)} {abs(r.year_pct)}% year</span>
        </div>
        <div class="tile-range">52-week range ${r.low_52w:,.2f} to ${r.high_52w:,.2f}</div>
        {flag}
      </div>""")
    return "\n".join(cards)


def html_table(df: pd.DataFrame) -> str:
    return df.to_html(index=False, border=0, classes="data", justify="left")


def findings(r: dict[str, pd.DataFrame]) -> list[str]:
    """Plain-language findings computed from the data, not typed by hand."""
    latest = r["latest"].set_index("series")
    spread, real, quality = r["spread"], r["real_wti"], r["data_quality"].set_index("series")
    wti, gas = latest.loc["wti"], latest.loc["natural_gas"]
    spread_now, spread_avg = spread["spread"].iloc[-1], spread["spread"].tail(1260).mean()
    peak = real.loc[real["real"].idxmax()]
    worst = r["biggest_moves"].iloc[0]
    out = [
        f"WTI crude closed at ${wti.price:,.2f} a barrel on {wti.date}, "
        f"{'up' if wti.year_pct > 0 else 'down'} {abs(wti.year_pct)}% from a year earlier.",
        f"Natural gas closed at ${gas.price:,.2f}, "
        f"{'up' if gas.year_pct > 0 else 'down'} {abs(gas.year_pct)}% from a year earlier.",
        f"Brent costs ${spread_now:,.2f} more than WTI, compared with an average gap of "
        f"${spread_avg:,.2f} over the last five years of trading.",
        f"Adjusted for inflation, WTI peaked in {peak.month} at ${peak.real:,.2f} in today's dollars "
        f"(${peak.nominal:,.2f} at the time).",
        f"The largest one-day move in WTI was ${abs(worst.change):,.2f} on {worst.date}, "
        f"when the price closed at {money(worst.price)}.",
    ]
    alerts = r["latest"][r["latest"]["alert"]]
    if len(alerts):
        names = ", ".join(alerts["label"])
        out.append(f"Alert: {names} moved more than {ALERT_PCT:.0f}% in the last week.")
    else:
        out.append(f"No series moved more than {ALERT_PCT:.0f}% in the last week.")
    dropped = int(quality["missing_prices_dropped"].sum())
    out.append(f"Data checks dropped {dropped} row(s) with a missing price and kept "
               f"{int(quality['zero_or_negative_prices_kept'].sum())} real negative price.")
    return out


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Energy Price Dashboard</title>
<style>
  body {{ margin:0; background:#f4f3ef; color:{ink}; font-family:system-ui,-apple-system,"Segoe UI",sans-serif; line-height:1.45; }}
  main {{ max-width:1080px; margin:0 auto; padding:24px 16px 48px; }}
  h1 {{ font-size:26px; margin:0 0 4px; }}
  h2 {{ font-size:18px; margin:0 0 2px; }}
  .sub, .note {{ color:{ink2}; font-size:14px; margin:0 0 12px; }}
  .tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; margin:20px 0; }}
  .tile, .card {{ background:{surface}; border:1px solid {grid}; border-radius:10px; padding:16px; }}
  .card {{ margin:16px 0; overflow-x:auto; }}
  .tile-name {{ font-size:14px; color:{ink2}; }}
  .dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px; }}
  .tile-value {{ font-size:30px; font-weight:650; margin:4px 0; }}
  .unit {{ font-size:14px; font-weight:400; color:{ink2}; }}
  .tile-changes {{ display:flex; flex-wrap:wrap; gap:4px 14px; font-size:14px; }}
  .tile-range {{ font-size:13px; color:{ink2}; margin-top:6px; }}
  .flag {{ margin-top:8px; font-size:13px; font-weight:600; }}
  ul {{ margin:8px 0 0; padding-left:20px; }}
  table.data {{ border-collapse:collapse; width:100%; font-size:14px; }}
  table.data th, table.data td {{ text-align:left; padding:6px 10px; border-bottom:1px solid {grid}; white-space:nowrap; }}
  table.data th {{ color:{ink2}; font-weight:600; }}
  footer {{ color:{ink2}; font-size:13px; margin-top:24px; }}
</style>
</head>
<body>
<main>
  <h1>Energy Price Dashboard</h1>
  <p class="sub">Daily crude oil and natural gas prices. Data through {as_of}. Built with Python, SQL and Plotly.</p>

  <div class="tiles">{tiles}</div>

  <div class="card">
    <h2>What the data shows</h2>
    <ul>{findings}</ul>
  </div>

  <div class="card">
    <h2>Crude oil: WTI and Brent</h2>
    <p class="note">WTI is the US benchmark and Brent is the global one. Use the buttons to change the time range.</p>
    {crude}
  </div>

  <div class="card">
    <h2>Brent minus WTI</h2>
    <p class="note">How much more a barrel of Brent costs than a barrel of WTI. Above zero means US crude is cheaper.</p>
    {spread}
  </div>

  <div class="card">
    <h2>Natural gas</h2>
    <p class="note">Henry Hub daily price with its 90-day average, which smooths out short spikes.</p>
    {gas}
  </div>

  <div class="card">
    <h2>WTI adjusted for inflation</h2>
    <p class="note">Monthly average price restated in today's dollars using the US consumer price index.</p>
    {real}
  </div>

  <div class="card">
    <h2>Ten largest one-day moves in WTI</h2>
    <p class="note">Dollars per barrel.</p>
    {moves}
  </div>

  <div class="card">
    <h2>Average price by year</h2>
    {yearly}
  </div>

  <div class="card">
    <h2>Data checks</h2>
    <p class="note">What the pipeline found and fixed when it loaded each file.</p>
    {quality}
  </div>

  <footer>Sources: US Energy Information Administration prices and US Bureau of Labor Statistics CPI, via the
  open <a href="https://github.com/datasets">datasets</a> project. Prices are market benchmarks, not what a
  business pays at the pump.</footer>
</main>
</body>
</html>
"""


def yearly_wide(yearly: pd.DataFrame, years: int = 10) -> pd.DataFrame:
    wide = yearly.pivot(index="year", columns="series", values="avg_price")[list(LABELS)]
    wide.columns = [LABELS[c] for c in wide.columns]
    return wide.tail(years).iloc[::-1].reset_index().rename(columns={"year": "Year"})


def main() -> None:
    r = run_all()
    figs = {"crude": crude_chart(r["daily"]), "spread": spread_chart(r["spread"]),
            "gas": gas_chart(r["daily"]), "real": real_chart(r["real_wti"])}
    config = {"displayModeBar": False, "responsive": True}
    parts = {}
    for i, (name, fig) in enumerate(figs.items()):
        # Load the Plotly library once, from its CDN, with the first chart.
        parts[name] = fig.to_html(full_html=False, config=config,
                                  include_plotlyjs="cdn" if i == 0 else False)

    notes = findings(r)
    moves = r["biggest_moves"].rename(columns={"date": "Date", "price": "Close", "change": "Change"})
    quality = r["data_quality"].rename(columns=lambda c: c.replace("_", " ").capitalize())
    as_of = r["latest"]["date"].max()

    OUT_HTML.parent.mkdir(exist_ok=True)
    OUT_HTML.write_text(PAGE.format(
        ink=INK, ink2=INK_2, grid=GRID, surface=SURFACE, as_of=as_of,
        tiles=tiles(r["latest"]),
        findings="".join(f"<li>{escape(n)}</li>" for n in notes),
        moves=html_table(moves), yearly=html_table(yearly_wide(r["yearly"])),
        quality=html_table(quality), **parts))

    cols = ["label", "date", "price", "week_pct", "month_pct", "year_pct", "low_52w", "high_52w", "alert"]
    OUT_MD.parent.mkdir(exist_ok=True)
    OUT_MD.write_text("\n".join([
        "# Energy price summary", "", f"Data through {as_of}.", "",
        "## What the data shows", "", *[f"- {n}" for n in notes], "",
        "## Latest prices", "", r["latest"][cols].to_markdown(index=False), "",
        "## Ten largest one-day moves in WTI", "", moves.to_markdown(index=False), "",
        "## Average price by year", "", yearly_wide(r["yearly"]).to_markdown(index=False), "",
        "## Data checks", "", r["data_quality"].to_markdown(index=False), ""]))
    print(f"Wrote {OUT_HTML} and {OUT_MD}")


if __name__ == "__main__":
    main()
