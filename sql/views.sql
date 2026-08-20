-- Both netbacks and the arb on one row per trade date, USD/MMBtu FOB US Gulf.
-- arb_usd_mmbtu is null on dates only one route covers, which is what keeps a
-- comparison from being drawn across two different samples.
CREATE OR REPLACE VIEW v_netback_arb AS
WITH wide AS (
    SELECT
        trade_date,
        MAX(netback_usd_mmbtu) FILTER (WHERE route = 'us_gulf_to_tokyo')     AS netback_tokyo,
        MAX(netback_usd_mmbtu) FILTER (WHERE route = 'us_gulf_to_rotterdam') AS netback_rotterdam
    FROM netback_panel
    GROUP BY trade_date
)
SELECT
    trade_date,
    netback_tokyo,
    netback_rotterdam,
    netback_tokyo - netback_rotterdam AS arb_usd_mmbtu
FROM wide;
