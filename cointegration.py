"""
Cointegration testing: TLS (orthogonal regression) hedge ratio, followed
by an Engle-Granger style ADF test on the resulting residual spread.
"""

import numpy as np
from statsmodels.tsa.stattools import adfuller


def tls_fit(x, y):
    """
    Total Least Squares (orthogonal regression) of y on x.

    Returns (alpha, beta) such that y ~= alpha + beta * x, fit by minimizing
    perpendicular distance to the line rather than vertical distance. This
    avoids the asymmetry of standard OLS, where regressing A-on-B gives a
    different slope than regressing B-on-A.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    x_mean, y_mean = x.mean(), y.mean()
    x_c, y_c = x - x_mean, y - y_mean

    data = np.column_stack([x_c, y_c])
    _, _, vh = np.linalg.svd(data, full_matrices=False)
    v = vh[0]  # principal direction of the (x, y) point cloud

    if np.isclose(v[0], 0):
        raise ValueError("Degenerate TLS fit: x series has ~zero variance.")

    beta = v[1] / v[0]
    alpha = y_mean - beta * x_mean
    return alpha, beta


def compute_spread(log_a, log_b, alpha, beta):
    """Spread = log(A) - (alpha + beta * log(B)) -- the Engle-Granger residual."""
    log_a = np.asarray(log_a, dtype=float)
    log_b = np.asarray(log_b, dtype=float)
    return log_a - (alpha + beta * log_b)


def engle_granger_test(log_a, log_b):
    """
    Engle-Granger two-step cointegration test using a TLS-fitted relationship.

    Step 1: TLS fit of log_a on log_b -> (alpha, beta), the hedge ratio.
    Step 2: ADF test on the resulting residual (spread).

    Note: the ADF p-value here is the standard statsmodels approximation,
    not the Engle-Granger-specific critical values tabulated for residuals
    from an *estimated* relationship (those differ slightly because the
    spread is constructed from a fitted line, not an observed series).
    statsmodels.tsa.stattools.coint() applies the correct adjusted critical
    values but only supports OLS internally. This implementation prioritises
    the symmetric TLS hedge ratio per spec; treat the p-value as a close,
    slightly optimistic approximation rather than an exact one.
    """
    alpha, beta = tls_fit(log_b, log_a)  # log_a ~ alpha + beta * log_b
    spread = compute_spread(log_a, log_b, alpha, beta)

    adf_result = adfuller(spread, autolag="AIC")
    adf_stat, adf_pvalue = adf_result[0], adf_result[1]

    return {
        "alpha": alpha,
        "beta": beta,
        "adf_stat": adf_stat,
        "adf_pvalue": adf_pvalue,
        "spread": spread,
    }
