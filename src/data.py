"""From the two DuckDB tables to one point-in-time frame per route.

    dataset("tokyo")  ->  one row per trade date of the destination market: the destination and
                          freight settles a trader could read at that day's New York close

Every print carries two stamps. trade_date is the day on the file; settle_utc is the instant it
became readable, the market's local close on that day converted to UTC, so that Singapore,
Amsterdam and London prints on one date sit on one clock. A row is anchored at asof_utc, the New
York close, and each leg joins with merge_asof backward on these instants: the latest settle
already printed, never one that came after the anchor. FX is charged a day late on top, and a leg
older than the tolerance drops the row rather than being carried on.
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


def fx():
    """EURUSD bars, each readable at the anchor of the day after its label."""
    df = sql.query("SELECT trade_date AS fx_trade_date, eurusd FROM fx ORDER BY trade_date")
    df["fx_available_utc"] = to_utc(df["fx_trade_date"] + pd.Timedelta(days=c.FX_LAG_DAYS), c.ASOF)
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

    # the cargo clock: loads on next month's program, sails mid-month, lands after the voyage
    df["loading_month"] = df["trade_date"] + pd.offsets.MonthBegin(1)
    arrival = df["loading_month"] + pd.Timedelta(days=c.LOAD_DAY - 1 + r["laden_days"])
    df["delivery_month"] = arrival.dt.to_period("M").dt.to_timestamp()

    # each leg is the latest settle of its contract printed by the anchor, never a later one
    dest = dest.add_prefix("dest_").sort_values("dest_settle_utc")
    df = pd.merge_asof(df, dest, left_on="asof_utc", right_on="dest_settle_utc",
                       left_by="delivery_month", right_by="dest_delivery_month",
                       direction="backward", tolerance=pd.Timedelta(c.TOLERANCE))
    freight = freight.add_prefix("freight_").sort_values("freight_settle_utc")
    df = pd.merge_asof(df, freight, left_on="asof_utc", right_on="freight_settle_utc",
                       left_by="loading_month", right_by="freight_delivery_month",
                       direction="backward", tolerance=pd.Timedelta(c.TOLERANCE))
    if r["price"] == "TTF":  # EUR/MWh: the row also needs the newest FX bar readable by the anchor
        df = pd.merge_asof(df, fx().sort_values("fx_available_utc"), left_on="asof_utc",
                           right_on="fx_available_utc", direction="backward",
                           tolerance=pd.Timedelta(c.TOLERANCE))

    df = df.dropna()  # a leg missing, or older than the tolerance, drops the row
    df = df.drop(columns=["loading_month", "delivery_month", "dest_delivery_month",
                          "freight_delivery_month"])
    oldest_leg = df.filter(like="_trade_date").min(axis=1)  # dest_, freight_ and fx_trade_date
    df["staleness_days"] = (df["trade_date"] - oldest_leg).dt.days
    return df.set_index("trade_date")
