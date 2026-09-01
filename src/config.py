"""Paths, market conventions and every physical assumption, each with its unit."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LNG_DIR = ROOT / "data" / "lng"
FREIGHT_DIR = ROOT / "data" / "freight"
FX_DIR = ROOT / "data" / "fx"
DB_PATH = ROOT / "data" / "lng.duckdb"
SQL_DIR = ROOT / "sql"

MONTH_CODES = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
               "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}
CODE_BY_MONTH = {number: code for code, number in MONTH_CODES.items()}

# product -> (timezone, time of day the settle is published on the trade date)
SETTLE_ANCHORS = {
    "JKM": ("Asia/Singapore", pd.Timedelta(hours=16, minutes=30)),  # Platts window, no DST
    "TTF": ("Europe/Amsterdam", pd.Timedelta(hours=17)),
    "BLNG2": ("Europe/London", pd.Timedelta(hours=16)),  # Baltic publication
    "BLNG3": ("Europe/London", pd.Timedelta(hours=16)),
}

# The vendor does not document whether a daily FX bar is stamped at the session open or its
# close, so a bar labelled D is charged as usable only at D+1 17:00 New York.
FX_AVAILABLE = ("America/New_York", pd.Timedelta(days=1, hours=17))

# A panel row is anchored at the New York close, the last of the four market closes. Every
# price on the row has to have printed before it.
ASOF = ("America/New_York", pd.Timedelta(hours=17))
TOLERANCE = pd.Timedelta(days=5)  # how long a settle may be carried, about 3 business days

MMBTU_PER_MWH = 3.412142  # TTF quotes EUR/MWh; JKM and the netback are USD/MMBtu
LOAD_DAY = 15  # mid-month sailing, so the delivery month holds for a whole trade month

CARGO_MMBTU = 3_500_000.0  # 174,000 m3 two-stroke, what it sells after heel and tank margins
BOIL_OFF_PER_DAY = 0.0015  # fraction of the remaining cargo, per laden day
ROUND_TRIP = 2.0  # Baltic BLNG rates are round-trip: the cargo pays the ballast leg home
PORT_DAYS = 2.0  # load plus discharge, on hire
PORT_COST_USD = 200_000.0  # port, agency and tug fees at both ends

# route -> destination product, freight product, laden days, canal USD round trip, regas USD/MMBtu
ROUTES = {
    "us_gulf_to_tokyo": ("JKM", "BLNG3", 20, 1_000_000.0, 0.0),
    "us_gulf_to_rotterdam": ("TTF", "BLNG2", 10, 0.0, 0.50),
}
