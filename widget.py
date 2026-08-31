"""
Builds the interactive HTML widget: a group-level summary, a clickable list
of pairs that passed the Benjamini-Hochberg (FDR-controlled) cointegration
test, and a detail panel (dual-axis price chart, spread+band chart,
z-score+threshold chart, stats block) for whichever single pair is selected.

The output is one self-contained .html file -- no build step, no server,
just open it in a browser. Charting is done with Chart.js, loaded from a
CDN at view-time (so an internet connection is needed when *opening* the
file, not when generating it).
"""

import json
import os
from datetime import datetime

import numpy as np
import pandas as pd


def _clean(value):
    """Converts numpy/pandas scalars to plain JSON-safe Python values, NaN -> None."""
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (np.floating, float)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    return value


def _series_to_list(series):
    """Converts a pandas Series to a list of JSON-safe values (NaN -> None)."""
    return [_clean(v) for v in series.tolist()]


def _dates_to_list(index):
    return [d.strftime("%Y-%m-%d") for d in index]


def _clean_momentum(momentum):
    """
    JSON-safe serialization of the momentum.py summary dict passed in from
    main.py, or None when the pair has no valid AR(1) half-life (same
    has_reversion_estimate=False population the z-score/threshold fields
    are already left blank for).
    """
    if momentum is None:
        return None
    return {k: _clean(v) for k, v in momentum.items()}


def build_group_summary(sector_name, basket, estimation_df, trading_df, n_pairs_tested, fdr_level,
                         bh_critical_pvalue, n_passed):
    return {
        "sector": sector_name,
        "basket": list(basket),
        "run_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "estimation_start": estimation_df.index[0].strftime("%Y-%m-%d"),
        "estimation_end": estimation_df.index[-1].strftime("%Y-%m-%d"),
        "trading_start": trading_df.index[0].strftime("%Y-%m-%d"),
        "trading_end": trading_df.index[-1].strftime("%Y-%m-%d"),
        "n_pairs_tested": int(n_pairs_tested),
        "fdr_level": _clean(fdr_level),
        "bh_critical_pvalue": _clean(bh_critical_pvalue),
        "n_passed": int(n_passed),
    }


def build_pair_entry(row, price_a_full, price_b_full, spread_full, rolling_mean_full,
                      rolling_std_full, z_trading, estimation_end_date, z_threshold,
                      recent_breach_window, name_a=None, name_b=None, momentum=None):
    """
    Assembles one pair's full record for the JSON payload: its stats (from
    the results_df row) plus every series the widget needs to draw.

    name_a/name_b are display-only company names (falls back to the ticker
    symbol if a lookup failed) -- purely presentational, no bearing on any
    statistic.

    rolling_mean_full/rolling_std_full/z_trading are None when this pair
    passed BH but had no valid AR(1) half-life (no window could be sized).
    In that case the pair still gets an entry -- has_reversion_estimate
    is set to False and the band/z-score series are emitted as nulls/empty
    rather than omitting the pair from the widget entirely.

    momentum is the summary dict built by momentum.build_momentum_entry
    (via main.py), or None for the same no-valid-half-life pairs described
    above -- there's no AR(1) fit or z-score to build a turning-point
    diagnostic from in that case either.
    """
    has_reversion = rolling_mean_full is not None

    if has_reversion:
        upper_band = rolling_mean_full + rolling_std_full
        lower_band = rolling_mean_full - rolling_std_full
        rolling_mean_list = _series_to_list(rolling_mean_full)
        rolling_upper_list = _series_to_list(upper_band)
        rolling_lower_list = _series_to_list(lower_band)
        zscore_dates = _dates_to_list(z_trading.index)
        zscore_values = _series_to_list(z_trading)
    else:
        n = len(spread_full)
        rolling_mean_list = [None] * n
        rolling_upper_list = [None] * n
        rolling_lower_list = [None] * n
        zscore_dates = []
        zscore_values = []

    breach_date = row["breach_date"]
    breach_date_str = _clean(breach_date)

    return {
        "key": f"{row['ticker_a']}__{row['ticker_b']}",
        "ticker_a": row["ticker_a"],
        "ticker_b": row["ticker_b"],
        "name_a": name_a or row["ticker_a"],
        "name_b": name_b or row["ticker_b"],
        "has_reversion_estimate": has_reversion,
        "stats": {
            "eg_adf_stat": _clean(row["eg_adf_stat"]),
            "eg_pvalue": _clean(row["eg_pvalue"]),
            "fdr_level": _clean(row["fdr_level"]),
            "bh_critical_pvalue": _clean(row["bh_critical_pvalue"]),
            "hedge_ratio_beta": _clean(row["hedge_ratio_beta"]),
            "intercept_alpha": _clean(row["intercept_alpha"]),
            "half_life_days": _clean(row["half_life_days"]),
            "zscore_window": _clean(row["zscore_window"]),
            "latest_zscore": _clean(row["latest_zscore"]),
            "max_abs_zscore": _clean(row["max_abs_zscore"]),
            "threshold_breached": _clean(row["threshold_breached"]),
            "breach_date": breach_date_str,
            "z_threshold": z_threshold,
            "recent_breach_window": recent_breach_window,
        },
        "momentum": _clean_momentum(momentum),
        "estimation_end_date": estimation_end_date,
        "series": {
            "dates": _dates_to_list(price_a_full.index),
            "price_a": _series_to_list(price_a_full),
            "price_b": _series_to_list(price_b_full),
            "spread": _series_to_list(spread_full),
            "rolling_mean": rolling_mean_list,
            "rolling_upper": rolling_upper_list,
            "rolling_lower": rolling_lower_list,
        },
        "zscore_series": {
            "dates": zscore_dates,
            "zscore": zscore_values,
        },
    }


