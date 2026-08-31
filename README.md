# Pairs-Trading Screening Tool

A manually-run research script that screens a basket of tickers for
statistically valid mean-reverting pairs. It is **not** a backtester —
there is no position sizing, P&L simulation, or trade entry/exit logic.
Its only job is to tell you which pairs are statistically worth your
further (manual) economic review, and what state their spread is
currently in.

## How it works

1. **Data** (`data_fetch.py`) — pulls daily adjusted close prices via
   `yfinance` for every ticker in `TICKER_BASKET`, drops any ticker with
   excessive missing data, then splits the series into an **estimation
   window** (used for all statistical fitting) and a **trading window**
   (used only for the rolling z-score and threshold flag).
2. **Cointegration** (`cointegration.py`) — for every unique pair, fits a
   **Total Least Squares (orthogonal) regression** between the two log
   price series (avoids the OLS asymmetry of regressing A-on-B vs B-on-A),
   then runs an **ADF test** on the resulting residual (the Engle-Granger
   spread).
3. **Multiple-testing correction** (`multiple_testing.py`) — applies the
   **Benjamini-Hochberg (FDR control)** procedure across all pairs' p-values
   at once, rather than checking each pair's p-value in isolation. This
   controls the *expected proportion of false positives* among declared
   discoveries (the target `FDR_LEVEL` in `config.py`), which is a less
   conservative target than a Bonferroni-style family-wise error correction
   — it accepts more false positives in exchange for fewer false negatives,
   on the assumption you'll apply your own economic judgment to the
   shortlist afterward (see the caveat below).
4. **Half-life** (`half_life.py`) — for pairs that pass, fits an AR(1)/
   Ornstein-Uhlenbeck approximation to the spread to estimate how many
   trading days it takes to revert halfway back to its mean.
5. **Z-score** (`zscore.py`) — sizes a rolling window per pair at
   `3 × half-life` (bounded to a sensible floor/ceiling), computes the
   rolling z-score over the trading window, and flags whether/when it
   breached the configurable threshold (`Z_THRESHOLD`, default ±2.5).
   **This flag is diagnostic only** — "the relationship may be
   diverging" — not a trade signal.
6. **Momentum diagnostics** (`momentum.py`) — for pairs that passed
   Benjamini-Hochberg *and* have a valid AR(1) half-life, adds a
   discretionary entry-timing overlay on top of the diagnostic z-score
   flag. Two lenses, both reusing fits/series the pipeline already
   computes rather than introducing new ones:
   - **AR(1)-implied drift vs. realized move** — reuses the same AR(1)
     `(a, b)` fit `half_life.py` already runs on the *estimation-window*
     spread, applies it forward into the trading window (the same static
     way the TLS hedge ratio is applied forward), and checks whether the
     day-to-day realized spread move is starting to agree in sign with
     what the fitted model always predicted (a pull back toward the
     mean) — or whether the spread is still being driven by something
     the model doesn't capture.
   - **Z-score velocity/acceleration** — first and second differences of
     the already-causal rolling z-score from `zscore.py`. No new series,
     no new lookback window for the base calculation.

   Both lenses are windowed by the same `RECENT_BREACH_WINDOW` the
   threshold flag already uses. **This step never feeds back into
   `passes_bh`, the z-score, or the threshold flag** — it's purely an
   additional read, and like the threshold flag it is diagnostic only,
   not a trade signal.
7. **Output** — two files per run, written to `output/`:
   - `output.py` writes a **CSV** with one row per pair tested (including
     pairs that failed cointegration — nothing is silently discarded).
   - `widget.py` writes an **interactive HTML report** covering only the
     pairs that passed Benjamini-Hochberg: a group-level summary panel, a
     clickable list of passing pairs, and a detail panel (dual-axis price
     chart, spread+band chart, z-score+threshold chart, full stats block)
     for whichever single pair is selected. Open the `.html` file in any
     browser — no server or build step needed (an internet connection is
     needed at *view* time only, to load Chart.js from a CDN).

## Why Benjamini-Hochberg instead of Bonferroni

Bonferroni controls the probability of *even one* false positive across the
whole basket, which gets extremely strict as the basket grows (a 20-ticker
basket gives 190 pairs, and a corrected significance level of roughly
0.00026 — over 190x stricter than the conventional 0.05). That's
conservative enough to reject genuinely cointegrated pairs whose reversion
signal is real but modest, which compounds badly with the already-limited
statistical power of ADF tests on a few years of daily data.

