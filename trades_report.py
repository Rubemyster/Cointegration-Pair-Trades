"""
Trade monitor: renders a second, independent HTML report tracking the
pairs logged via trades.py.

Statistical scope, deliberately narrower than the main screener:

- No Benjamini-Hochberg here. BH corrects for testing many candidate
  pairs at once during discovery. Once you've already committed to a
  specific pair and logged a trade, you're not screening a basket
  anymore -- you're monitoring one relationship you already selected --
  so a multiple-testing correction doesn't apply.
- The hedge ratio (alpha, beta), half-life, and z-score window are held
  FIXED at whatever they were on the screener run you entered from
  (trades.py's entry_snapshot). This mirrors the main pipeline's own
  "static hedge ratio, no rolling re-estimation" choice for the trading
  window -- re-fitting on every check-in would mean the number on screen
  no longer reflects what you actually traded on.
- What DOES update on every run: the spread and z-score are recomputed
  against fresh price data through today (or through exit_date for a
  closed trade), using that fixed relationship. A fresh ADF test is also
  run on the post-entry spread, but purely as an informational "does this
  still look mean-reverting since I entered" flag -- not a pass/fail
  gate, and it never removes a trade from the report.

No P&L, no position sizing -- same diagnostic-only spirit as the main
screener's threshold flag.
"""

import json
import os
from datetime import datetime

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller

import config
from data_fetch import fetch_price_data
from cointegration import compute_spread
from zscore import rolling_mean_std
from trades import load_trades


