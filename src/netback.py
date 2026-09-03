"""The economics of one cargo: what the voyage costs and what is left at the loading flange.

Every term is USD per loaded MMBtu, so the row subtracts exactly:

    netback = dest_price - boiloff - regas - freight - canal - port
"""

import pandas as pd

from src import config as c


def netback(route, df):
    """The cost stack and the netback, one row per trade date of the aligned dataset."""
    r = c.ROUTES[route]
    delivered = (1 - c.BOIL_OFF_PER_DAY) ** r["laden_days"]  # boil-off compounds on the remainder
    out = pd.DataFrame(index=df.index)
    out["dest_price"] = (df["dest_settle"] * df["eurusd"] / c.MMBTU_PER_MWH if r["price"] == "TTF"
                         else df["dest_settle"])  # EUR/MWh into USD/MMBtu; JKM already is
    out["boiloff"] = out["dest_price"] * (1 - delivered)
    out["regas"] = r["regas_usd_mmbtu"] * delivered  # a terminal fee, paid on what arrives
    out["freight"] = (df["freight_settle"] * (r["laden_days"] * c.ROUND_TRIP + c.PORT_DAYS)
                      / c.CARGO_MMBTU)
    out["canal"] = r["canal_usd"] / c.CARGO_MMBTU
    out["port"] = c.PORT_COST_USD / c.CARGO_MMBTU
    out["netback"] = (out["dest_price"] - out["boiloff"] - out["regas"] - out["freight"]
                      - out["canal"] - out["port"])
    return out
