"""
Z-score computation: per-pair dynamic rolling window (sized off that pair's
half-life), rolling z-score over the full series, and a threshold-breach
flag applied only to the trading-window slice.
"""

import numpy as np
import pandas as pd


def determine_zscore_window(half_life, multiplier, min_window, max_window):
    """
    Window = round(multiplier * half_life), bounded to [min_window, max_window].
    Returns None if half_life is missing/invalid (e.g. non-mean-reverting fit).
    """
    if half_life is None or half_life <= 0 or np.isnan(half_life):
        return None
    window = int(round(multiplier * half_life))
    window = max(window, min_window)
    window = min(window, max_window)
    return window


def rolling_mean_std(spread_series, window):
    """
    Rolling mean and std of a spread series, computed causally (only data up
    to and including each date, within `window` bars, is used).

    Intended usage: pass the FULL spread series (estimation + trading) so
    the first few trading-window points can legitimately draw on the tail
    of the estimation window for their rolling stats -- that data already
    existed at those points in time, so this is not look-ahead.
    """
    rolling_mean = spread_series.rolling(window=window, min_periods=window).mean()
    rolling_std = spread_series.rolling(window=window, min_periods=window).std(ddof=0)
    return rolling_mean, rolling_std


def rolling_zscore(spread_series, window):
    """
    Rolling z-score of a spread series. See rolling_mean_std for the
    causality note -- the same logic applies here.
    """
    rolling_mean, rolling_std = rolling_mean_std(spread_series, window)
    return (spread_series - rolling_mean) / rolling_std


def flag_threshold_breach(z_trading_window, threshold, recent_window=5):
    """
    Flags whether the pair is *currently or recently* diverging: True only
    if |z| > threshold at some point within the last `recent_window` valid
    (non-NaN) z-score observations -- not "ever, at any point in the whole
    trading window". A pair that breached once weeks ago and has since
    reverted no longer counts as breached.

    Returns (breached: bool, breach_date, max_abs_z: float).
      - breach_date is the MOST RECENT breach date within the recent
        window (None if not breached), since that's what "still in
        breach" needs -- not the first breach ever.
      - max_abs_z is still computed over the FULL trading window (not
        just the recent slice), since "how extreme did this get" remains
        useful context even when the breach flag itself is recency-scoped.

    This is a diagnostic "relationship may be diverging" flag only --
    no trade entry/exit logic is implied or triggered by it.
    """
    abs_z = z_trading_window.abs()
    valid = abs_z.dropna()
    if valid.empty:
        return False, None, np.nan

    max_abs_z = valid.max()

    recent = valid.tail(recent_window)
    breached_mask = recent > threshold
    if breached_mask.any():
        most_recent_breach_date = recent.index[breached_mask][-1]
        return True, most_recent_breach_date, max_abs_z

    return False, None, max_abs_z