def _clean(v):
    """Converts numpy/pandas scalars to plain JSON-safe Python values, NaN -> None."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return v


def _pair_history(ticker_a, ticker_b, start_date, end_date=None):
    """
    Fetches enough daily price history for one pair to cover a rolling-
    window lookback before start_date (so early post-entry points don't
    NaN out) through end_date. Independent of config.SECTORS -- this only
    ever fetches the two tickers a specific trade needs.
    """
    end_date = end_date or datetime.today()
    span_days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
    months = max(2, int(np.ceil(span_days / 30)) + 3)  # pad for weekends/holidays + window lookback
    return fetch_price_data([ticker_a, ticker_b], total_months=months, end_date=end_date)


def _status_label(latest_z, threshold, has_data):
    if not has_data:
        return "no_data"
    if latest_z is None or (isinstance(latest_z, float) and np.isnan(latest_z)):
        return "insufficient_history"
    return "diverging" if abs(latest_z) > threshold else "in_range"


def build_trade_entry(trade, prices, z_threshold):
    """
    Computes current status for one trade, using its FIXED entry_snapshot
    relationship applied to fresh price data. See module docstring for why
    the relationship isn't re-fit here.
    """
    ticker_a, ticker_b = trade["ticker_a"], trade["ticker_b"]
    snap = trade["entry_snapshot"]
    alpha, beta, window = (
        snap.get("intercept_alpha"), snap.get("hedge_ratio_beta"), snap.get("zscore_window"),
    )

    has_data = (
        alpha is not None and beta is not None and window is not None
        and prices is not None and ticker_a in prices.columns and ticker_b in prices.columns
        and len(prices) > 0
    )

    end_ref = trade["exit_date"] or datetime.today().strftime("%Y-%m-%d")

    result = {
        "trade_id": trade["trade_id"],
        "sector": trade["sector"],
        "ticker_a": ticker_a,
        "ticker_b": ticker_b,
        "entry_date": trade["entry_date"],
        "exit_date": trade["exit_date"],
        "note": trade["note"],
        "days_held": (pd.Timestamp(end_ref) - pd.Timestamp(trade["entry_date"])).days,
        "entry_snapshot": {k: _clean(v) for k, v in snap.items()},
        "status": "no_data",
        "latest_zscore": None,
        "max_abs_zscore_since_entry": None,
        "since_entry_adf_pvalue": None,
        "still_mean_reverting": None,
        "series": None,
    }

    if not has_data:
        return result

    log_a = np.log(prices[ticker_a])
    log_b = np.log(prices[ticker_b])
    spread = compute_spread(log_a.values, log_b.values, alpha, beta)
    spread_series = pd.Series(spread, index=prices.index)

    window_int = int(round(window))
    rolling_mean, rolling_std = rolling_mean_std(spread_series, window_int)
    z_series = (spread_series - rolling_mean) / rolling_std

    entry_ts = pd.Timestamp(trade["entry_date"])
    since_entry_spread = spread_series[spread_series.index >= entry_ts].dropna()
    since_entry_z = z_series[z_series.index >= entry_ts].dropna()

    latest_z = since_entry_z.iloc[-1] if len(since_entry_z) else None
    max_abs_z = since_entry_z.abs().max() if len(since_entry_z) else None

    result["latest_zscore"] = _clean(latest_z)
    result["max_abs_zscore_since_entry"] = _clean(max_abs_z)
    result["status"] = _status_label(latest_z, z_threshold, True)

    # Informational only -- see module docstring. Needs a reasonable minimum
    # sample before an ADF result means anything.
    if len(since_entry_spread) >= 20:
        try:
            adf_stat, adf_p = adfuller(since_entry_spread, autolag="AIC")[:2]
            result["since_entry_adf_pvalue"] = _clean(adf_p)
            result["still_mean_reverting"] = bool(adf_p < 0.10)
        except Exception:
            pass

    result["series"] = {
        "dates": [d.strftime("%Y-%m-%d") for d in spread_series.index],
        "spread": [_clean(v) for v in spread_series.tolist()],
        "rolling_mean": [_clean(v) for v in rolling_mean.tolist()],
        "zscore": [_clean(v) for v in z_series.tolist()],
    }
    return result


def build_trades_payload(trades, z_threshold, include_closed=True, fetch_fn=None):
    """
    fetch_fn defaults to data_fetch.fetch_price_data; injectable for testing
    (see test_synthetic-style monkeypatching in the main pipeline).
    """
    fetch_fn = fetch_fn or _pair_history

    if not include_closed:
        trades = [t for t in trades if t["exit_date"] is None]

    entries = []
    for t in trades:
        end_ref = pd.Timestamp(t["exit_date"]) if t["exit_date"] else None
        try:
            prices = fetch_fn(t["ticker_a"], t["ticker_b"], start_date=t["entry_date"], end_date=end_ref)
        except Exception as e:
            print(f"Could not fetch price history for {t['ticker_a']}/{t['ticker_b']}: {e}")
            prices = None
        entries.append(build_trade_entry(t, prices, z_threshold))

    entries.sort(key=lambda e: (e["exit_date"] is not None, e["entry_date"]))

    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "z_threshold": z_threshold,
        "trades": entries,
    }


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Active Trades Monitor</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0f1115; --panel: #171a21; --border: #2a2e38; --text: #e6e8eb;
    --muted: #9aa1ad; --accent: #5b9dff; --good: #4caf7d; --bad: #e0556e; --warn: #e0a355;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  h1 { font-size: 20px; margin: 0 0 4px 0; }
  .subtitle { font-size: 13px; color: var(--muted); margin-bottom: 18px; }
  .layout { display: grid; grid-template-columns: 560px 1fr; gap: 20px; align-items: start; }
  .panel { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-weight: 500; font-size: 11px; text-transform: uppercase; }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: #1f232c; }
  tbody tr.selected { background: #232a3a; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; }
  .badge.in_range { background: rgba(76,175,125,0.18); color: var(--good); }
  .badge.diverging { background: rgba(224,85,110,0.18); color: var(--bad); }
  .badge.no_data, .badge.insufficient_history { background: rgba(224,163,85,0.18); color: var(--warn); }
  .badge.closed { background: rgba(154,161,173,0.18); color: var(--muted); }
  .stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 18px; }
  .stat-box { background: #1b1f29; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; }
  .stat-box .label { font-size: 11px; color: var(--muted); }
  .stat-box .value { font-size: 15px; margin-top: 2px; }
  .chart-wrap { background: #1b1f29; border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin-bottom: 16px; }
  .chart-wrap h3 { margin: 0 0 8px 0; font-size: 13px; color: var(--muted); font-weight: 500; }
  canvas { max-height: 260px; }
  .empty-state { color: var(--muted); padding: 40px; text-align: center; }
  .note-box { font-size: 12px; color: var(--muted); background: #1b1f29; border: 1px solid var(--border);
    border-radius: 8px; padding: 10px 12px; margin-bottom: 16px; }
</style>
</head>
<body>

<h1>Active Trades Monitor</h1>
<div class="subtitle" id="subtitle">Diagnostic only -- no P&amp;L, no position sizing, no trade signal. Hedge ratio held fixed at entry.</div>

<div class="layout">
  <div class="panel">
    <table>
      <thead><tr><th>Pair</th><th>Days held</th><th>Current Z</th><th>Status</th></tr></thead>
      <tbody id="trade-list"></tbody>
    </table>
  </div>
  <div class="panel" id="detail-panel"><div class="empty-state">Select a trade on the left.</div></div>
</div>

<script id="payload-data" type="application/json">__PAYLOAD_JSON__</script>
<script>
const payload = JSON.parse(document.getElementById('payload-data').textContent);
let activeCharts = [];

function fmt(v, digits) {
  if (v === null || v === undefined) return '\u2014';
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (typeof v === 'number') return v.toFixed(digits === undefined ? 3 : digits);
  return v;
}

function statusLabel(t) {
  if (t.exit_date) return 'closed';
  return t.status;
}
function statusText(t) {
  if (t.exit_date) return 'closed ' + t.exit_date;
  return ({in_range: 'in range', diverging: 'diverging', no_data: 'no data', insufficient_history: 'insufficient history'})[t.status] || t.status;
}

function renderList() {
  const tbody = document.getElementById('trade-list');
  if (payload.trades.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No trades logged yet.</td></tr>';
    return;
  }
  tbody.innerHTML = payload.trades.map((t, i) => `
    <tr data-index="${i}" onclick="selectTrade(${i})">
      <td>${t.ticker_a} / ${t.ticker_b}</td>
      <td>${t.days_held}</td>
      <td>${fmt(t.latest_zscore, 2)}</td>
      <td><span class="badge ${statusLabel(t)}">${statusText(t)}</span></td>
    </tr>`).join('');
  selectTrade(0);
}

function destroyCharts() { activeCharts.forEach(c => c.destroy()); activeCharts = []; }

function renderDetail(t) {
  destroyCharts();
  const snap = t.entry_snapshot;
  document.getElementById('detail-panel').innerHTML = `
    <h2 style="margin-bottom:2px;">${t.ticker_a} / ${t.ticker_b} &nbsp; <span class="badge ${statusLabel(t)}">${statusText(t)}</span></h2>
    <div class="subtitle" style="margin-bottom:12px;">${t.sector} &middot; entered ${t.entry_date}${t.exit_date ? ' &middot; exited ' + t.exit_date : ''}${t.note ? ' &middot; "' + t.note + '"' : ''}</div>

    <div class="note-box">Hedge ratio, half-life, and z-score window below are FIXED at what they were when this trade was logged -- not re-fit on this run. Current z-score and the mean-reversion check are computed fresh against today's prices using that fixed relationship.</div>

    <div class="stats-grid">
      <div class="stat-box"><div class="label">Hedge ratio &beta; (at entry)</div><div class="value">${fmt(snap.hedge_ratio_beta,4)}</div></div>
      <div class="stat-box"><div class="label">Half-life (at entry)</div><div class="value">${fmt(snap.half_life_days,1)} days</div></div>
      <div class="stat-box"><div class="label">Z-window (at entry)</div><div class="value">${fmt(snap.zscore_window,0)} days</div></div>
      <div class="stat-box"><div class="label">Z-score at entry</div><div class="value">${fmt(snap.latest_zscore_at_entry,2)}</div></div>
      <div class="stat-box"><div class="label">Current z-score</div><div class="value">${fmt(t.latest_zscore,2)}</div></div>
      <div class="stat-box"><div class="label">Max |z| since entry</div><div class="value">${fmt(t.max_abs_zscore_since_entry,2)}</div></div>
      <div class="stat-box"><div class="label">Still mean-reverting? (informal ADF, p&lt;0.10)</div><div class="value">${t.still_mean_reverting === null ? 'insufficient data' : (t.still_mean_reverting ? 'Yes' : 'No -- check the relationship')}</div></div>
      <div class="stat-box"><div class="label">Since-entry ADF p-value</div><div class="value">${fmt(t.since_entry_adf_pvalue,4)}</div></div>
      <div class="stat-box"><div class="label">Days held</div><div class="value">${t.days_held}</div></div>
    </div>

    ${t.series ? `
    <div class="chart-wrap"><h3>Spread vs. fixed-relationship rolling mean (since before entry)</h3><canvas id="spreadChart"></canvas></div>
    <div class="chart-wrap"><h3>Z-score since entry (dashed = &plusmn;${payload.z_threshold} threshold, diagnostic only)</h3><canvas id="zChart"></canvas></div>
    ` : '<div class="empty-state">No price history available for this pair.</div>'}
  `;

  if (!t.series) { activeCharts = []; return; }

  const dates = t.series.dates;
  const spreadChart = new Chart(document.getElementById('spreadChart'), {
    type: 'line',
    data: { labels: dates, datasets: [
      { label: 'Spread', data: t.series.spread, borderColor: '#e6e8eb', borderWidth: 1.5, pointRadius: 0, tension: 0 },
      { label: 'Rolling mean', data: t.series.rolling_mean, borderColor: 'rgba(91,157,255,0.7)', borderWidth: 1, pointRadius: 0, tension: 0, borderDash: [4,3] },
    ]},
    options: { responsive: true, animation: false, interaction: { mode: 'index', intersect: false },
      scales: { x: { ticks: { maxTicksLimit: 10 }, grid: { color: '#23262f' } }, y: { grid: { color: '#23262f' } } },
      plugins: { legend: { labels: { color: '#9aa1ad' } } } },
  });

  const zDates = dates;
  const threshold = payload.z_threshold;
  const upperLine = zDates.map(() => threshold);
  const lowerLine = zDates.map(() => -threshold);
  const zChart = new Chart(document.getElementById('zChart'), {
    type: 'line',
    data: { labels: zDates, datasets: [
      { label: 'Z-score', data: t.series.zscore, borderColor: '#5b9dff', borderWidth: 1.5, pointRadius: 0, tension: 0 },
      { label: `+${threshold}`, data: upperLine, borderColor: 'rgba(224,85,110,0.6)', borderWidth: 1, borderDash: [5,4], pointRadius: 0 },
      { label: `-${threshold}`, data: lowerLine, borderColor: 'rgba(224,85,110,0.6)', borderWidth: 1, borderDash: [5,4], pointRadius: 0 },
    ]},
    options: { responsive: true, animation: false, interaction: { mode: 'index', intersect: false },
      scales: { x: { ticks: { maxTicksLimit: 10 }, grid: { color: '#23262f' } }, y: { grid: { color: '#23262f' } } },
      plugins: { legend: { labels: { color: '#9aa1ad' } } } },
  });

  activeCharts = [spreadChart, zChart];
}

function selectTrade(index) {
  document.querySelectorAll('#trade-list tr').forEach(tr => tr.classList.remove('selected'));
  const row = document.querySelector(`#trade-list tr[data-index="${index}"]`);
  if (row) row.classList.add('selected');
  renderDetail(payload.trades[index]);
}

renderList();
</script>
</body>
</html>
"""


def render_html(payload):
    return _HTML_TEMPLATE.replace("__PAYLOAD_JSON__", json.dumps(payload))


def write_trades_report(payload, output_dir=None):
    output_dir = output_dir or getattr(config, "OUTPUT_DIR", "output")
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"trades_report_{timestamp}.html"
    path = os.path.join(output_dir, filename)
    html = render_html(payload)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def run(trades_path="trades.json", include_closed=True):
    trades = load_trades(trades_path)
    if not trades:
        print("No trades logged in trades.json -- nothing to report. Use trades.py to log one.")
        return None
    payload = build_trades_payload(trades, config.Z_THRESHOLD, include_closed=include_closed)
    path = write_trades_report(payload)
    print(f"Trades report written to {path}")
    return path


if __name__ == "__main__":
    run()
