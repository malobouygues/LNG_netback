"""Paths, the contract naming convention, when each market's print becomes readable, and every
physical and financial assumption behind the voyage, each with its unit and its source."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB = DATA / "lng.duckdb"

MONTH_CODES = "FGHJKMNQUVXZ"  # futures month codes, January to December: JKMH2025 is March 2025

# --- when a price becomes readable --------------------------------------------
# Each market settles on its own wall clock, so a settle is readable from the local close on its
# trade date. Singapore has no DST, London does: every stamp goes through UTC.
CLOSE = {"JKM": ("Asia/Singapore", "16:30:00"),   # Platts JKM window
         "NWM": ("Europe/London", "16:30:00"),    # Platts NWE window
         "BLNG2": ("Europe/London", "16:00:00"),  # Baltic publication
         "BLNG3": ("Europe/London", "16:00:00")}

# The cargo is sold FOB US Gulf, so a row for trade date D is anchored at the New York close, after
# Singapore and London have printed: every price on the row has to be older than it.
ASOF = ("America/New_York", "17:00:00")

# Past this a settle is stale rather than late: the row is dropped instead of carrying it on.
TOLERANCE = "5D"

# The cargo month M is the first whose Platts window has not opened yet. JKM and NWM settle on the
# average of the assessments from the 16th of M-2 to the 15th of M-1: inside that window part of
# the price is already fixed and lags the market. So a trade up to the 15th takes M+2, from the
# 16th M+3. Loading mid-month, Europe lands within M and Tokyo in M+1, by either canal.
ROLL_DAY = 16

# --- the ship -----------------------------------------------------------------
# The Baltic's standard LNGC174, the ship BLNG2 and BLNG3 price: 2-stroke, 174,000 m3, boil-off
# 0.085% a day (Baltic circular 35/23). Platts' June 2026 guide uses 0.12% laden, a fleet average.
CARGO_MMBTU = 3_500_000      # what the 174,000 m3 sells after heel and tank margins
BOIL_OFF_PER_DAY = 0.00085   # fraction of the remaining cargo, per laden day
ROUND_TRIP = 2               # Baltic BLNG rates are round-trip: the cargo pays the ballast leg home
PORT_DAYS = 3                # 1.5 days loading, 1.5 discharging (Platts LNG guide, June 2026)
PORT_COST_USD = 200_000      # port, agency and tug fees at both ends

# --- the money ----------------------------------------------------------------
FUNDING_RATE = 0.05      # Glencore's "current marketing funding cost of c.5%", 2 Oct 2026
INSURANCE_RATE = 0.0009  # 2025 cargo premiums over goods trade: 24.2bn (IUMI) / 26,260bn (WTO)

# --- the routes ---------------------------------------------------------------
# Panama tolls for a 174,000 m3 LNG carrier, ACP tariff since 1 Jan 2025: USD 300,000 per transit
# plus USD 2.05 per m3 laden, the ballast transit home at 85% of it.
PANAMA_USD = 1.85 * (300_000 + 2.05 * 174_000)  # about USD 1.21 million a round trip

# Both markers are DES LNG in USD/MMBtu, so neither route pays regas or FX. The FOB cost of the
# cargo, Henry Hub plus liquefaction, is the same on each route and cancels in the arb: left out.
# delivery_lag is the months from the loading month to the delivery month.
ROUTES = {
    "tokyo_panama": {"price": "JKM", "freight": "BLNG3", "delivery_lag": 1,
                     "laden_days": 25, "canal_usd": PANAMA_USD},  # 25 x 2 + 3 = BLNG3's 53-day RV
    "tokyo_cape": {"price": "JKM", "freight": "BLNG3", "delivery_lag": 1,
                   "laden_days": 45, "canal_usd": 0},  # 9 cargoes in 10 went this way in 2025-26
    "rotterdam": {"price": "NWM", "freight": "BLNG2", "delivery_lag": 0,
                  "laden_days": 15, "canal_usd": 0},  # BLNG2's own 28-day RV implies 12.5
}
