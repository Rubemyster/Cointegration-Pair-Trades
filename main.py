"""
Pairs-trading screening tool -- main orchestration.

This is a research/screening script, not a backtester: it tests every
combination within TICKER_BASKET (see config.py) for cointegration, derives
a hedge ratio and half-life for pairs that pass, and computes a dynamic
rolling z-score over an out-of-sample trading window, flagging any pair
whose z-score breaches a configurable threshold.

No position sizing, P&L simulation, or trade entry/exit logic is included
by design -- this tool's only job is to surface statistically interesting
pairs for further (manual) review.

Multiple-testing correction: Benjamini-Hochberg (FDR control), not
Bonferroni. This requires a two-pass structure -- BH needs every pair's
p-value before it can decide which pairs pass, unlike Bonferroni's alpha/n
threshold, which could be checked pair-by-pair as you went:
  Pass 1: run the Engle-Granger test on every pair, collect all p-values.
  Pass 2: apply Benjamini-Hochberg across the full set of p-values at once.
  Pass 3: for pairs that passed, compute half-life, z-score, and the
          threshold flag, and retain their series for the HTML widget.

For pairs that pass BH and have a valid AR(1) half-life, momentum.py adds
a discretionary turning-point diagnostic on top: it compares the AR(1)
model's implied pull-back-to-mean against the realized spread move, and
tracks the velocity/acceleration of the already-computed z-score. This
never feeds back into passes_bh, the z-score, or the threshold flag -- it
is purely an additional read surfaced in the CSV and widget for manual
entry-timing judgement, not a statistically-corrected test the way BH is.

Produces two outputs per run:
  - a CSV with one row per pair tested (including failures)
  - an interactive HTML report covering only pairs that passed BH

Run with:  python main.py
"""

import itertools

import numpy as np
import pandas as pd

import config
from data_fetch import fetch_price_data, fetch_ticker_names, split_windows
from cointegration import engle_granger_test, compute_spread
from multiple_testing import benjamini_hochberg
from half_life import fit_ar1
from zscore import determine_zscore_window, rolling_mean_std, flag_threshold_breach
from momentum import build_momentum_entry
from output import write_results
from widget import build_group_summary, build_pair_entry, build_payload, write_widget


