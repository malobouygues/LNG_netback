"""Fetch the raw csv files into data/ from TradingView, one per contract. Needs tvDatafeed;
nothing else does, and the csv files are committed, so the repo never has to run this.

    python -m src.download
"""

import pandas as pd
from tvDatafeed import Interval, TvDatafeed

from src import config as c

# product -> TradingView symbol root, exchange, folder under data/
FEEDS = {"JKM": ("JKM", "NYMEX", "lng"), "TTF": ("TFM", "ICEENDEX", "lng"),
         "BLNG2": ("BG2", "NYMEX", "freight"), "BLNG3": ("BG3", "NYMEX", "freight")}
MONTHS_BACK = 12  # the next loading program and the eleven before it
BARS = 40         # settles per contract, the two months or so it trades


def save(bars, path):
    pd.DataFrame({"date": bars.index.strftime("%Y-%m-%d"), "value": bars["close"].to_numpy()}
                 ).to_csv(path, index=False, header=False)


def main():
    tv = TvDatafeed()
    front = pd.Timestamp.now().to_period("M") + 1
    for product, (symbol, exchange, folder) in FEEDS.items():
        for back in range(MONTHS_BACK):
            month = front - back
            code = f"{c.MONTH_CODES[month.month - 1]}{month.year}"
            bars = tv.get_hist(symbol=symbol + code, exchange=exchange, interval=Interval.in_daily,
                               n_bars=BARS)
            if bars is None or bars.empty:  # never the continuous series: one file, one contract
                print(f"{product}{code}: nothing returned, skipped")
                continue
            save(bars, c.DATA / folder / f"{product}{code}.csv")
            print(f"{product}{code}: {len(bars)} rows")
    fx = tv.get_hist(symbol="EURUSD", exchange="FX_IDC", interval=Interval.in_daily, n_bars=265)
    save(fx, c.DATA / "fx" / "eurusd_daily.csv")
    print(f"eurusd_daily: {len(fx)} rows")


if __name__ == "__main__":
    main()
