"""The economics of one cargo: what the voyage costs and what is left at the loading flange.

Every term is USD per loaded MMBtu, so the row subtracts exactly:

    netback = dest_price - boiloff - freight - canal - port - working_capital - insurance

JKM and NWE are both DES prices, LNG delivered at the terminal, so no regas is subtracted. The
netback is what the cargo is worth FOB US Gulf. Its cost there, about 115% of Henry Hub plus a
liquefaction fee, is the same whichever way the ship sails: it cancels in the arb and is left out.
"""

import pandas as pd

from src import config as c


def netback(route, df):
    """The cost stack and the netback, one row per trade date of the aligned dataset."""
    r = c.ROUTES[route]
    delivered = (1 - c.BOIL_OFF_PER_DAY) ** r["laden_days"]  # boil-off compounds on the remainder
    days_on_hire = r["laden_days"] * c.ROUND_TRIP + c.PORT_DAYS  # laden out, ballast home, ports

    out = pd.DataFrame(index=df.index)
    out["dest_price"] = df["dest_settle"]  # JKM and NWM both quote USD/MMBtu
    out["boiloff"] = out["dest_price"] * (1 - delivered)  # lost energy, valued at the destination
    out["freight"] = df["freight_settle"] * days_on_hire / c.CARGO_MMBTU  # USD/day into USD/MMBtu
    out["canal"] = r["canal_usd"] / c.CARGO_MMBTU
    out["port"] = c.PORT_COST_USD / c.CARGO_MMBTU
    # the cargo is paid for at loading and sold at delivery: it is financed while it sails
    out["working_capital"] = out["dest_price"] * c.FUNDING_RATE * r["laden_days"] / 365
    out["insurance"] = out["dest_price"] * c.INSURANCE_RATE
    out["netback"] = (out["dest_price"] - out["boiloff"] - out["freight"] - out["canal"]
                      - out["port"] - out["working_capital"] - out["insurance"])
    return out
