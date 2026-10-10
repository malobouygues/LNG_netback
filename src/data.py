"""From the DuckDB futures table to one point-in-time frame per route.

    dataset("tokyo_cape")  ->  one row per trade date of the destination market: the destination
                               and freight settles a trader could read at that day's New York close

Every print carries two stamps. trade_date is the day on the file; settle_utc is the instant it
became readable, the market's local close on that day converted to UTC, so that Singapore and
London prints on one date sit on one clock. A row is anchored at asof_utc, the New York close, and
each leg joins with merge_asof backward on these instants: the latest settle already printed,
never one that came after the anchor. A leg older than the tolerance drops the row rather than
being carried on.
"""

import pandas as pd

from src import config as c, sql


def to_utc(dates, market):
    """The local wall-clock time of a market on each date, as a UTC instant."""
    tz, time = market
    return (dates + pd.Timedelta(time)).dt.tz_localize(tz).dt.tz_convert("UTC")


def futures(product):
    """One product's settles, every contract, stamped with the instant each became readable."""
    df = sql.query(f"SELECT contract, delivery_month, trade_date, settle FROM futures "
                   f"WHERE product = '{product}' ORDER BY delivery_month, trade_date")
    df["settle_utc"] = to_utc(df["trade_date"], c.CLOSE[product])
    return df


def dataset(route):
    """The two legs of one route on each trade date of its destination market, as of the New
    York close: the delivery-month destination contract and the loading-month freight."""
    r = c.ROUTES[route]
    dest = futures(r["price"])
    freight = futures(r["freight"])

    df = dest[["trade_date"]].drop_duplicates()
    df = df.sort_values("trade_date", ignore_index=True)
    df["asof_utc"] = to_utc(df["trade_date"], c.ASOF)

    # the cargo month: two months out up to the 15th, three from the 16th, before any Platts window
    month = (df["trade_date"] - pd.Timedelta(days=c.ROLL_DAY - 1)).dt.to_period("M") + 3
    df["loading_month"] = month.dt.to_timestamp()
    df["delivery_month"] = (month + r["delivery_lag"]).dt.to_timestamp()

    # each leg is the latest settle of its contract printed by the anchor, never a later one
    dest = dest.add_prefix("dest_").sort_values("dest_settle_utc")
    df = pd.merge_asof(df, dest, left_on="asof_utc", right_on="dest_settle_utc",
                       left_by="delivery_month", right_by="dest_delivery_month",
                       direction="backward", tolerance=pd.Timedelta(c.TOLERANCE))
    freight = freight.add_prefix("freight_").sort_values("freight_settle_utc")
    df = pd.merge_asof(df, freight, left_on="asof_utc", right_on="freight_settle_utc",
                       left_by="loading_month", right_by="freight_delivery_month",
                       direction="backward", tolerance=pd.Timedelta(c.TOLERANCE))

    df = df.dropna()  # a leg missing, or older than the tolerance, drops the row
    df = df.drop(columns=["dest_delivery_month", "freight_delivery_month"])
    oldest_leg = df[["dest_trade_date", "freight_trade_date"]].min(axis=1)
    df["staleness_days"] = (df["trade_date"] - oldest_leg).dt.days
    return df.set_index("trade_date")
