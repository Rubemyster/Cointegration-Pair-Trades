---
name: pairs-divergence-research
description: Researches the likely real-world cause behind a pair flagged by a Benjamini-Hochberg pairs-trading screener (a pasted row from its pairs_screen_*.csv output, a pasted JSON pair entry from its HTML widget, or a plain-language mention of two tickers that diverged). Trigger this whenever the user pastes a screener CSV row or JSON pair record, mentions a "breach", "z-score", "threshold_breached", or "divergence" for two equities, or asks things like "why did this pair diverge", "what happened between X and Y", or "research this pair" in the context of a statistical/cointegrated pairs relationship. Distinguishes mechanical causes (ex-dividend, index rebalance, earnings-date mismatch, corporate actions) from genuine single-name catalysts (M&A, earnings surprise, rating change, litigation) from sector-wide moves, anchors all searches to the correct dates so estimation-window news isn't mistaken for a trading-window cause, and ends in a classification useful for manual economic-rationale review. Do NOT use for generic "look up this stock" requests that aren't about a screened pair's divergence.
---

# Pairs Divergence Research

## Purpose

The pairs-trading screener this skill supports is statistics-only by design
(TLS cointegration + Engle-Granger ADF test, Benjamini-Hochberg FDR
correction, half-life, dynamic z-score, threshold flag). It deliberately
stops short of any economic judgement — that step is manual. This skill
*is* that manual step, automated: given one pair's row, find out what's
actually happening in the real world that could explain the statistical
divergence, and hand back a classification the user can act on.

**This skill never outputs a trade recommendation.** Its only job is to
tell the user *why* a pair might be diverging and *whether that reason
suggests the divergence is likely temporary or structural* — the trading
decision itself stays with the user.

## Step 0 — Parse the input

The user will typically paste one row. Recognize either shape:

**CSV row** (columns, in the order the tool writes them):
`sector, ticker_a, ticker_b, name_a, name_b, eg_adf_stat, eg_pvalue, fdr_level, bh_critical_pvalue, passes_bh, hedge_ratio_beta, intercept_alpha, half_life_days, zscore_window, latest_zscore, max_abs_zscore, threshold_breached, breach_date`

If they paste values without a header row, map positionally in that exact
order. If a header row is present, map by name instead (column order can
drift across tool versions).

**JSON pair entry** (from the HTML widget's payload) — has nested `stats`,
`series`, and `zscore_series` objects. Prefer this shape when available: it
includes the actual price/spread series, which Step 1 below otherwise has
to infer indirectly.

If what's pasted matches neither shape well, ask the user to paste the row
again or confirm the two tickers — don't guess at ticker symbols.

## Step 1 — Establish the anchor date and direction

Good research depends entirely on searching the right window. Get this
right before searching anything:

- **Anchor date**: use `breach_date` if present and not null. If
  `threshold_breached` is false or `breach_date` is empty, there's no
  single anchor — ask the user for the most recent date in the trading
  window (or ask them to paste the sector's `group_summary`/`trading_end`
  alongside the row), since "diverged, but never breached" still needs a
  date to search around.
- **Don't search pre-estimation-window news.** News from inside the
  estimation window is already baked into the fitted `hedge_ratio_beta`/
  `intercept_alpha` — it cannot explain a *trading-window* divergence. If
  the row/JSON doesn't include `estimation_end_date`, treat the ~4-6 weeks
  immediately before the anchor date as the primary search window and say
  so explicitly in the output, rather than silently guessing further back.
- **Direction**: if you have the `series` data (JSON shape), compute which
  leg actually over/underperformed over the trading window and by roughly
  how much — this tells you which ticker's news to weight more heavily,
  and lets you sanity-check that any news you find actually points the
  right way. If you only have the CSV row (no series), infer direction
  from `latest_zscore`'s sign together with `hedge_ratio_beta`, and treat
  it as provisional; note in the output that it's inferred, not measured.

## Step 2 — Screen out mechanical causes first

Before treating anything as a "real" catalyst, check for these — they're
the most common false positives in pairs research, because they produce a
genuine price gap with no fundamental content:

- Ex-dividend date for either ticker near the anchor date (mechanical
  price drop)
- Stock split, consolidation, rights issue, or bonus/scrip issue
- Index reshuffle (e.g. FTSE 100 ↔ 250 migration, S&P inclusion/exclusion)
  — causes passive-flow-driven moves unrelated to fundamentals
- Earnings-date mismatch — one leg reported and re-rated, the other hasn't
  yet
- Ticker validity — confirm the symbol is still actively listed under that
  ticker; a stale/delisted/renamed ticker will otherwise send you down a
  dead end (worth a first-pass sanity search: `"{ticker} delisted"` /
  `"{ticker} ticker change"`)

If one of these explains the gap, say so plainly and weight it heavily in
the final classification — it changes what kind of divergence this is.

## Step 3 — Search for a genuine catalyst, per ticker

For each of the two tickers, search (search engine, 3-8 queries total
across both names is usually enough — scale up only if results are thin
or conflicting):

- `"{name} news {month} {year}"` and `"{ticker} share price {date range}"`
- M&A: `"{name} merger"` / `"{name} acquisition"` / `"{name} takeover"`
- Earnings/guidance: `"{name} profit warning"` / `"{name} results {year}"`
- Ratings/analyst action: `"{name} downgrade"` / `"{name} price target"`
- Legal/regulatory: `"{name} investigation"` / `"{name} lawsuit"`
- Management: `"{name} CEO"` / `"{name} resigns"`

Weight results by how close their date is to the anchor date, and by
whether their direction (price up/down) matches what Step 1 found.

## Step 4 — Check idiosyncratic vs. sector-wide

Before concluding a single-name catalyst caused the divergence, sanity
check: does this look like the whole sector moved, with these two names
just having slightly different sensitivity to it? If the user has other
pairs from the same sector/run, ask whether other pairs show a
similar-direction move around the same date. If there's no macro/sector
news that would explain a broad move and the price action is genuinely
one-sided, idiosyncratic is more likely — but flag the ambiguity rather
than asserting one over the other without evidence.

## Step 5 — Output

Always end with a structured note in this shape (chat reply, not a file,
unless the user asks to save it):

```
## {ticker_a} / {ticker_b} — divergence research

**Anchor**: breach on {date} | latest z = {value} | window = {n} days
**Direction**: {which leg moved, and how} (measured / inferred)

**Mechanical check**: {ex-div / split / index / earnings-mismatch findings, or "none found"}

**{ticker_a}**: {what was found, dated, sourced — or "no relevant news found"}
**{ticker_b}**: {same}

**Sector context**: {idiosyncratic vs. sector-wide read, with reasoning}

**Classification**: one of —
  - Mechanical/technical — divergence may not revert on the statistical timeline
  - Idiosyncratic, likely temporary — consistent with the tool's mean-reversion thesis
  - Idiosyncratic, structural (e.g. confirmed M&A) — relationship may be permanently broken
  - Sector-wide — statistical pair intact, not a single-name story
  - Unexplained — no catalyst found; could be noise or not-yet-public information

**Sources**: {dated links}
```

Keep prose tight — this feeds a manual review step, not a report. If
nothing turns up, say so plainly rather than stretching thin evidence into
a story; "unexplained" is a legitimate and useful answer.

## Guardrails

- Never phrase the classification as a trade instruction ("buy/sell/enter/
  exit") — describe what was found and what it implies about the
  *statistical relationship*, and leave the decision to the user.
- Cite every factual claim with a dated source; don't state a catalyst as
  fact without one.
- If evidence conflicts (e.g. one source says upgrade, another downgrade),
  say so rather than picking one.
