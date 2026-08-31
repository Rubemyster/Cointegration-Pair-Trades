"""
Configuration for the pairs-trading screening tool.

Edit the constants below to change the universe, windows, or thresholds
between runs. Nothing else in the codebase should need to change for a
basic re-run with a different basket.
"""

# --- Universe ---
# Each key is a sector/basket run independently through the full pipeline
# (its own estimation/trading split, its own Engle-Granger pass, and its
# own Benjamini-Hochberg correction -- sectors are NOT pooled together for
# multiple-testing purposes, since pairs from unrelated sectors aren't part
# of the same family of hypotheses). The HTML widget lets you switch
# between sectors via a dropdown; the CSV contains all sectors, tagged by
# a `sector` column.
SECTORS = {
    # Financials FTSE 100 + FTSE 250
    "FINANCIALS": [
        "ABDN.L",
        "ADM.L",
        "AHT.L",
        "AJB.L",
        "ASHM.L",
        "AV.L",
        "BARC.L",
        "BEZ.L",
        "BGEO.L",
        "BNKR.L",
        "HSBA.L",
        "ICG.L",
        "INVP.L",
        "IPF.L",
        "JUP.L",
        "LGEN.L",
        "LLOY.L",
        "MNG.L",
        "NWG.L",
        "PHNX.L",
        "PRU.L",
        "SDR.L",
        "STAN.L",
        "STJ.L",
    ],
    # Energy, Utilities and Infrastructure
    "ENERGY_UTILITIES": [
        "BP.L",
        "CNA.L",
        "DCC.L",
        "ENOG.L",
        "HBR.L",
        "NG.L",
        "PNN.L",
        "SSE.L",
        "SVT.L",
        "TRIG.L",
        "UKW.L",
        "UU.L",
        "GCP.L",
        "HICL.L",
        "INPP.L",
        "FSFL.L",
    ],
    # Minerals & Mining
    "MATERIALS": [
        "AAL.L",
        "ANTO.L",
        "BHP.L",
        "CRDA.L",
        "FRES.L",
        "GLEN.L",
        "HOC.L",
        "JMAT.L",
        "RIO.L",
    ],
    # Industrial & Construction
    "INDUSTRIALS": [
        "BA.L",
        "BBY.L",
        "BKG.L",
        "BNZL.L",
        "DPLM.L",
        "GKN.L",
        "HILS.L",
        "IMI.L",
        "KIE.L",
        "MGNS.L",
        "MRO.L",
        "SMIN.L",
        "SPX.L",
        "WEIR.L",
    ],
    # Consumer
    "CONSUMER": [
        "ABF.L",
        "BME.L",
        "DOM.L",
        "DNLM.L",
        "EZJ.L",
        "GRG.L",
        "IHG.L",
        "MKS.L",
        "NXT.L",
        "PETS.L",
        "SBRY.L",
        "TSCO.L",
        "WTB.L",
    ],
    # Healthcare
    "HEALTHCARE": ["AZN.L", "GSK.L", "HIK.L", "SN.L", "CTEC.L"],
    # TMT
    "TMT": [
        "AAF.L",
        "AUTO.L",
        "BT-A.L",
        "EXPN.L",
        "INF.L",
        "ITV.L",
        "REL.L",
        "RMV.L",
        "SGE.L",
        "VOD.L",
        "WPP.L",
    ],
    # Real Estate
    "REAL_ESTATE": [
        "BLND.L",
        "BBOX.L",
        "DLN.L",
        "GPE.L",
        "LAND.L",
        "LMP.L",
        "SGRO.L",
        "UTG.L",
        "PHP.L",
        "HMSO.L",
    ],
    # Investment Trusts
    "INVESTMENT_TRUSTS": [
        "3IN.L",
        "ATT.L",
        "BRWM.L",
        "CTY.L",
        "FCIT.L",
        "HGT.L",
        "JAM.L",
        "JGGI.L",
        "MNKS.L",
        "PCT.L",
        "PSH.L",
        "RCP.L",
        "SMT.L",
    ],
    # Housebuilders -- distinct driver from REAL_ESTATE: build-and-sell on a
    # housing-starts/completions cycle, not hold-and-lease like the REITs
    # above. Mortgage rates and planning consents are the shared exposure.
    "UK_HOUSEBUILDERS": [
        "BDEV.L",  # Barratt Developments -- added, verify before use
        "PSN.L",  # Persimmon -- added, verify before use
        "TW.L",  # Taylor Wimpey -- added, verify before use
        "BWY.L",  # Bellway -- added, verify before use
    ],
    # Money-center and large regional banks -- same rate/credit-cycle exposure
    "US_BANKS": [
        "JPM",
        "BAC",
        "WFC",
        "C",
        "USB",
        "PNC",
        "TFC",
        "COF",
        "MTB",
        "FITB",
        "RF",
        "KEY",
        "CFG",
        "HBAN",
        "ZION",
        "SNV",  # Synovus -- added, verify before use
        "FHN",  # First Horizon -- added, verify before use
        "WBS",  # Webster Financial -- added, verify before use
        "PNFP",  # Pinnacle Financial Partners -- added, verify before use
    ],
    # Integrated and E&P oil & gas -- same commodity price driver
    "US_OIL_GAS": [
        "XOM",
        "CVX",
        "COP",
        "OXY",
        "MPC",
        "PSX",
        "VLO",
        "HES",
        "DVN",
        "FANG",
        "EOG",  # EOG Resources -- added, verify before use
        "APA",  # APA Corp -- added, verify before use
        "CTRA",  # Coterra Energy -- added, verify before use
    ],
    # Legacy network carriers -- same fuel-cost/demand cyclicality
    "US_AIRLINES": ["DAL", "UAL", "AAL", "LUV", "ALK", "JBLU"],
    # Large-format discount/grocery retail -- same consumer-spending driver
    "US_RETAIL": ["WMT", "TGT", "KR", "COST", "DG", "DLTR", "BBY", "ROST", "TJX"],
    # National homebuilders -- same rates/housing-cycle exposure
    "US_HOMEBUILDERS": ["DHI", "LEN", "PHM", "NVR", "TOL", "KBH", "MTH"],
    # Multi-line and life/P&C insurers -- same rate/underwriting-cycle exposure
    "US_INSURANCE": [
        "TRV", "ALL", "PGR", "CB", "AIG", "MET", "PRU", "AFL", "HIG",
        "LNC",  # Lincoln National -- added, verify before use
        "UNM",  # Unum Group -- added, verify before use
        "GL",  # Globe Life -- added, verify before use
    ],
    # Regulated electric utilities -- same rate-regulation/rates exposure
    "US_UTILITIES": [
        "DUK", "SO", "D", "AEP", "EXC", "XEL", "ED", "PEG", "WEC", "ES",
        "PPL",  # PPL Corp -- added, verify before use
        "FE",  # FirstEnergy -- added, verify before use
        "AEE",  # Ameren -- added, verify before use
    ],
    # Premium automakers + core supplier -- same auto-cycle/input-cost driver
    "DE_AUTO": ["BMW.DE", "MBG.DE", "VOW3.DE", "PAH3.DE", "CON.DE"],
    # Bulk/specialty chemicals -- same energy-input-cost driver
    "DE_CHEMICALS": ["BAS.DE", "LXS.DE", "WCH.DE", "1COV.DE", "SY1.DE"],
    # Banking and reinsurance -- same rate-cycle exposure
    "DE_BANKS_INSURANCE": ["DBK.DE", "CBK.DE", "ALV.DE", "MUV2.DE", "HNR1.DE"],
    # Capital-goods / industrial engineering -- same capex-cycle driver
    "DE_INDUSTRIALS": ["SIE.DE", "MTX.DE", "HEI.DE", "GEA.DE", "KGX.DE"],
    # Power generation and utilities -- same energy-transition/regulation driver
    "DE_UTILITIES_ENERGY": ["EOAN.DE", "RWE.DE", "ENR.DE"],
    "US_SEMICONDUCTORS": [
        "NVDA", "AMD", "INTC", "TXN", "QCOM", "AVGO", "MU", "ADI", "MRVL",
        "ON",  # ON Semiconductor -- added, verify before use
        "SWKS",  # Skyworks Solutions -- added, verify before use
        "MPWR",  # Monolithic Power Systems -- added, verify before use
    ],
    "US_PHARMA": ["PFE", "MRK", "BMY", "LLY", "ABBV", "JNJ", "GILD", "AMGN"],
    "US_REIT": ["PLD", "AMT", "EQIX", "O", "SPG", "PSA", "WELL", "DLR"],
    "US_STAPLES": [
        "PG", "KO", "PEP", "CL", "KMB", "GIS", "KHC", "MDLZ",
        "CLX",  # Clorox -- added, verify before use
        "CHD",  # Church & Dwight -- added, verify before use
        "HSY",  # Hershey -- added, verify before use
    ],
    "US_ASSET_MANAGERS": ["BLK", "BX", "KKR", "APO", "TROW", "BEN"],
    # North American Class I freight rail -- same freight-volume/fuel-cost
    # driver. CNI and CP are Canadian companies but both carry a primary
    # NYSE listing quoted in USD, so they satisfy the same-currency rule
    # for this basket without needing a separate Canadian listing.
    "US_RAILROADS": ["UNP", "CSX", "NSC", "CNI", "CP"],
    # Wireline/wireless carriers and cable -- same subscriber-growth/
    # capex-cycle and debt-load rate sensitivity.
    "US_MEDIA_TELECOM": ["T", "VZ", "CMCSA", "CHTR", "TMUS"],
    # Gold miners -- one of the cleanest single-commodity drivers available:
    # the gold price. AU is AngloGold Ashanti's NYSE ADR (South African
    # company), included for the same reason as CNI/CP above -- USD-listed,
    # so it fits this basket without leaving the currency family.
    "US_GOLD_MINERS": ["GOLD", "NEM", "AEM", "KGC", "AU"],
    # Card networks and consumer-credit issuers -- same consumer-spending/
    # credit-cycle driver.
    "US_PAYMENTS": ["V", "MA", "AXP", "DFS", "SYF"],
    # Prime defense contractors -- same driver: US defense budget cycle,
    # program award timing.
    "US_DEFENSE_AEROSPACE": ["LMT", "RTX", "NOC", "GD", "LHX"],
    "DE_HEALTHCARE": ["FRE.DE", "FME.DE", "SHL.DE", "MRK.DE", "BAYN.DE"],
    # Now includes mid-cap residential landlords alongside the large-cap 3 --
    # same subsector (German residential rent-regulated housing), same driver.
    # (*) = mid-cap, verify before use
    "DE_REAL_ESTATE": ["VNA.DE", "LEG.DE", "DWNI.DE", "TAG.DE", "AT1.DE", "GYC.DE", "DIC.DE"],
    # Enterprise/vertical software -- same driver: software spend cycle,
    # subscription-revenue multiples. Note: Nemetschek's Xetra ticker is
    # NEM.DE -- unrelated to "NEM" (Newmont) in US_GOLD_MINERS above; the
    # ".DE" suffix keeps them as distinct dict entries, just flagging the
    # coincidence so it isn't misread as a typo.
    "DE_SOFTWARE": ["SAP.DE", "TMV.DE", "NEM.DE"],
    "FR_LUXURY": ["MC.PA", "RMS.PA", "KER.PA", "CDI.PA"],
    # Still capped near 3 -- France structurally lacks more banks of scale
    # even including mid-cap; adding smaller names here would mean crossing
    # into small-cap or non-bank financials, which breaks the driver logic.
    "FR_BANKS": ["BNP.PA", "GLE.PA", "ACA.PA"],
    # Mid-cap infra/energy distribution added alongside the two large utilities
    # (*) = mid-cap, verify before use
    "FR_UTILITIES": ["ENGI.PA", "VIE.PA", "RUI.PA", "ALO.PA"],
    "NL_SEMI_EQUIPMENT": ["ASML.AS", "ASMI.AS", "BESI.AS"],
    # Dutch banking is structurally limited to ING/ABN at scale; no mid-cap
    # domestic bank exists to add without leaving the subsector. Left as-is.
    "NL_BANKS": ["INGA.AS", "ABN.AS"],
   "ES_BANKS": ["SAN.MC", "BBVA.MC", "CABK.MC", "SAB.MC", "BKT.MC"],
    # Mid-cap renewables/grid names added alongside the large-cap 3
    # (*) = mid-cap, verify before use
    "ES_UTILITIES": ["IBE.MC", "NTGY.MC", "RED.MC", "SLR.MC", "ENC.MC"],
    # --- Canada (TSX, CAD) ---
    # "Big Six" Canadian banks -- same rate/credit-cycle exposure as
    # US_BANKS, but a separate BH family: distinct regulatory regime (OSFI
    # vs. US regulators) and a CAD-denominated basket, so pooling with
    # US_BANKS would violate the same-currency rule.
    "CA_BANKS": [
        "RY.TO",  # Royal Bank of Canada -- verify before use
        "TD.TO",  # TD Bank -- verify before use
        "BNS.TO",  # Bank of Nova Scotia -- verify before use
        "BMO.TO",  # Bank of Montreal -- verify before use
        "CM.TO",  # CIBC -- verify before use
        "NA.TO",  # National Bank of Canada -- verify before use
    ],
    # Integrated oil sands / E&P -- same commodity driver as US_OIL_GAS,
    # kept as its own CAD-denominated family for the same reason as above.
    "CA_ENERGY": [
        "SU.TO",  # Suncor Energy -- verify before use
        "CNQ.TO",  # Canadian Natural Resources -- verify before use
        "IMO.TO",  # Imperial Oil -- verify before use
        "CVE.TO",  # Cenovus Energy -- verify before use
    ],
    # --- Switzerland (SIX, CHF) ---
    # Large-cap pharma/life-sciences -- same R&D-pipeline/patent-cliff
    # driver. Basket is intentionally thin (3 names, 3 pairs): Switzerland
    # only has two global pharma giants at this scale, plus one adjacent
    # CDMO/life-sciences name -- widening further would mean leaving the
    # subsector, the same tradeoff already noted for FR_BANKS/NL_BANKS.
    "CH_PHARMA_LIFESCIENCE": [
        "NOVN.SW",  # Novartis -- verify before use
        "ROG.SW",  # Roche Holding -- verify before use
        "LONN.SW",  # Lonza Group -- verify before use
    ],
    # Banking/wealth management and insurance -- same rate-cycle exposure,
    # grouped together the same way DE_BANKS_INSURANCE already does.
    # Credit Suisse (formerly CSGN.SW) is deliberately absent -- it was
    # absorbed into UBS in 2023 and no longer trades as an independent
    # security.
    "CH_FINANCIALS": [
        "UBSG.SW",  # UBS Group -- verify before use
        "ZURN.SW",  # Zurich Insurance Group -- verify before use
        "SLHN.SW",  # Swiss Life Holding -- verify before use
        "BAER.SW",  # Julius Baer Group -- verify before use
    ],
}

