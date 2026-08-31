"""
Trade log: a simple, persistent record of which pairs you've manually
entered and exited, independent of any single screener run.

This module does bookkeeping only -- no P&L, no position sizing, no
entry/exit signal generation (consistent with the rest of this tool).
Its only job is to remember which pairs you're currently in and let
trades_report.py monitor them going forward.

Each trade snapshots the statistical relationship (hedge ratio, half-life,
z-score window, the p-value it screened on) exactly as it stood on the
screener run you entered from. This matters because trades_report.py
holds that relationship FIXED rather than re-fitting it on every check-in
-- mirroring the main pipeline's own "static hedge ratio, no rolling
re-estimation" choice for the trading window. Snapshotting at entry time
is what makes that possible.

Storage: a flat trades.json file, NOT timestamped like the CSV/HTML
outputs -- this one needs to persist and be updated in place across runs.
"""

import json
import os
import uuid
from datetime import datetime

DEFAULT_TRADES_PATH = "trades.json"


def load_trades(path=DEFAULT_TRADES_PATH):
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def save_trades(trades, path=DEFAULT_TRADES_PATH):
    with open(path, "w") as f:
        json.dump(trades, f, indent=2, default=str)


def _match_row(results_df, ticker_a, ticker_b, sector=None):
    """
    Order-insensitive lookup of a pair's row in a results table (works on
    either the combined_results_df from main.run() or a pairs_screen_*.csv
    loaded back in with pandas).
    """
    mask = (
        ((results_df["ticker_a"] == ticker_a) & (results_df["ticker_b"] == ticker_b))
        | ((results_df["ticker_a"] == ticker_b) & (results_df["ticker_b"] == ticker_a))
    )
    if sector is not None:
        mask &= results_df["sector"] == sector
    matches = results_df[mask]
    if matches.empty:
        return None
    return matches.iloc[0]


def _safe_float(v):
    try:
        if v is None:
            return None
        f = float(v)
        return None if f != f else f  # NaN check without importing numpy here
    except (TypeError, ValueError):
        return None


def add_trade(ticker_a, ticker_b, results_df, entry_date=None, note=None,
              path=DEFAULT_TRADES_PATH):
    """
    Logs a new active trade, snapshotting the statistical relationship from
    `results_df` at entry time.

    `results_df` should be whatever results table you actually traded off
    of -- e.g. pd.read_csv() of the relevant pairs_screen_*.csv, or the
    combined_results_df returned directly by main.run(). Raises if the
    pair isn't found, rather than logging a trade with no snapshot to
    monitor against later.
    """
    row = _match_row(results_df, ticker_a, ticker_b)
    if row is None:
        raise ValueError(
            f"{ticker_a}/{ticker_b} not found in the supplied results -- "
            "pass the results table from the run you actually traded off of."
        )

    entry_date = entry_date or datetime.today().strftime("%Y-%m-%d")

    trade = {
        "trade_id": uuid.uuid4().hex[:8],
        "sector": row["sector"],
        "ticker_a": row["ticker_a"],
        "ticker_b": row["ticker_b"],
        "entry_date": entry_date,
        "exit_date": None,
        "note": note,
        "entry_snapshot": {
            "eg_pvalue": _safe_float(row["eg_pvalue"]),
            "hedge_ratio_beta": _safe_float(row["hedge_ratio_beta"]),
            "intercept_alpha": _safe_float(row["intercept_alpha"]),
            "half_life_days": _safe_float(row["half_life_days"]),
            "zscore_window": _safe_float(row["zscore_window"]),
            "latest_zscore_at_entry": _safe_float(row["latest_zscore"]),
        },
    }

    if trade["entry_snapshot"]["hedge_ratio_beta"] is None or trade["entry_snapshot"]["zscore_window"] is None:
        raise ValueError(
            f"{ticker_a}/{ticker_b} didn't pass Benjamini-Hochberg (or has no half-life fit) "
            "in the supplied results, so there's no hedge ratio/window to monitor against. "
            "Only pairs that passed the screen can be logged."
        )

    trades = load_trades(path)
    trades.append(trade)
    save_trades(trades, path)
    return trade


def close_trade(trade_id, exit_date=None, path=DEFAULT_TRADES_PATH):
    trades = load_trades(path)
    for t in trades:
        if t["trade_id"] == trade_id:
            t["exit_date"] = exit_date or datetime.today().strftime("%Y-%m-%d")
            save_trades(trades, path)
            return t
    raise ValueError(f"No trade found with id {trade_id}")


def list_trades(active_only=False, path=DEFAULT_TRADES_PATH):
    trades = load_trades(path)
    if active_only:
        trades = [t for t in trades if t["exit_date"] is None]
    return trades


if __name__ == "__main__":
    import argparse
    import glob

    import pandas as pd

    parser = argparse.ArgumentParser(description="Manage the active-trades log.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Log a new trade")
    p_add.add_argument("ticker_a")
    p_add.add_argument("ticker_b")
    p_add.add_argument("--entry-date", default=None, help="YYYY-MM-DD, defaults to today")
    p_add.add_argument("--note", default=None)
    p_add.add_argument(
        "--csv", default=None,
        help="Path to a pairs_screen_*.csv; defaults to the most recent one in output/",
    )

    p_close = sub.add_parser("close", help="Close an existing trade")
    p_close.add_argument("trade_id")
    p_close.add_argument("--exit-date", default=None, help="YYYY-MM-DD, defaults to today")

    p_list = sub.add_parser("list", help="List logged trades")
    p_list.add_argument("--active-only", action="store_true")

    args = parser.parse_args()

    if args.command == "add":
        csv_path = args.csv
        if csv_path is None:
            candidates = sorted(glob.glob(os.path.join("output", "pairs_screen_*.csv")))
            if not candidates:
                raise SystemExit(
                    "No pairs_screen_*.csv found in output/ -- run main.py first, or pass --csv."
                )
            csv_path = candidates[-1]
        results_df = pd.read_csv(csv_path)
        trade = add_trade(
            args.ticker_a, args.ticker_b, results_df,
            entry_date=args.entry_date, note=args.note,
        )
        print(f"Logged trade {trade['trade_id']}: {trade['ticker_a']}/{trade['ticker_b']} (from {csv_path})")

    elif args.command == "close":
        trade = close_trade(args.trade_id, exit_date=args.exit_date)
        print(f"Closed trade {trade['trade_id']} on {trade['exit_date']}")

    elif args.command == "list":
        for t in list_trades(active_only=args.active_only):
            status = "ACTIVE" if t["exit_date"] is None else f"CLOSED {t['exit_date']}"
            print(
                f"{t['trade_id']}  {t['ticker_a']}/{t['ticker_b']} ({t['sector']})  "
                f"entered {t['entry_date']}  [{status}]"
            )
