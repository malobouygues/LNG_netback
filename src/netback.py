"""The economics: what the voyage costs, what it leaves at the flange, and the arb.

Every component is USD per loaded MMBtu, so the row subtracts exactly:

    netback = dest_price - boiloff - regas - freight - canal - port
"""

import pandas as pd

from src import config as c


def price(name, spec, aligned):
    """One route's panel rows, from the aligned prices to the netback they leave."""
    dest_product, freight_product, laden_days, canal_usd, regas_usd = spec
    delivered = (1 - c.BOIL_OFF_PER_DAY) ** laden_days  # boil-off eats the remainder, so it compounds
    dest_price = (aligned["dest_settle"] * aligned["eurusd"] / c.MMBTU_PER_MWH
                  if dest_product == "TTF" else aligned["dest_settle"])

    panel = pd.DataFrame({
        "trade_date": aligned["trade_date"],
        "asof_timestamp_utc": aligned["asof_timestamp_utc"],
        "route": name,
        "dest_contract": aligned["dest_contract"],
        "freight_contract": aligned["freight_contract"],
        "dest_price_usd_mmbtu": dest_price,
        "eurusd": aligned["eurusd"],
        "freight_rate_usd_day": aligned["freight_settle"],
        "freight_cost_usd_mmbtu": (aligned["freight_settle"]
                                   * (laden_days * c.ROUND_TRIP + c.PORT_DAYS) / c.CARGO_MMBTU),
        "boiloff_cost_usd_mmbtu": dest_price * (1 - delivered),
        "canal_cost_usd_mmbtu": canal_usd / c.CARGO_MMBTU,
        "port_cost_usd_mmbtu": c.PORT_COST_USD / c.CARGO_MMBTU,
        "regas_cost_usd_mmbtu": regas_usd * delivered,  # a terminal fee is paid on what arrives
        "max_staleness_days": aligned["max_staleness_days"],
    })
    costs = [col for col in panel if col.endswith("_cost_usd_mmbtu")]
    panel["netback_usd_mmbtu"] = panel["dest_price_usd_mmbtu"] - panel[costs].sum(axis=1)
    return panel


def arb(panel):
    """Both netbacks and the spread, one row per trade date. The spread is blank where only
    one route has a price, which stops the two samples being compared."""
    wide = panel.pivot(index="trade_date", columns="route", values="netback_usd_mmbtu")
    wide["arb_usd_mmbtu"] = wide["us_gulf_to_tokyo"] - wide["us_gulf_to_rotterdam"]
    return wide.rename(columns={"us_gulf_to_tokyo": "netback_tokyo",
                                "us_gulf_to_rotterdam": "netback_rotterdam"}).reset_index()