def run_sector(sector_name, ticker_basket, name_cache=None):
    """
    Runs the full pipeline (fetch -> cointegration -> BH -> half-life ->
    z-score) for a single sector/basket. Returns (results_df, group_summary,
    pair_entries) -- the caller is responsible for combining these across
    sectors and writing output.

    Each sector gets its OWN Benjamini-Hochberg pass. Sectors are separate
    families of hypotheses (a banking pair and a mining pair being
    cointegrated are unrelated questions), so pooling all sectors into one
    BH correction would understate the discovery rate within each sector
    and isn't the standard FDR use case.
    """
    total_months = config.ESTIMATION_MONTHS + config.TRADING_MONTHS
    print(f"\n=== Sector: {sector_name} ({len(ticker_basket)} tickers) ===")
    print(f"Fetching ~{total_months} months of data for {len(ticker_basket)} tickers...")
    prices = fetch_price_data(
        ticker_basket, total_months,
        include_latest_intraday=config.INCLUDE_INTRADAY_LATEST_PRICE,
    )

    estimation_df, trading_df, combined_df = split_windows(
        prices,
        config.ESTIMATION_MONTHS,
        config.TRADING_MONTHS,
        config.TRADING_DAYS_PER_MONTH,
    )

    log_prices = np.log(combined_df)
    log_estimation = log_prices.loc[estimation_df.index]
    estimation_end_date = estimation_df.index[-1].strftime("%Y-%m-%d")

    tickers = list(combined_df.columns)
    pairs = list(itertools.combinations(tickers, 2))
    n_pairs = len(pairs)
    if n_pairs == 0:
        raise ValueError("Need at least 2 tickers with valid data to form a pair.")

    print(f"Testing {n_pairs} pairs.")

    # Display names only -- looked up for the tickers that actually survived
    # fetch_price_data's missing-data filter, not the full requested basket.
    name_map = fetch_ticker_names(tickers, cache=name_cache)

    # --- Pass 1: Engle-Granger test on every pair, collect all p-values ---
    eg_results = []
    for ticker_a, ticker_b in pairs:
        log_a_est = log_estimation[ticker_a].values
        log_b_est = log_estimation[ticker_b].values
        eg = engle_granger_test(log_a_est, log_b_est)
        eg_results.append({"ticker_a": ticker_a, "ticker_b": ticker_b, "eg": eg})

    # --- Pass 2: Benjamini-Hochberg across all p-values at once ---
    p_values = [r["eg"]["adf_pvalue"] for r in eg_results]
    passes_bh_list, critical_pvalue = benjamini_hochberg(p_values, config.FDR_LEVEL)
    
    # --- Diagnostic: show how the best p-value compares to the rank-1 BH threshold ---
    rank1_threshold = (1 / n_pairs) * config.FDR_LEVEL
    best_pvalue = min(p_values)
    print(f"Rank-1 BH threshold: {rank1_threshold:.6f}  |  Best p-value in basket: {best_pvalue:.6f}  |  Gap: {best_pvalue / rank1_threshold:.2f}x")

    n_passed = sum(passes_bh_list)
    print(
        f"Benjamini-Hochberg at FDR level {config.FDR_LEVEL}: "
        f"{n_passed} / {n_pairs} pairs pass "
        f"(critical p-value = {critical_pvalue if critical_pvalue is not None else 'n/a'})"
    )

    # --- Pass 3: for pairs that passed, compute half-life / z-score / flag ---
    trading_days_in_window = len(trading_df)
    max_zscore_window = trading_days_in_window  # cap: never exceed trading window length

    results = []
    pair_entries = []  # only populated for pairs that pass -- feeds the HTML widget

    for eg_result, passes_bh in zip(eg_results, passes_bh_list):
        ticker_a, ticker_b, eg = eg_result["ticker_a"], eg_result["ticker_b"], eg_result["eg"]

        row = {
            "sector": sector_name,
            "ticker_a": ticker_a,
            "ticker_b": ticker_b,
            "name_a": name_map.get(ticker_a, ticker_a),
            "name_b": name_map.get(ticker_b, ticker_b),
            "eg_adf_stat": eg["adf_stat"],
            "eg_pvalue": eg["adf_pvalue"],
            "fdr_level": config.FDR_LEVEL,
            "bh_critical_pvalue": critical_pvalue,
            "passes_bh": passes_bh,
            "hedge_ratio_beta": eg["beta"],
            "intercept_alpha": eg["alpha"],
            "half_life_days": np.nan,
            "ar1_alpha": np.nan,
            "ar1_beta": np.nan,
            "zscore_window": np.nan,
            "latest_zscore": np.nan,
            "max_abs_zscore": np.nan,
            "threshold_breached": np.nan,
            "breach_date": None,
            "ar1_sign_agreement_recent": np.nan,
            "ar1_latest_residual": np.nan,
            "zscore_delta_latest": np.nan,
            "zscore_delta2_latest": np.nan,
            "zscore_turning_recent": np.nan,
            "momentum_read": None,
        }

        if passes_bh:
            log_a_full = log_prices[ticker_a]
            log_b_full = log_prices[ticker_b]

            ar1_alpha, ar1_beta, half_life = fit_ar1(eg["spread"])
            row["half_life_days"] = half_life
            row["ar1_alpha"] = ar1_alpha
            row["ar1_beta"] = ar1_beta

            window = determine_zscore_window(
                half_life,
                config.ZSCORE_HALF_LIFE_MULTIPLIER,
                config.MIN_ZSCORE_WINDOW,
                max_zscore_window,
            )
            row["zscore_window"] = window

            # Spread only depends on the TLS fit (alpha/beta), not on the
            # z-score window, so it's always computable -- even for a pair
            # whose AR(1) fit doesn't imply mean-reversion (b >= 0, so
            # determine_zscore_window returned None).
            full_spread = compute_spread(
                log_a_full.values, log_b_full.values, eg["alpha"], eg["beta"]
            )
            full_spread_series = pd.Series(full_spread, index=log_a_full.index)

            rolling_mean = rolling_std = z_trading = None
            momentum_summary = None

            if window is not None:
                rolling_mean, rolling_std = rolling_mean_std(full_spread_series, window)
                z_full = (full_spread_series - rolling_mean) / rolling_std
                z_trading = z_full.loc[trading_df.index]

                valid_z = z_trading.dropna()
                row["latest_zscore"] = valid_z.iloc[-1] if len(valid_z) > 0 else np.nan

                breached, breach_date, max_abs_z = flag_threshold_breach(
                    z_trading, config.Z_THRESHOLD, config.RECENT_BREACH_WINDOW
                )
                row["max_abs_zscore"] = max_abs_z
                row["threshold_breached"] = breached
                row["breach_date"] = breach_date

                # Momentum/turning-point diagnostics (momentum.py) -- a
                # discretionary, widget-and-CSV-only overlay for entry
                # timing. Only computed where a valid AR(1) half-life
                # exists, same population the z-score/threshold flag is
                # already scoped to. Reuses the estimation-window-only
                # AR(1) fit (ar1_alpha, ar1_beta) and the already-causal
                # z_full series -- no new statistical model or lookback
                # window is introduced, and this never feeds back into
                # passes_bh, the z-score, or the threshold flag.
                momentum_entry = build_momentum_entry(
                    spread_full=full_spread_series,
                    ar1_alpha=ar1_alpha,
                    ar1_beta=ar1_beta,
                    z_full=z_full,
                    trading_index=trading_df.index,
                    recent_window=config.RECENT_BREACH_WINDOW,
                )
                row["ar1_sign_agreement_recent"] = momentum_entry["ar1"]["sign_agreement_recent"]
                row["ar1_latest_residual"] = momentum_entry["ar1"]["latest_residual"]
                row["zscore_delta_latest"] = momentum_entry["zvel"]["latest_delta_z"]
                row["zscore_delta2_latest"] = momentum_entry["zvel"]["latest_delta2_z"]
                row["zscore_turning_recent"] = momentum_entry["zvel"]["turning_recent"]
                row["momentum_read"] = momentum_entry["read"]

                momentum_summary = {
                    "ar1_sign_agreement_recent": momentum_entry["ar1"]["sign_agreement_recent"],
                    "ar1_latest_predicted_move": momentum_entry["ar1"]["latest_predicted"],
                    "ar1_latest_realized_move": momentum_entry["ar1"]["latest_realized"],
                    "ar1_latest_residual": momentum_entry["ar1"]["latest_residual"],
                    "zscore_delta_latest": momentum_entry["zvel"]["latest_delta_z"],
                    "zscore_delta2_latest": momentum_entry["zvel"]["latest_delta2_z"],
                    "zscore_turning_recent": momentum_entry["zvel"]["turning_recent"],
                    "momentum_read": momentum_entry["read"],
                    "recent_window": config.RECENT_BREACH_WINDOW,
                }

            # Every pair that passes BH gets a widget entry -- BH already
            # certified it as a statistical discovery, so it shouldn't
            # silently vanish between the CSV and the HTML report just
            # because the AR(1) half-life fit didn't imply reversion.
            # build_pair_entry marks these via has_reversion_estimate=False
            # and the widget shows them with the z-score/half-life fields
            # blank rather than treating "clear" and "no signal" as the
            # same thing.
            price_a_full = combined_df[ticker_a]
            price_b_full = combined_df[ticker_b]
            pair_entries.append(
                build_pair_entry(
                    row=row,
                    price_a_full=price_a_full,
                    price_b_full=price_b_full,
                    spread_full=full_spread_series,
                    rolling_mean_full=rolling_mean,
                    rolling_std_full=rolling_std,
                    z_trading=z_trading,
                    estimation_end_date=estimation_end_date,
                    z_threshold=config.Z_THRESHOLD,
                    recent_breach_window=config.RECENT_BREACH_WINDOW,
                    name_a=row["name_a"],
                    name_b=row["name_b"],
                    momentum=momentum_summary,
                )
            )

        results.append(row)

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values("eg_pvalue").reset_index(drop=True)

    # Sort widget pairs by p-value too, matching the CSV ordering
    pair_entries.sort(key=lambda p: p["stats"]["eg_pvalue"])

    group_summary = build_group_summary(
        sector_name=sector_name,
        basket=ticker_basket,
        estimation_df=estimation_df,
        trading_df=trading_df,
        n_pairs_tested=n_pairs,
        fdr_level=config.FDR_LEVEL,
        bh_critical_pvalue=critical_pvalue,
        n_passed=len(pair_entries),
    )

    print(f"Done with {sector_name}. {n_passed} / {n_pairs} pairs passed Benjamini-Hochberg.")
    return results_df, group_summary, pair_entries


