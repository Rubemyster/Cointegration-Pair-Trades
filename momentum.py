"""
Momentum / turning-point diagnostics for pairs that already passed
Benjamini-Hochberg and have a valid AR(1) half-life estimate
(has_reversion_estimate=True).

This module is entirely downstream of, and never feeds back into, the
statistical screen: it doesn't touch passes_bh, the z-score, or the
threshold-breach flag. It's a discretionary overlay for judging *when*
within an already-flagged pair might be worth a closer look -- never a
trade instruction, same guardrail as the rest of the tool.

Two independent, model-native lenses, both built from series/fits the
pipeline already computes -- no new statistical model or lookback window
is introduced:

1. AR(1)-implied drift vs. realized move (ar1_residual_signal)
   Reuses the same AR(1)/OU regression (a, b) that half_life.fit_ar1
   already fits on the ESTIMATION-window spread, and asks: in the trading
   window, is the day-to-day realized move now agreeing in sign with what
   that fitted model always predicted should eventually happen (a pull
   back toward the mean), or is the spread still being driven by
   something the model doesn't capture? Applying (a, b) forward into the
   trading window is the same estimation/trading discipline the static
   TLS hedge ratio already relies on -- a and b are never re-fit here.

2. Z-score velocity / acceleration (zscore_velocity)
   First and second differences of the z-score series zscore.py already
   computes causally. No new series, no new lookback window for the base
   signal -- just how fast, and whether, the standardized position is
   turning.

Both lenses are windowed by config.RECENT_BREACH_WINDOW, the same "how
many recent sessions count as *now*" window flag_threshold_breach already
uses, so all "recent" framing in the tool stays on one knob.

Guardrail: classify_momentum's 0.6/0.4 thresholds are a simple rule of
thumb, not a statistically corrected test the way Benjamini-Hochberg is --
there's no FDR-style correction for tuning momentum thresholds against a
pair's own history, so treat the resulting "read" as a prompt for manual
judgement, not a calibrated probability.
"""

import numpy as np


def ar1_predicted_moves(spread_full, ar1_alpha, ar1_beta):
    """
    Predicted next-step move at every point in spread_full, using the
    AR(1) (a, b) fitted on the ESTIMATION window only:

        e_hat[t] = a + b * spread[t-1]

    Returned as a pandas Series aligned to spread_full's index (first
    entry NaN -- no t-1 lag available there).
    """
    return ar1_alpha + ar1_beta * spread_full.shift(1)


def ar1_residual_signal(spread_full, ar1_alpha, ar1_beta, trading_index, recent_window):
    """
    Compares realized moves to AR(1)-predicted moves over the trading
    window and summarizes the most recent `recent_window` sessions.

    `spread_full` should be the FULL (estimation + trading) spread series,
    so the earliest trading-window day can legitimately draw its lagged
    value from the estimation-window tail -- that data already existed at
    that point in time, mirroring the causality note in
    zscore.rolling_mean_std.

    Returns a dict:
      - predicted / realized / residual: full-index pd.Series (residual =
        realized - predicted; near zero means the AR(1) dynamics hold)
      - sign_agreement_recent: fraction (0-1) of the last `recent_window`
        valid trading-window sessions where the realized move shares a
        sign with the model-predicted move (both pulling back toward the
        mean, or both still pushing away). None if no valid sessions.
      - latest_predicted / latest_realized / latest_residual: most recent
        trading-window values (None if unavailable).
    """
    realized = spread_full.diff()
    predicted = ar1_predicted_moves(spread_full, ar1_alpha, ar1_beta)
    residual = realized - predicted

    predicted_trading = predicted.loc[trading_index].dropna()
    realized_trading = realized.loc[trading_index].dropna()
    aligned_idx = predicted_trading.index.intersection(realized_trading.index)

    if len(aligned_idx) == 0:
        return {
            "predicted": predicted,
            "realized": realized,
            "residual": residual,
            "sign_agreement_recent": None,
            "latest_predicted": None,
            "latest_realized": None,
            "latest_residual": None,
        }

    recent_idx = aligned_idx[-recent_window:]
    p_recent = predicted_trading.loc[recent_idx]
    r_recent = realized_trading.loc[recent_idx]

    agreements = np.sign(p_recent.values) == np.sign(r_recent.values)
    sign_agreement_recent = float(np.mean(agreements)) if len(agreements) > 0 else None

    latest_idx = aligned_idx[-1]
    return {
        "predicted": predicted,
        "realized": realized,
        "residual": residual,
        "sign_agreement_recent": sign_agreement_recent,
        "latest_predicted": float(predicted_trading.loc[latest_idx]),
        "latest_realized": float(realized_trading.loc[latest_idx]),
        "latest_residual": float(residual.loc[latest_idx]),
    }


