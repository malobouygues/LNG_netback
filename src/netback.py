"""The economics of one cargo: what the voyage costs and what is left at the loading flange.

Every term is USD per loaded MMBtu, so the row subtracts exactly:

    netback = dest_price - boiloff - regas - freight - canal - port

The netback is what the cargo is worth FOB US Gulf. Its cost there, about 115% of Henry Hub plus
a liquefaction fee, is the same whichever way the ship sails: it cancels in the arb
netback_tokyo - netback_rotterdam and is left out.
"""

import pandas as pd

from src import config as c


def netback(route, df):
    """The cost stack and the netback, one row per trade date of the aligned dataset."""
    r = c.ROUTES[route]
    delivered = (1 - c.BOIL_OFF_PER_DAY) ** r["laden_days"]  # boil-off compounds on the remainder
    days_on_hire = r["laden_days"] * c.ROUND_TRIP + c.PORT_DAYS  # laden out, ballast home, ports

    out = pd.DataFrame(index=df.index)
    if r["price"] == "TTF":  # EUR/MWh into USD/MMBtu, at the FX bar on the row
        out["dest_price"] = df["dest_settle"] * df["eurusd"] / c.MMBTU_PER_MWH
    else:  # JKM already is USD/MMBtu
        out["dest_price"] = df["dest_settle"]
    out["boiloff"] = out["dest_price"] * (1 - delivered)  # lost energy, valued at the destination
    out["regas"] = r["regas_usd_mmbtu"] * delivered  # a terminal fee, paid on what arrives
    out["freight"] = df["freight_settle"] * days_on_hire / c.CARGO_MMBTU  # USD/day into USD/MMBtu
    out["canal"] = r["canal_usd"] / c.CARGO_MMBTU
    out["port"] = c.PORT_COST_USD / c.CARGO_MMBTU
    out["netback"] = (out["dest_price"] - out["boiloff"] - out["regas"] - out["freight"]
                      - out["canal"] - out["port"])
    return out