def run():
    """
    Runs every sector in config.SECTORS through the pipeline independently,
    then combines them into a single CSV (tagged by `sector`) and a single
    HTML widget with a sector-switching dropdown.
    """
    all_results = []
    sector_payloads = {}
    name_cache = {}  # shared across sectors so overlapping tickers are looked up once

    for sector_name, ticker_basket in config.SECTORS.items():
        try:
            results_df, group_summary, pair_entries = run_sector(
                sector_name, ticker_basket, name_cache=name_cache
            )
        except ValueError as e:
            print(f"Skipping sector {sector_name}: {e}")
            continue

        all_results.append(results_df)
        sector_payloads[sector_name] = build_payload(group_summary, pair_entries)

    if not all_results:
        raise ValueError("No sector produced results -- check data availability for all baskets.")

    combined_results_df = pd.concat(all_results, ignore_index=True)
    combined_results_df = combined_results_df.sort_values(
        ["sector", "eg_pvalue"]
    ).reset_index(drop=True)

    csv_path = write_results(combined_results_df, config.OUTPUT_DIR)

    multi_payload = {
        "sector_list": list(sector_payloads.keys()),
        "sectors": sector_payloads,
    }
    html_path = write_widget(multi_payload, config.OUTPUT_DIR)

    total_passed = sum(len(p["pairs"]) for p in sector_payloads.values())
    total_tested = sum(p["group"]["n_pairs_tested"] for p in sector_payloads.values())
    print(f"\n=== All sectors done. {total_passed} / {total_tested} pairs passed BH overall. ===")
    print(f"CSV written to {csv_path}")
    print(f"HTML report written to {html_path}")
    return combined_results_df, multi_payload


if __name__ == "__main__":
    run()