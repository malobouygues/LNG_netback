"""Build data/lng.duckdb from the raw csv files, and read it back.

    python -m src.sql

Two tables. futures holds every contract's settles in the unit it is quoted in, JKM USD/MMBtu,
TTF EUR/MWh, BLNG2 and BLNG3 USD per charter day: one csv per contract, named product, month
code and year, so JKMH2025.csv is March 2025 JKM. fx holds the daily EURUSD bar. Both keep the
trade date on the file; when a print became readable is data.py's business.
"""

import duckdb

from src import config as c


def query(sql):
    with duckdb.connect(c.DB, read_only=True) as con:
        return con.sql(sql).df()


def build():
    c.DB.unlink(missing_ok=True)
    with duckdb.connect(c.DB) as con:
        # the contract is the file name; its last five characters are the month code and the year
        con.execute(f"""
            CREATE TABLE futures AS
            SELECT left(contract, length(contract) - 5) AS product, contract,
                   make_date(right(contract, 4)::INTEGER,
                             strpos('{c.MONTH_CODES}', contract[-5]), 1) AS delivery_month,
                   trade_date, settle
            FROM (SELECT parse_filename(filename, true) AS contract, trade_date, settle
                  FROM read_csv(['{c.DATA}/lng/*.csv', '{c.DATA}/freight/*.csv'],
                                header = false, filename = true,
                                columns = {{'trade_date': 'DATE', 'settle': 'DOUBLE'}}))
            ORDER BY 1, 3, 4""")
        con.execute(f"""
            CREATE TABLE fx AS
            SELECT trade_date, eurusd
            FROM read_csv('{c.DATA}/fx/eurusd_daily.csv', header = false,
                          columns = {{'trade_date': 'DATE', 'eurusd': 'DOUBLE'}})
            ORDER BY 1""")

        print(con.sql("SELECT product, COUNT(DISTINCT contract) AS contracts, MIN(trade_date), "
                      "MAX(trade_date), COUNT(*) FROM futures GROUP BY 1 ORDER BY 1"))
        print(con.sql("SELECT MIN(trade_date), MAX(trade_date), COUNT(*) FROM fx"))


if __name__ == "__main__":
    build()
