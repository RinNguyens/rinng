from rinng.news.feed import parse_binance, parse_okx, parse_rss
from rinng.news.score import coins_in, outlook, score_headline


def test_hack_is_bearish_high_impact():
    s = score_headline("DeFi protocol drained of $40M in exploit")
    assert s.sentiment == "bearish" and s.impact == 3 and "hack" in s.tags


def test_listing_is_bullish_and_names_coin():
    s = score_headline("OKX will launch AERO/USDC for spot trading", "exchange")
    assert s.sentiment == "bullish" and s.impact == 3 and "AERO" in s.coins


def test_delisting_bearish():
    assert score_headline("Binance Will Delist ABC, DEF on 2026-11-20", "exchange").score < 0


def test_macro_raises_impact_without_direction():
    s = score_headline("Powell speaks at Jackson Hole today")
    assert s.impact == 3 and s.sentiment == "neutral"


def test_coin_names_and_tickers():
    assert coins_in("Bitcoin ETF sees inflows as $SOL and ETHUSDT rally") == ["SOL", "ETH", "BTC"]


def test_outlook_decays_and_filters_by_coin():
    now = 100 * 3_600_000
    items = [
        {"time": now, "score": 0.8, "impact": 3, "coins": ["BTC"]},
        {"time": now - 20 * 3_600_000, "score": -0.8, "impact": 3, "coins": ["BTC"]},
        {"time": now, "score": -0.9, "impact": 3, "coins": ["ETH"]},
        {"time": now - 30 * 3_600_000, "score": -1.0, "impact": 3, "coins": ["BTC"]},
    ]
    o = outlook(items, now, "BTC")
    assert o["count"] == 2 and o["label"] == "bullish"
    assert outlook([], now)["label"] == "neutral"


def test_parsers():
    rss = """<rss><channel><item><title>Bitcoin surges</title><link>https://x/1</link>
    <pubDate>Sat, 14 Nov 2026 10:00:00 +0000</pubDate></item></channel></rss>"""
    [r] = parse_rss("T", rss)
    assert r["coins"] == ["BTC"] and r["sentiment"] == "bullish" and r["time"] > 0
    okx = {"data": [{"details": [{"title": "OKX to delist XYZ", "url": "u", "pTime": "1"}]}]}
    assert parse_okx(okx)[0]["sentiment"] == "bearish"
    bn = {
        "data": {
            "catalogs": [
                {
                    "articles": [
                        {"code": "c", "title": "Binance Will List FOO (FOO)", "releaseDate": 2}
                    ]
                }
            ]
        }
    }
    b = parse_binance(bn)[0]
    assert b["coins"] == ["FOO"] and b["url"].endswith("/c")


def test_multi_week_low_outweighs_rally_word():
    s = score_headline("Bitcoin Hits 12-Week Low as Fed Rate Fears Undo Most of Summer Rally")
    assert s.sentiment == "bearish"
