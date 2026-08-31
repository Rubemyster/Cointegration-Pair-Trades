"""
Data layer: pulls adjusted close prices via yfinance and splits the
result into an estimation window and a trading window.
"""

from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf


def fetch_ticker_names(tickers, cache=None):
    """
    Best-effort lookup of each ticker's display name (company short/long
    name) via yfinance, for presentation in the CSV/widget only. This is
    never used in any statistical calculation -- a slow, missing, or wrong
    lookup can only affect how a pair is *labelled*, never the screening
    result itself, so failures are swallowed and we fall back to the raw
    ticker symbol.

    `cache` (dict) can be passed in and reused across sectors so a ticker
    appearing in more than one sector is only looked up once.
    """
    if cache is None:
        cache = {}
    missing = [t for t in tickers if t not in cache]
    for t in missing:
        try:
            info = yf.Ticker(t).info
            name = info.get("shortName") or info.get("longName")
            cache[t] = name if name else t
        except Exception:
            cache[t] = t
    return {t: cache[t] for t in tickers}


def fetch_latest_intraday_prices(tickers):
    """
    Best-effort fetch of each ticker's most recent traded price (via
    yfinance's fast_info) for splicing in as an "as of right now" data
    point when the pipeline is run mid-session. This is a live/unadjusted
    quote, not a dividend/split-adjusted close like the rest of the series
    -- an acceptable approximation for spread/z-score purposes, but not
    the same kind of number as the historical closes.

    Failures are swallowed per-ticker (never block the run): a ticker
    missing from the returned dict just means fetch_price_data falls back
    to forward-filling its last known close for the appended row instead.
    """
    latest = {}
    for t in tickers:
        try:
            fast_info = yf.Ticker(t).fast_info
            price = fast_info.get("last_price") if hasattr(fast_info, "get") else fast_info.last_price
            if price is not None:
                latest[t] = float(price)
        except Exception:
            continue
    return latest


def fetch_price_data(tickers, total_months, end_date=None, max_missing_frac=0.05,
                      include_latest_intraday=True):
    """
    Pulls daily adjusted close prices for `tickers` covering approximately
    `total_months` of history, ending at `end_date` (defaults to today).

    Drops any ticker with more than `max_missing_frac` of its data missing
    over the window (e.g. due to a late listing date or a delisting),
    then forward-fills small gaps and drops any remaining incomplete rows
    so all surviving tickers share an identical, gap-free date index.

    If `include_latest_intraday` is True and today's daily bar isn't
    available yet (i.e. we're running mid-session, before yfinance has
    published today's close), an extra row dated today is appended using
    each ticker's latest live quote via fetch_latest_intraday_prices, so
    the trading-window z-score reflects where the pair is *right now*
    rather than lagging to the previous close. This only ever extends the
    TRADING window (today is always the most recent date) -- it can never
    leak into the estimation-window cointegration fit.
    """
    if end_date is None:
        end_date = datetime.today()
    # buffer beyond the nominal window to comfortably cover weekends/holidays
    start_date = end_date - timedelta(days=int(total_months * 31) + 15)

    raw = yf.download(
        tickers,
        start=start_date.strftime("%Y-%m-%d"),
        end=end_date.strftime("%Y-%m-%d"),
        auto_adjust=True,  # 'Close' becomes the dividend/split-adjusted close
        progress=False,
        group_by="column",
    )

    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"].copy()
    else:
        # yfinance collapses to a flat frame when only one ticker is passed
        prices = raw[["Close"]].copy()
        prices.columns = [tickers[0]] if isinstance(tickers, list) else [tickers]

    prices = prices.dropna(axis=1, how="all")

    missing_frac = prices.isna().mean()
    keep = missing_frac[missing_frac <= max_missing_frac].index.tolist()
    dropped = sorted(set(prices.columns) - set(keep))
    if dropped:
        print(f"Dropping tickers with excessive missing data (>{max_missing_frac:.0%}): {dropped}")
    prices = prices[keep]

    prices = prices.ffill().dropna()

    if include_latest_intraday and len(prices) > 0:
        today = pd.Timestamp(datetime.today().date())
        if prices.index[-1].normalize() < today:
            latest = fetch_latest_intraday_prices(list(prices.columns))
            if latest:
                # fall back to last known close for any ticker the live
                # lookup failed on, rather than dropping the whole row
                row_values = {t: latest.get(t, prices[t].iloc[-1]) for t in prices.columns}
                new_row = pd.DataFrame([row_values], index=[today])
                prices = pd.concat([prices, new_row])
                n_live = len(latest)
                print(
                    f"Appended intraday row for {today.strftime('%Y-%m-%d')}: "
                    f"{n_live}/{len(prices.columns)} tickers got a live quote "
                    f"(rest carried forward from last close)."
                )

    return prices


def split_windows(prices, estimation_months, trading_months, trading_days_per_month=21):
    """
    Slices the most recent (estimation_months + trading_months) of data
    into an estimation_df (earlier portion) and trading_df (final portion).
    Returns (estimation_df, trading_df, combined_df).
    """
    est_days = estimation_months * trading_days_per_month
    trade_days = trading_months * trading_days_per_month
    required = est_days + trade_days

    if len(prices) < required:
        raise ValueError(
            f"Not enough aligned data: have {len(prices)} rows, need at least {required}. "
            "Try a smaller basket, fewer dropped tickers, or shorter windows."
        )

    combined = prices.iloc[-required:]
    estimation_df = combined.iloc[:est_days]
    trading_df = combined.iloc[est_days:]
    return estimation_df, trading_df, combined