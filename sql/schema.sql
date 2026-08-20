-- Prices in USD/MMBtu except TTF settles, which are EUR/MWh as quoted.
CREATE TABLE lng_futures_daily (
    product              VARCHAR      NOT NULL,
    contract             VARCHAR      NOT NULL,
    delivery_month       DATE         NOT NULL,
    trade_date           DATE         NOT NULL,
    settle_timestamp_utc TIMESTAMPTZ  NOT NULL,
    settle               DOUBLE       NOT NULL,
    PRIMARY KEY (contract, trade_date)
);

-- Baltic round-trip time charter equivalent, USD per charter day. Can print negative.
CREATE TABLE freight_futures_daily (
    product              VARCHAR      NOT NULL,
    contract             VARCHAR      NOT NULL,
    delivery_month       DATE         NOT NULL,
    trade_date           DATE         NOT NULL,
    settle_timestamp_utc TIMESTAMPTZ  NOT NULL,
    settle               DOUBLE       NOT NULL,
    PRIMARY KEY (contract, trade_date)
);

-- USD per EUR. available_timestamp_utc is the worst-case availability, not the print time.
CREATE TABLE fx_daily (
    trade_date              DATE         NOT NULL,
    available_timestamp_utc TIMESTAMPTZ  NOT NULL,
    eurusd                  DOUBLE       NOT NULL,
    PRIMARY KEY (trade_date)
);

-- Every column USD per loaded MMBtu, except the freight rate (USD/day) and the FX rate.
-- eurusd is null on the Tokyo route, which is quoted in USD and needs no conversion.
CREATE TABLE netback_panel (
    trade_date             DATE         NOT NULL,
    asof_timestamp_utc     TIMESTAMPTZ  NOT NULL,
    route                  VARCHAR      NOT NULL,
    dest_contract          VARCHAR      NOT NULL,
    freight_contract       VARCHAR      NOT NULL,
    dest_price_usd_mmbtu   DOUBLE       NOT NULL,
    eurusd                 DOUBLE,
    freight_rate_usd_day   DOUBLE       NOT NULL,
    freight_cost_usd_mmbtu DOUBLE       NOT NULL,
    boiloff_cost_usd_mmbtu DOUBLE       NOT NULL,
    canal_cost_usd_mmbtu   DOUBLE       NOT NULL,
    port_cost_usd_mmbtu    DOUBLE       NOT NULL,
    regas_cost_usd_mmbtu   DOUBLE       NOT NULL,
    max_staleness_days     INTEGER      NOT NULL,
    netback_usd_mmbtu      DOUBLE       NOT NULL,
    PRIMARY KEY (route, trade_date)
);