Benjamini-Hochberg instead targets a tolerable *rate* of false discoveries
(`FDR_LEVEL`, default 0.05) among whatever it flags as significant, which
loosens the bar considerably and lets more genuinely-cointegrated pairs
through — at the cost of accepting more false positives along the way.
Since this tool is a manual-review screener rather than an auto-trading
pipeline, that tradeoff favors BH: false positives get caught by your own
economic-rationale check afterward, while false negatives (a real pair
filtered out before you ever see it) can't be recovered.

## Running it

```bash
pip install -r requirements.txt
python main.py
```

Edit `TICKER_BASKET` in `config.py` to test a different sector/basket —
nothing else needs to change. Other tunable parameters (window lengths,
FDR level, z-score multiplier, threshold) are also in `config.py`.

## Output columns (CSV)

| Column | Meaning |
|---|---|
| `ticker_a`, `ticker_b` | the pair |
| `eg_adf_stat`, `eg_pvalue` | Engle-Granger ADF test statistic/p-value |
| `fdr_level` | the target false discovery rate used (`config.FDR_LEVEL`) |
| `bh_critical_pvalue` | the effective p-value cutoff BH derived for this run |
| `passes_bh` | whether the pair cleared the Benjamini-Hochberg threshold |
| `hedge_ratio_beta`, `intercept_alpha` | TLS-fitted relationship |
| `half_life_days` | estimated mean-reversion half-life |
| `zscore_window` | rolling window used for that pair's z-score |
| `latest_zscore` | most recent z-score in the trading window |
| `max_abs_zscore` | largest absolute z-score reached in the trading window |
| `threshold_breached`, `breach_date` | whether/when `Z_THRESHOLD` was breached |
| `ar1_alpha`, `ar1_beta` | AR(1) intercept/slope fitted on the estimation-window spread (same fit `half_life_days` is derived from) |
| `ar1_sign_agreement_recent` | fraction of the last `RECENT_BREACH_WINDOW` sessions where the realized spread move agreed in sign with the AR(1)-predicted move |
| `ar1_latest_residual` | most recent (realized − AR(1)-predicted) move; near zero means the fitted dynamics are holding |
| `zscore_delta_latest`, `zscore_delta2_latest` | most recent first/second difference of the rolling z-score (velocity/acceleration) |
| `zscore_turning_recent` | whether `\|z\|` is smaller now than it was `RECENT_BREACH_WINDOW` sessions ago |
| `momentum_read` | combined plain-language read: `reversion signs agree` / `still diverging` / `mixed signal` / `insufficient data` |

## A note on the dual-axis price chart in the HTML report

The price chart layers both tickers' raw prices on independently-scaled
left/right axes. This is a quick visual sense-check, not statistical
evidence — with two free axis scales, you can make almost any two series
*look* like they track each other. The spread and z-score charts below it
are the actual evidence; the price chart is there to give visual context,
and is labelled as such in the report.

## A note on the ADF p-value

The Engle-Granger procedure technically requires critical values adjusted
for the fact that the spread comes from an *estimated* relationship, not
an observed series — `statsmodels.tsa.stattools.coint()` applies this
correction but only supports OLS internally. Since this tool uses TLS
specifically to avoid OLS's regression-direction asymmetry, it reports the
standard ADF p-value instead, which is a close but slightly optimistic
approximation. Worth keeping in mind when a pair sits right on the
BH critical p-value boundary.

## A note on the momentum diagnostics

`momentum.py` only runs for pairs that already passed Benjamini-Hochberg
*and* have a valid AR(1) half-life (`has_reversion_estimate = True` in the
widget) — the same population the z-score/threshold flag is scoped to. It
is entry-timing help, not a second statistical test: `classify_momentum`'s
0.6 / 0.4 sign-agreement thresholds are a plain rule of thumb, and unlike
the Benjamini-Hochberg correction applied to the cointegration p-values,
there is no false-discovery-rate correction protecting these thresholds
against being read too confidently across many pairs. Treat `momentum_read`
as a prompt for a closer manual look, in the same spirit as
`threshold_breached` — never as an entry/exit instruction.

## Validation

`test_synthetic.py` runs the actual `main.run()` pipeline (not a parallel
copy of the logic) against synthetic data, bypassing the network call to
yfinance, confirming the cointegration test, Benjamini-Hochberg correction,
half-life estimation, dynamic z-score window, threshold flag, momentum
diagnostics, and HTML widget payload all behave correctly on both a
genuinely mean-reverting pair and unrelated random-walk pairs. Run with
`python test_synthetic.py`.

Note: in that synthetic run, one or two genuinely unrelated random-walk
pairs typically still pass BH by chance — a real illustration of the
false-positive tradeoff described above, not a bug in the test.
