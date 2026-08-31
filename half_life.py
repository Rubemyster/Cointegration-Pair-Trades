"""
Half-life of mean reversion, via an AR(1) / Ornstein-Uhlenbeck approximation
fitted to the estimation-window spread.
"""

import numpy as np
import statsmodels.api as sm


def fit_ar1(spread):
    """
    Fits: delta_spread[t] = a + b * spread[t-1] + e[t]

    Returns (a, b, half_life):
      - a, b: the fitted intercept/slope -- the full AR(1) model, not just
        the derived half-life. momentum.py reuses these directly (as
        estimation-window-only parameters applied forward into the trading
        window, the same way the static TLS hedge ratio already is) to
        build a model-implied expected-move diagnostic. See momentum.py.
      - half_life: -ln(2) / b, in the same units as the spread's sampling
        frequency (trading days for daily data). None if b >= 0, since
        that implies the spread is not mean-reverting under this linear
        approximation (a positive or zero coefficient means deviations
        don't decay back toward the mean).
    """
    spread = np.asarray(spread, dtype=float)
    spread_lag = spread[:-1]
    delta_spread = spread[1:] - spread_lag

    X = sm.add_constant(spread_lag)
    model = sm.OLS(delta_spread, X).fit()
    a, b = model.params[0], model.params[1]

    half_life = None if b >= 0 else -np.log(2) / b
    return a, b, half_life


def compute_half_life(spread):
    """
    Convenience wrapper for callers that only need the half-life estimate.
    See fit_ar1 for the full (a, b, half_life) fit.
    """
    _, _, half_life = fit_ar1(spread)
    return half_life
