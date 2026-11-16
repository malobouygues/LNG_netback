"""The economics of one cargo: what the voyage costs and what is left at the loading flange.

Every term is USD per loaded MMBtu, so the row subtracts exactly:

    netback = dest_price - boiloff - freight - canal - port - working_capital - insurance

JKM and NWE are both DES prices, LNG delivered at the terminal, so no regas is subtracted. The
netback is what the cargo is worth FOB US Gulf. Its cost there, about 115% of Henry Hub plus a
liquefaction fee, is the same whichever way the ship sails: it cancels in the arb and is left out.
"""

import pandas as pd

from src import config as c


def netback(route, df, **changes):
    """The cost stack and the netback, one row per trade date of the aligned dataset. Any
    assumption can be changed by name for a sensitivity, as in
    netback("tokyo_cape", df, laden_days=40)."""
    p = {"cargo_mmbtu": c.CARGO_MMBTU, "boil_off_per_day": c.BOIL_OFF_PER_DAY,
         "port_days": c.PORT_DAYS, "port_cost_usd": c.PORT_COST_USD,
         "funding_rate": c.FUNDING_RATE, "insurance_rate": c.INSURANCE_RATE,
         **c.ROUTES[route], **changes}
    # boil-off compounds on what is left of the cargo
    delivered = (1 - p["boil_off_per_day"]) ** p["laden_days"]
    # laden out, ballast home, and the days in port
    days_on_hire = p["laden_days"] * c.ROUND_TRIP + p["port_days"]

    out = pd.DataFrame(index=df.index)
    out["dest_price"] = df["dest_settle"]  # JKM and NWM both quote USD/MMBtu
    out["boiloff"] = out["dest_price"] * (1 - delivered)  # lost energy, valued at the destination
    # USD per day into USD per loaded MMBtu
    out["freight"] = df["freight_settle"] * days_on_hire / p["cargo_mmbtu"]
    out["canal"] = p["canal_usd"] / p["cargo_mmbtu"]
    out["port"] = p["port_cost_usd"] / p["cargo_mmbtu"]
    # the cargo is paid for at loading and sold at delivery: it is financed while it sails
    out["working_capital"] = out["dest_price"] * p["funding_rate"] * p["laden_days"] / 365
    out["insurance"] = out["dest_price"] * p["insurance_rate"]
    out["netback"] = (out["dest_price"] - out["boiloff"] - out["freight"] - out["canal"]
                      - out["port"] - out["working_capital"] - out["insurance"])
    return out