def zscore_velocity(z_full, trading_index, recent_window):
    """
    First (delta_z) and second (delta2_z) differences of the z-score
    series.

    Takes the FULL z-score series (estimation + trading, as produced in
    main.py by zscore.rolling_zscore's underlying calc) rather than the
    trading-window slice alone, for the same causality reason documented
    in zscore.rolling_mean_std: the first few trading-window points can
    legitimately draw their velocity from the estimation-window tail,
    since that data already existed at those points in time.

    Returns a dict:
      - delta_z / delta2_z: pd.Series (full index)
      - latest_delta_z / latest_delta2_z: most recent valid values in the
        trading window (None if unavailable)
      - turning_recent: True if |z| is smaller now than it was
        `recent_window` valid sessions ago -- a simple endpoint-to-endpoint
        directional read, not a smoothed trend fit. None if fewer than 2
        valid trading-window z-score observations exist.
    """
    delta_z_full = z_full.diff()
    delta2_z_full = delta_z_full.diff()

    delta_z = delta_z_full.loc[trading_index]
    delta2_z = delta2_z_full.loc[trading_index]

    valid_delta = delta_z.dropna()
    valid_delta2 = delta2_z.dropna()
    valid_z = z_full.loc[trading_index].dropna()

    latest_delta_z = float(valid_delta.iloc[-1]) if len(valid_delta) > 0 else None
    latest_delta2_z = float(valid_delta2.iloc[-1]) if len(valid_delta2) > 0 else None

    turning_recent = None
    if len(valid_z) >= 2:
        window = valid_z.tail(min(recent_window, len(valid_z)))
        if len(window) >= 2:
            turning_recent = bool(abs(window.iloc[-1]) < abs(window.iloc[0]))

    return {
        "delta_z": delta_z,
        "delta2_z": delta2_z,
        "latest_delta_z": latest_delta_z,
        "latest_delta2_z": latest_delta2_z,
        "turning_recent": turning_recent,
    }


def classify_momentum(sign_agreement_recent, turning_recent):
    """
    Combines the two lenses into a single plain-language read. Never a
    trade instruction -- describes what the diagnostics show, same
    guardrail the rest of the tool follows (see module docstring re:
    these thresholds not being statistically corrected).
    """
    if sign_agreement_recent is None or turning_recent is None:
        return "insufficient data"
    if sign_agreement_recent >= 0.6 and turning_recent:
        return "reversion signs agree"
    if sign_agreement_recent < 0.4 and not turning_recent:
        return "still diverging"
    return "mixed signal"


def build_momentum_entry(spread_full, ar1_alpha, ar1_beta, z_full, trading_index, recent_window):
    """
    Assembles the full momentum diagnostic block for one pair. Callers
    (main.py) should only call this when a pair has a valid AR(1)
    half-life (window is not None) -- same population has_reversion_estimate
    already scopes the z-score/threshold fields to.
    """
    ar1 = ar1_residual_signal(spread_full, ar1_alpha, ar1_beta, trading_index, recent_window)
    zvel = zscore_velocity(z_full, trading_index, recent_window)
    read = classify_momentum(ar1["sign_agreement_recent"], zvel["turning_recent"])

    return {
        "ar1": ar1,
        "zvel": zvel,
        "read": read,
    }