def build_payload(group_summary, pair_entries):
    return {
        "group": group_summary,
        "pairs": pair_entries,
    }


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Pairs Screening Report</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0f1115;
    --panel: #171a21;
    --border: #2a2e38;
    --text: #e6e8eb;
    --muted: #9aa1ad;
    --accent: #5b9dff;
    --accent2: #ff8a5b;
    --good: #4caf7d;
    --bad: #e0556e;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px;
    background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  h1 { font-size: 20px; margin: 0 0 4px 0; }
  .sector-bar { display: flex; align-items: center; gap: 10px; margin: 10px 0 14px 0; }
  .sector-bar label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .sector-bar select {
    background: var(--panel); color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 6px 10px; font-size: 13px; min-width: 220px;
  }
  h2 { font-size: 15px; margin: 0 0 12px 0; color: var(--muted); font-weight: 500; }
  .summary {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
    background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    padding: 16px; margin-bottom: 20px;
  }
  .summary .item { display: flex; flex-direction: column; }
  .summary .label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .summary .value { font-size: 15px; margin-top: 2px; }
  .layout { display: grid; grid-template-columns: 640px 1fr; gap: 20px; align-items: start; }
  .panel {
    background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 16px;
  }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-weight: 500; font-size: 11px; text-transform: uppercase; }
  th.sortable { cursor: pointer; user-select: none; white-space: nowrap; }
  th.sortable:hover { color: var(--text); }
  th.sortable .arrow { display: inline-block; width: 10px; opacity: 0.6; }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: #1f232c; }
  tbody tr.selected { background: #232a3a; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; }
  .pair-name { line-height: 1.3; }
  .pair-ticker-sub { font-size: 11px; color: var(--muted); }
  .badge.breach { background: rgba(224,85,110,0.18); color: var(--bad); }
  .badge.clear { background: rgba(76,175,125,0.18); color: var(--good); }
  .badge.no-signal { background: rgba(154,161,173,0.18); color: var(--muted); }
  .badge.mixed { background: rgba(255,190,90,0.18); color: #ffbe5a; }
  .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 18px; }
  .stat-box {
    background: #1b1f29; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px;
  }
  .stat-box .label { font-size: 11px; color: var(--muted); }
  .stat-box .value { font-size: 15px; margin-top: 2px; }
  .chart-wrap { background: #1b1f29; border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin-bottom: 16px; }
  .chart-wrap h3 { margin: 0 0 8px 0; font-size: 13px; color: var(--muted); font-weight: 500; }
  canvas { max-height: 280px; }
  .empty-state { color: var(--muted); padding: 40px; text-align: center; }
  .legend-note { font-size: 11px; color: var(--muted); margin-top: 4px; }
</style>
</head>
<body>

<h1>Pairs Screening Report</h1>
<div class="sector-bar">
  <label for="sector-select">Sector</label>
  <select id="sector-select" onchange="selectSectorFilter(this.value)"></select>
</div>
<h2 id="subtitle">All pairs that passed Benjamini-Hochberg, across every sector</h2>

<div class="summary" id="summary-panel"></div>

<div class="layout">
  <div class="panel">
    <table>
      <thead>
        <tr>
          <th>Pair</th>
          <th>Sector</th>
          <th class="sortable" onclick="setSort('eg_pvalue')">p-value <span class="arrow" id="arrow-eg_pvalue"></span></th>
          <th class="sortable" onclick="setSort('latest_zscore')">Current Z <span class="arrow" id="arrow-latest_zscore"></span></th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody id="pair-list"></tbody>
    </table>
  </div>

  <div class="panel" id="detail-panel">
    <div class="empty-state">Select a pair on the left to see its detail.</div>
  </div>
</div>

<script id="payload-data" type="application/json">__PAYLOAD_JSON__</script>
<script>
const multiPayload = JSON.parse(document.getElementById('payload-data').textContent);
let activeCharts = [];

// Flatten every sector's passing pairs into one list, tagging each with
// its sector name so it can still be traced back to the right payload
// (needed for the detail panel, which reuses each pair's full record).
const allPairs = [];
multiPayload.sector_list.forEach(sectorName => {
  multiPayload.sectors[sectorName].pairs.forEach(p => {
    allPairs.push(Object.assign({ sector: sectorName }, p));
  });
});

let sectorFilter = 'ALL';
let sortKey = 'eg_pvalue';   // default: p-value
let sortDir = 'asc';         // p-value ascending = most significant first
let currentList = [];        // the filtered+sorted list currently on screen

function fmt(v, digits) {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (typeof v === 'number') return v.toFixed(digits === undefined ? 3 : digits);
  return v;
}

function renderSectorDropdown() {
  const sel = document.getElementById('sector-select');
  const options = [`<option value="ALL">All sectors (${allPairs.length} passed)</option>`]
    .concat(multiPayload.sector_list.map(name => {
      const n = multiPayload.sectors[name].pairs.length;
      return `<option value="${name}">${name} (${n} passed)</option>`;
    }));
  sel.innerHTML = options.join('');
  sel.value = sectorFilter;
}

function selectSectorFilter(sectorName) {
  sectorFilter = sectorName;
  renderSummary();
  renderPairList();
}

function setSort(key) {
  if (sortKey === key) {
    sortDir = sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    sortKey = key;
    sortDir = 'asc';
  }
  renderPairList();
}

function updateSortArrows() {
  ['eg_pvalue', 'latest_zscore'].forEach(key => {
    const el = document.getElementById(`arrow-${key}`);
    if (!el) return;
    el.textContent = key === sortKey ? (sortDir === 'asc' ? '▲' : '▼') : '';
  });
}

function getFilteredSorted() {
  let list = sectorFilter === 'ALL' ? allPairs : allPairs.filter(p => p.sector === sectorFilter);
  list = list.slice().sort((a, b) => {
    let av = a.stats[sortKey], bv = b.stats[sortKey];
    // nulls/undefined always sort last, regardless of direction
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    return sortDir === 'asc' ? av - bv : bv - av;
  });
  return list;
}

function renderSummary() {
  const list = sectorFilter === 'ALL' ? allPairs : allPairs.filter(p => p.sector === sectorFilter);
  const groups = sectorFilter === 'ALL'
    ? multiPayload.sector_list.map(name => multiPayload.sectors[name].group)
    : [multiPayload.sectors[sectorFilter].group];
  const nTested = groups.reduce((sum, g) => sum + g.n_pairs_tested, 0);
  const items = sectorFilter === 'ALL'
    ? [
        ['Sectors screened', multiPayload.sector_list.length],
        ['Pairs tested (all sectors)', nTested],
        ['Pairs passed BH', list.length],
        ['Overall pass rate', nTested ? ((list.length / nTested) * 100).toFixed(1) + '%' : '—'],
      ]
    : [
        ['Estimation / trading window', `${groups[0].estimation_start} → ${groups[0].trading_end}`],
        ['Pairs tested', groups[0].n_pairs_tested],
        ['FDR level (Q) / BH critical p', `${fmt(groups[0].fdr_level, 3)} / ${fmt(groups[0].bh_critical_pvalue, 6)}`],
        ['Pairs passed', list.length],
      ];
  const el = document.getElementById('summary-panel');
  el.innerHTML = items.map(([label, value]) =>
    `<div class="item"><div class="label">${label}</div><div class="value">${value}</div></div>`
  ).join('');
}

function renderPairList() {
  currentList = getFilteredSorted();
  updateSortArrows();
  const tbody = document.getElementById('pair-list');
  if (currentList.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No pairs passed the Benjamini-Hochberg FDR-controlled threshold.</td></tr>';
    document.getElementById('detail-panel').innerHTML =
      '<div class="empty-state">Select a pair on the left to see its detail.</div>';
    return;
  }
  tbody.innerHTML = currentList.map((p, i) => {
    return `<tr data-index="${i}" onclick="selectPair(${i})">
      <td>${p.ticker_a} / ${p.ticker_b}</td>
      <td>${p.sector}</td>
      <td>${fmt(p.stats.eg_pvalue, 4)}</td>
      <td>${fmt(p.stats.latest_zscore, 2)}</td>
      <td>${statusBadge(p)}</td>
    </tr>`;
  }).join('');
  selectPair(0);
}

function fmtPct(v) {
  if (v === null || v === undefined) return '—';
  return (v * 100).toFixed(0) + '%';
}

function momentumReadBadgeClass(read) {
  if (read === 'reversion signs agree') return 'clear';
  if (read === 'still diverging') return 'breach';
  if (read === 'mixed signal') return 'mixed';
  return 'no-signal';
}

function momentumPanelHtml(pair) {
  const m = pair.momentum;
  if (!pair.has_reversion_estimate || !m) {
    return `<div class="chart-wrap">
      <h3>Momentum / turning-point diagnostics</h3>
      <div class="empty-state" style="padding:20px;">Not available -- this pair has no valid AR(1) half-life, so there's no fitted reversion model to compare realized moves against, and no z-score to take a velocity from.</div>
    </div>`;
  }
  const badgeClass = momentumReadBadgeClass(m.momentum_read);
  return `<div class="chart-wrap">
    <h3>Momentum / turning-point diagnostics, last ${m.recent_window} sessions (discretionary overlay -- not a trade signal)</h3>
    <div style="margin-bottom:10px;"><span class="badge ${badgeClass}">${m.momentum_read}</span></div>
    <div class="stats-grid" style="margin-bottom:0;">
      <div class="stat-box"><div class="label">AR(1) sign agreement (recent)</div><div class="value">${fmtPct(m.ar1_sign_agreement_recent)}</div></div>
      <div class="stat-box"><div class="label">AR(1) latest residual</div><div class="value">${fmt(m.ar1_latest_residual, 5)}</div></div>
      <div class="stat-box"><div class="label">Z-score Δ (latest)</div><div class="value">${fmt(m.zscore_delta_latest, 3)}</div></div>
      <div class="stat-box"><div class="label">Z-score Δ² (latest)</div><div class="value">${fmt(m.zscore_delta2_latest, 3)}</div></div>
    </div>
    <div class="legend-note">Sign agreement: fraction of the last ${m.recent_window} sessions where the realized spread move matched the direction the estimation-window AR(1) fit predicted (a pull back toward the mean). Z-score Δ/Δ²: first/second differences of the already-causal rolling z-score -- a shrinking |z| means the standardized position is turning back toward zero.</div>
  </div>`;
}

function statusBadge(p) {
  // A pair that passed BH but has no valid AR(1) half-life gets its own
  // badge -- it's a real statistical discovery, but there's no reversion
  // estimate to build a z-score window from, so "breach"/"clear" would
  // both overstate what's actually known about it.
  if (!p.has_reversion_estimate) return '<span class="badge no-signal">no signal</span>';
  return p.stats.threshold_breached
    ? '<span class="badge breach">breach</span>'
    : '<span class="badge clear">clear</span>';
}

function destroyCharts() {
  activeCharts.forEach(c => c.destroy());
  activeCharts = [];
}

function segmentColorFn(estIdx, colorBefore, colorAfter) {
  return (ctx) => (ctx.p0DataIndex < estIdx ? colorBefore : colorAfter);
}

function renderDetail(pair) {
  destroyCharts();
  const s = pair.stats;
  const hasReversion = pair.has_reversion_estimate;
  const estIdx = pair.series.dates.indexOf(pair.estimation_end_date) + 1;

  let breachBadge;
  if (!hasReversion) {
    breachBadge = `<span class="badge no-signal">passed BH, but no valid half-life -- z-score unavailable</span>`;
  } else if (s.threshold_breached) {
    breachBadge = `<span class="badge breach">recent breach ±${s.z_threshold} on ${s.breach_date}</span>`;
  } else {
    breachBadge = `<span class="badge clear">no breach in last ${s.recent_breach_window} sessions (±${s.z_threshold})</span>`;
  }

  const spreadSubtitle = hasReversion
    ? 'lighter region = estimation window, solid = trading window'
    : 'no band shown -- this pair has no valid AR(1) half-life, so no reversion-sized window could be built';

  const momentumBlock = momentumPanelHtml(pair);

  const zChartBlock = hasReversion
    ? `<div class="chart-wrap">
         <h3>Z-score over trading window (dashed lines = ±${s.z_threshold} threshold; breach flag = |z| exceeded this in the last ${s.recent_breach_window} sessions)</h3>
         <canvas id="zChart"></canvas>
       </div>`
    : `<div class="chart-wrap">
         <h3>Z-score over trading window</h3>
         <div class="empty-state" style="padding:20px;">No z-score available. This pair cleared the Benjamini-Hochberg cointegration test, but its spread didn't fit a mean-reverting AR(1) model (the estimated reversion coefficient wasn't negative), so no window could be sized and no trading signal can be built from it.</div>
       </div>`;

  document.getElementById('detail-panel').innerHTML = `
    <h2 style="margin-bottom:2px;">${pair.name_a} / ${pair.name_b} &nbsp; ${breachBadge}</h2>
    <div class="pair-ticker-sub" style="margin-bottom:12px;">${pair.ticker_a} / ${pair.ticker_b}</div>

    <div class="stats-grid">
      <div class="stat-box"><div class="label">EG ADF stat / p-value</div><div class="value">${fmt(s.eg_adf_stat,3)} / ${fmt(s.eg_pvalue,4)}</div></div>
      <div class="stat-box"><div class="label">FDR level (Q) / BH critical p</div><div class="value">${fmt(s.fdr_level,3)} / ${fmt(s.bh_critical_pvalue,6)}</div></div>
      <div class="stat-box"><div class="label">Hedge ratio β (TLS)</div><div class="value">${fmt(s.hedge_ratio_beta,4)}</div></div>
      <div class="stat-box"><div class="label">Intercept α</div><div class="value">${fmt(s.intercept_alpha,4)}</div></div>
      <div class="stat-box"><div class="label">Half-life</div><div class="value">${fmt(s.half_life_days,1)} days</div></div>
      <div class="stat-box"><div class="label">Z-score window</div><div class="value">${fmt(s.zscore_window,0)} days</div></div>
      <div class="stat-box"><div class="label">Latest z-score</div><div class="value">${fmt(s.latest_zscore,2)}</div></div>
      <div class="stat-box"><div class="label">Max |z| in trading window</div><div class="value">${fmt(s.max_abs_zscore,2)}</div></div>
    </div>

    ${momentumBlock}

    <div class="chart-wrap">
      <h3>Price (dual axis -- visual reference only, axes are independently scaled, not statistical evidence)</h3>
      <canvas id="priceChart"></canvas>
    </div>
    <div class="chart-wrap">
      <h3>Spread vs. rolling mean ±1 std band (${spreadSubtitle})</h3>
      <canvas id="spreadChart"></canvas>
    </div>
    ${zChartBlock}
  `;

  const dates = pair.series.dates;
  const colorAEst = 'rgba(91,157,255,0.35)', colorATrade = 'rgba(91,157,255,1)';
  const colorBEst = 'rgba(255,138,91,0.35)', colorBTrade = 'rgba(255,138,91,1)';
  const colorSpreadEst = 'rgba(230,232,235,0.35)', colorSpreadTrade = 'rgba(230,232,235,1)';

  const priceChart = new Chart(document.getElementById('priceChart'), {
    type: 'line',
    data: {
      labels: dates,
      datasets: [
        {
          label: pair.ticker_a, data: pair.series.price_a, yAxisID: 'yA',
          borderWidth: 1.5, pointRadius: 0, tension: 0,
          segment: { borderColor: segmentColorFn(estIdx, colorAEst, colorATrade) },
        },
        {
          label: pair.ticker_b, data: pair.series.price_b, yAxisID: 'yB',
          borderWidth: 1.5, pointRadius: 0, tension: 0,
          segment: { borderColor: segmentColorFn(estIdx, colorBEst, colorBTrade) },
        },
      ],
    },
    options: {
      responsive: true, animation: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { ticks: { maxTicksLimit: 10 }, grid: { color: '#23262f' } },
        yA: { type: 'linear', position: 'left', title: { display: true, text: pair.ticker_a }, grid: { color: '#23262f' } },
        yB: { type: 'linear', position: 'right', title: { display: true, text: pair.ticker_b }, grid: { drawOnChartArea: false } },
      },
      plugins: { legend: { labels: { color: '#9aa1ad' } } },
    },
  });

  const spreadChart = new Chart(document.getElementById('spreadChart'), {
    type: 'line',
    data: {
      labels: dates,
      datasets: [
        {
          label: 'Spread', data: pair.series.spread,
          borderWidth: 1.5, pointRadius: 0, tension: 0,
          segment: { borderColor: segmentColorFn(estIdx, colorSpreadEst, colorSpreadTrade) },
        },
        {
          label: 'Rolling mean', data: pair.series.rolling_mean,
          borderColor: 'rgba(91,157,255,0.7)', borderWidth: 1, pointRadius: 0, tension: 0, borderDash: [4,3],
        },
        {
          label: '+1 std', data: pair.series.rolling_upper,
          borderColor: 'rgba(154,161,173,0.4)', borderWidth: 1, pointRadius: 0, tension: 0,
        },
        {
          label: '-1 std', data: pair.series.rolling_lower,
          borderColor: 'rgba(154,161,173,0.4)', borderWidth: 1, pointRadius: 0, tension: 0,
        },
      ],
    },
    options: {
      responsive: true, animation: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { ticks: { maxTicksLimit: 10 }, grid: { color: '#23262f' } },
        y: { grid: { color: '#23262f' } },
      },
      plugins: { legend: { labels: { color: '#9aa1ad' } } },
    },
  });

  activeCharts = [priceChart, spreadChart];

  if (hasReversion) {
    const zDates = pair.zscore_series.dates;
    const zValues = pair.zscore_series.zscore;
    const threshold = s.z_threshold;
    const upperLine = zDates.map(() => threshold);
    const lowerLine = zDates.map(() => -threshold);
    const breachPoints = zDates.map((d, i) => (d === s.breach_date ? zValues[i] : null));

    const zChart = new Chart(document.getElementById('zChart'), {
      type: 'line',
      data: {
        labels: zDates,
        datasets: [
          { label: 'Z-score', data: zValues, borderColor: '#5b9dff', borderWidth: 1.5, pointRadius: 0, tension: 0 },
          { label: `+${threshold}`, data: upperLine, borderColor: 'rgba(224,85,110,0.6)', borderWidth: 1, borderDash: [5,4], pointRadius: 0 },
          { label: `-${threshold}`, data: lowerLine, borderColor: 'rgba(224,85,110,0.6)', borderWidth: 1, borderDash: [5,4], pointRadius: 0 },
          { label: 'Breach', data: breachPoints, borderColor: 'transparent', pointBackgroundColor: '#e0556e', pointRadius: 5, showLine: false },
        ],
      },
      options: {
        responsive: true, animation: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: { ticks: { maxTicksLimit: 10 }, grid: { color: '#23262f' } },
          y: { grid: { color: '#23262f' } },
        },
        plugins: { legend: { labels: { color: '#9aa1ad' } } },
      },
    });

    activeCharts.push(zChart);
  }
}

function selectPair(index) {
  document.querySelectorAll('#pair-list tr').forEach(tr => tr.classList.remove('selected'));
  const row = document.querySelector(`#pair-list tr[data-index="${index}"]`);
  if (row) row.classList.add('selected');
  renderDetail(currentList[index]);
}

renderSectorDropdown();
renderSummary();
renderPairList();
</script>
</body>
</html>
"""


def render_html(payload):
    return _HTML_TEMPLATE.replace("__PAYLOAD_JSON__", json.dumps(payload))


def write_widget(payload, output_dir="output"):
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"pairs_report_{timestamp}.html"
    path = os.path.join(output_dir, filename)
    html = render_html(payload)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path