# --- Data windows ---
# If True, and the pipeline is run mid-session (before today's daily bar
# is published), an extra row for today is appended using each ticker's
# latest live quote -- so the trading-window z-score reflects the current
# moment rather than lagging to the previous close. Never affects the
# estimation-window cointegration fit (see data_fetch.fetch_price_data).
INCLUDE_INTRADAY_LATEST_PRICE = True
# Estimation window: all statistical fitting (cointegration, hedge ratio,
# half-life) happens only on this data.
# Trading window: out-of-sample period used only for the rolling z-score
# and threshold flag.
ESTIMATION_MONTHS = 24  # 2 years
TRADING_MONTHS = 3  # 3 months
TRADING_DAYS_PER_MONTH = 21  # approximation used to convert months -> trading days

# --- Cointegration testing / multiple-testing correction ---
# Benjamini-Hochberg controls the False Discovery Rate (the expected
# proportion of false positives among declared discoveries), at this level.
FDR_LEVEL = 0.05

# --- Z-score window sizing (dynamic, per pair) ---
ZSCORE_HALF_LIFE_MULTIPLIER = (
    3  # rolling window = multiplier x half-life (trading days)
)
MIN_ZSCORE_WINDOW = 5  # floor, avoids degenerate tiny windows
# Upper cap is applied at runtime: window is never allowed to exceed the
# number of trading days in the trading window itself.

# --- Threshold flag (diagnostic only -- NOT an entry/exit signal) ---
Z_THRESHOLD = (
    2.5  # change to 3 / 3.5 / 4 etc. as needed, no other code changes required
)
# threshold_breached only fires if |z| > Z_THRESHOLD within the last
# RECENT_BREACH_WINDOW trading sessions -- i.e. "currently/recently
# diverging", not "diverged at any point in the whole trading window".
# Also reused by momentum.py as the lookback for its AR(1) sign-agreement
# and z-score turning check, so all "recent" framing in the tool stays on
# one knob.
RECENT_BREACH_WINDOW = 5

# --- Output ---
OUTPUT_DIR = "output"