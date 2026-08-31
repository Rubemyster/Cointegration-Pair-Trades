"""
Validates the full pipeline end-to-end using synthetic data, bypassing the
network call to yfinance (not available in every environment / sandbox).

Runs the REAL main.run() function (not a parallel copy of its logic) by
monkey-patching fetch_price_data, so this exercises main.py,
cointegration.py, half_life.py, zscore.py, output.py, and widget.py exactly
as they execute in production -- including both the CSV and the HTML
widget output.

Builds:
  - a genuinely cointegrated pair (fast-reverting OU spread around a TLS relationship)
  - a pair of independent random walks (should NOT pass cointegration)

Run with: python test_synthetic.py
"""

import numpy as np
import pandas as pd

import config
import data_fetch
import main

np.random.seed(7)

N = (config.ESTIMATION_MONTHS + config.TRADING_MONTHS) * config.TRADING_DAYS_PER_MONTH
dates = pd.bdate_range("2022-01-01", periods=N)

# --- Synthetic pair 1: genuinely cointegrated (fast-reverting OU spread) ---
common_trend = np.cumsum(np.random.normal(0, 0.01, N))
log_B1 = 4.0 + common_trend + np.cumsum(np.random.normal(0, 0.002, N))
true_beta, true_alpha = 1.3, 0.5
ou_spread = np.zeros(N)
theta, sigma = 0.15, 0.02  # ~4-5 trading day half-life
for t in range(1, N):
    ou_spread[t] = ou_spread[t - 1] + theta * (0 - ou_spread[t - 1]) + np.random.normal(0, sigma)
log_A1 = true_alpha + true_beta * log_B1 + ou_spread

# --- Synthetic pair 2: independent random walks (NOT cointegrated) ---
log_A2 = 3.0 + np.cumsum(np.random.normal(0, 0.012, N))
log_B2 = 2.5 + np.cumsum(np.random.normal(0.0005, 0.012, N))

synthetic_prices = pd.DataFrame({
    "COINT_A": np.exp(log_A1),
    "COINT_B": np.exp(log_B1),
    "RAND_A": np.exp(log_A2),
    "RAND_B": np.exp(log_B2),
}, index=dates)


def fake_fetch_price_data(tickers, total_months, end_date=None, max_missing_frac=0.05,
                           include_latest_intraday=True):
    print(f"[mocked fetch_price_data] returning synthetic data for {tickers}")
    return synthetic_prices.copy()


# Patch the function reference main.py actually calls
data_fetch.fetch_price_data = fake_fetch_price_data
main.fetch_price_data = fake_fetch_price_data

config.SECTORS = {"SYNTH_SECTOR": ["COINT_A", "COINT_B", "RAND_A", "RAND_B"]}
config.OUTPUT_DIR = "test_output"

results_df, multi_payload = main.run()

print("\n--- Validating output ---")

assert "passes_bh" in results_df.columns, "Expected passes_bh column (BH replaced Bonferroni)"
assert "sector" in results_df.columns, "Expected sector column for multi-sector support"
assert "bonferroni_alpha" not in results_df.columns, "Bonferroni column should be fully removed"

assert multi_payload["sector_list"] == ["SYNTH_SECTOR"]
payload = multi_payload["sectors"]["SYNTH_SECTOR"]

assert len(payload["pairs"]) == int(results_df["passes_bh"].sum()), (
    "Widget pair count should match the number of pairs that passed Benjamini-Hochberg"
)

cointegrated_passed = any(
    {p["ticker_a"], p["ticker_b"]} == {"COINT_A", "COINT_B"} for p in payload["pairs"]
)
assert cointegrated_passed, "Expected COINT_A/COINT_B to appear in the widget payload"
print("PASS: synthetic cointegrated pair correctly identified and present in widget payload.")

for p in payload["pairs"]:
    assert "bh_critical_pvalue" in p["stats"]
    assert "fdr_level" in p["stats"]
    series = p["series"]
    n = len(series["dates"])
    assert len(series["price_a"]) == n
    assert len(series["price_b"]) == n
    assert len(series["spread"]) == n
    assert len(series["rolling_mean"]) == n
    z = p["zscore_series"]
    assert len(z["dates"]) == len(z["zscore"])
    assert p["estimation_end_date"] in series["dates"]
print(f"PASS: series length/shape consistent across all {len(payload['pairs'])} widget pair(s).")

assert "fdr_level" in payload["group"]
assert "bh_critical_pvalue" in payload["group"]
assert payload["group"]["sector"] == "SYNTH_SECTOR"

# --- Momentum diagnostics (momentum.py) ---
for col in [
    "ar1_alpha", "ar1_beta", "ar1_sign_agreement_recent", "ar1_latest_residual",
    "zscore_delta_latest", "zscore_delta2_latest", "zscore_turning_recent", "momentum_read",
]:
    assert col in results_df.columns, f"Expected momentum column '{col}' in results_df"
print("PASS: momentum columns present in results_df.")

VALID_READS = {"reversion signs agree", "still diverging", "mixed signal", "insufficient data"}
for p in payload["pairs"]:
    if p["has_reversion_estimate"]:
        assert p["momentum"] is not None, "Expected a momentum block for every has_reversion_estimate pair"
        assert p["momentum"]["momentum_read"] in VALID_READS
    else:
        assert p["momentum"] is None, "Expected momentum to be null for pairs with no valid half-life"
print("PASS: momentum diagnostics present/absent consistently with has_reversion_estimate.")

print("\nGroup summary:", payload["group"])
print("\nAll checks passed.")
