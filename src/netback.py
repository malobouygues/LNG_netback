"""The economics: what the voyage costs, what it leaves at the flange, and the arb.

Every component is USD per loaded MMBtu, so the row subtracts exactly:

    netback = dest_price - boiloff - regas - freight - canal - port
"""

from __future__ import annotations

import pandas as pd

from config import (
    BOIL_OFF_PER_DAY,
    CARGO_MMBTU,
    MMBTU_PER_MWH,
    PORT_COST_USD,
    PORT_DAYS,
    ROUND_TRIP,
)


def price(name: str, spec, aligned: pd.DataFrame) -> pd.DataFrame:
    """One route's panel rows, from the aligned prices to the netback they leave."""
    dest_product, _freight_product, laden_days, canal_usd, regas_usd = spec

    delivered = (1 - BOIL_OFF_PER_DAY) ** laden_days  # boil-off eats the remainder, so it compounds
    dest_price = (
        aligned["dest_settle"] * aligned["eurusd"] / MMBTU_PER_MWH
        if dest_product == "TTF"
        else aligned["dest_settle"]
    )

    panel = pd.DataFrame(
        {
            "trade_date": aligned["trade_date"],
            "asof_timestamp_utc": aligned["asof_timestamp_utc"],
            "route": name,
            "dest_contract": aligned["dest_contract"],
            "freight_contract": aligned["freight_contract"],
            "dest_price_usd_mmbtu": dest_price,
            "eurusd": aligned["eurusd"],
            "freight_rate_usd_day": aligned["freight_settle"],
            "freight_cost_usd_mmbtu": aligned["freight_settle"]
            * (laden_days * ROUND_TRIP + PORT_DAYS)
            / CARGO_MMBTU,
            "boiloff_cost_usd_mmbtu": dest_price * (1 - delivered),
            "canal_cost_usd_mmbtu": canal_usd / CARGO_MMBTU,
            "port_cost_usd_mmbtu": PORT_COST_USD / CARGO_MMBTU,
            "regas_cost_usd_mmbtu": regas_usd * delivered,  # a terminal fee is paid on what arrives
            "max_staleness_days": aligned["max_staleness_days"],
        }
    )
    costs = [c for c in panel if c.endswith("_cost_usd_mmbtu")]
    panel["netback_usd_mmbtu"] = panel["dest_price_usd_mmbtu"] - panel[costs].sum(axis=1)
    return panel


def arb(panel: pd.DataFrame) -> pd.DataFrame:
    """Both netbacks and the spread, one row per trade date. The spread is blank where
    only one route has a price, which stops the two samples being compared."""
    wide = panel.pivot(index="trade_date", columns="route", values="netback_usd_mmbtu")
    wide["arb_usd_mmbtu"] = wide["us_gulf_to_tokyo"] - wide["us_gulf_to_rotterdam"]
    return wide.rename(
        columns={"us_gulf_to_tokyo": "netback_tokyo", "us_gulf_to_rotterdam": "netback_rotterdam"}
    ).reset_index()
