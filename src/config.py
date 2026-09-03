"""Paths, the contract naming convention, when each market's print becomes readable, and every
physical assumption behind the voyage, each with its unit."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB = DATA / "lng.duckdb"

MONTH_CODES = "FGHJKMNQUVXZ"  # futures month codes, January to December: JKMH2025 is March 2025

# --- when a price becomes readable --------------------------------------------
# Each market settles on its own wall clock, so a settle is readable from the local close on its
# trade date. Singapore has no DST, Amsterdam and London do: every stamp goes through UTC.
CLOSE = {"JKM": ("Asia/Singapore", "16:30:00"),   # Platts assessment window
         "TTF": ("Europe/Amsterdam", "17:00:00"),
         "BLNG2": ("Europe/London", "16:00:00"),  # Baltic publication
         "BLNG3": ("Europe/London", "16:00:00")}

# A row for trade date D is anchored at the New York close, the last of the four: every price on
# the row has to have printed before it.
ASOF = ("America/New_York", "17:00:00")

# The vendor does not say whether a daily FX bar is stamped at the session open or its close, so
# a bar labelled D is charged as readable only at the anchor of D+1.
FX_LAG_DAYS = 1

# Past this a settle is stale rather than late: the row is dropped instead of carrying it on.
TOLERANCE = "5D"

# --- the cargo ----------------------------------------------------------------
CARGO_MMBTU = 3_500_000    # 174,000 m3 two-stroke ship, what it sells after heel and tank margins
LOAD_DAY = 15              # sails mid-month, so one delivery month holds for a whole trade month
BOIL_OFF_PER_DAY = 0.0015  # fraction of the remaining cargo, per laden day
ROUND_TRIP = 2             # Baltic BLNG rates are round-trip: the cargo pays the ballast leg home
PORT_DAYS = 2              # load plus discharge, on hire
PORT_COST_USD = 200_000    # port, agency and tug fees at both ends
MMBTU_PER_MWH = 3.412142   # TTF quotes EUR/MWh; JKM and the netback are USD/MMBtu

# Both routes load in the US Gulf. Freight is the loading-month BLNG contract, fixed when the
# ship is; the destination is the delivery-month JKM or TTF, what the cargo sells against.
ROUTES = {
    "tokyo": {"price": "JKM", "freight": "BLNG3", "laden_days": 20,  # via Panama
              "canal_usd": 1_000_000, "regas_usd_mmbtu": 0.0},
    "rotterdam": {"price": "TTF", "freight": "BLNG2", "laden_days": 10,
                  "canal_usd": 0, "regas_usd_mmbtu": 0.50},
}
