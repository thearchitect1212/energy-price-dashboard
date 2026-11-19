-- Metrics for the energy price dashboard.
-- Each query is named with a "-- name:" line so metrics.py can run it by name.

-- name: latest
-- Latest price per series, compared with about a week, a month and a year earlier.
-- Markets close on weekends and holidays, so "a week ago" means the last
-- trading day on or before that date.
WITH last_day AS (
    SELECT series, MAX(date) AS date FROM prices GROUP BY series
)
SELECT p.series,
       p.date,
       p.price,
       (SELECT price FROM prices x WHERE x.series = p.series
          AND x.date <= DATE(p.date, '-7 days')  ORDER BY x.date DESC LIMIT 1) AS price_week_ago,
       (SELECT price FROM prices x WHERE x.series = p.series
          AND x.date <= DATE(p.date, '-30 days') ORDER BY x.date DESC LIMIT 1) AS price_month_ago,
       (SELECT price FROM prices x WHERE x.series = p.series
          AND x.date <= DATE(p.date, '-1 year')  ORDER BY x.date DESC LIMIT 1) AS price_year_ago,
       (SELECT MAX(price) FROM prices x WHERE x.series = p.series
          AND x.date > DATE(p.date, '-1 year')) AS high_52w,
       (SELECT MIN(price) FROM prices x WHERE x.series = p.series
          AND x.date > DATE(p.date, '-1 year')) AS low_52w
FROM prices p
JOIN last_day d ON d.series = p.series AND d.date = p.date;

-- name: daily
-- Every trading day with its day-over-day change and 30- and 90-day moving averages.
SELECT date,
       series,
       price,
       price - LAG(price) OVER w                                    AS change,
       ROUND(100.0 * (price - LAG(price) OVER w) / LAG(price) OVER w, 2) AS pct_change,
       ROUND(AVG(price) OVER (w ROWS BETWEEN 29 PRECEDING AND CURRENT ROW), 2) AS avg_30d,
       ROUND(AVG(price) OVER (w ROWS BETWEEN 89 PRECEDING AND CURRENT ROW), 2) AS avg_90d
FROM prices
WINDOW w AS (PARTITION BY series ORDER BY date)
ORDER BY series, date;

-- name: yearly
SELECT SUBSTR(date, 1, 4)   AS year,
       series,
       ROUND(AVG(price), 2) AS avg_price,
       MIN(price)           AS low,
       MAX(price)           AS high,
       COUNT(*)             AS trading_days
FROM prices
GROUP BY year, series
ORDER BY year, series;

-- name: spread
-- Brent minus WTI on days when both traded. A wide gap means US crude is cheap
-- compared with the global price.
SELECT b.date,
       b.price                      AS brent,
       w.price                      AS wti,
       ROUND(b.price - w.price, 2)  AS spread
FROM prices b
JOIN prices w ON w.date = b.date AND w.series = 'wti'
WHERE b.series = 'brent'
ORDER BY b.date;

-- name: biggest_moves
-- The ten largest one-day moves in WTI by dollars per barrel.
-- Dollars, not percent, because a percent change means nothing across a negative price.
SELECT date, price, ROUND(change, 2) AS change
FROM (
    SELECT date, price, price - LAG(price) OVER (ORDER BY date) AS change
    FROM prices
    WHERE series = 'wti'
)
WHERE change IS NOT NULL
ORDER BY ABS(change) DESC
LIMIT 10;

-- name: real_wti
-- Monthly average WTI in today's dollars: price x (latest CPI / CPI that month).
WITH monthly AS (
    SELECT SUBSTR(date, 1, 7) AS month, AVG(price) AS avg_price
    FROM prices
    WHERE series = 'wti'
    GROUP BY month
),
latest_cpi AS (
    SELECT cpi FROM cpi ORDER BY month DESC LIMIT 1
)
SELECT m.month,
       ROUND(m.avg_price, 2)                                  AS nominal,
       ROUND(m.avg_price * (SELECT cpi FROM latest_cpi) / c.cpi, 2) AS real
FROM monthly m
JOIN cpi c ON c.month = m.month
ORDER BY m.month;
