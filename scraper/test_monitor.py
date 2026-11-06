import json
from pathlib import Path

import pytest

import monitor as m

FIX = Path(__file__).parent / "fixtures"
CFG = json.loads((Path(__file__).parent / "sources.json").read_text(encoding="utf-8"))
SHOPS = {s["id"]: s for s in CFG["shops"]}


@pytest.mark.parametrize("text,expected", [
    ("1 149,99 zł", 1149.99),
    ("1149.99 PLN", 1149.99),
    ("429,99", 429.99),
    ("\xa0289,00\xa0zł", 289.0),
    ("399 zł", 399.0),
    ("brak", None),
    ("", None),
])
def test_parse_price(text, expected):
    assert m.parse_price(text) == expected


@pytest.mark.parametrize("shop_id", ["alfa", "voltix", "mediaplus"])
def test_each_shop_markup_is_parsed(shop_id):
    items = m.parse_shop((FIX / f"{shop_id}.html").read_text(encoding="utf-8"), SHOPS[shop_id])
    assert len(items) == 6
    skus = {i["sku"] for i in items}
    assert "ssd-1tb-nv" in skus and "mon-27-qhd" in skus
    for it in items:
        assert it["price"] and 100 < it["price"] < 2000
        assert isinstance(it["in_stock"], bool)
        assert it["name"]


def test_mediaplus_split_price_is_joined():
    page = '<ul><li class="offer" data-product-id="x" data-available="0"><a class="offer-name">X</a><p class="offer-price"><strong>1 024</strong><sup>49</sup> zł</p></li></ul>'
    [it] = m.parse_shop(page, SHOPS["mediaplus"])
    assert it["price"] == 1024.49 and it["in_stock"] is False


def test_voltix_prefix_stripped_and_out_of_stock():
    page = '<table class="offers"><tbody><tr id="sku-abc"><td class="name">A</td><td class="price">99.90 PLN</td><td class="avail">out of stock</td></tr></tbody></table>'
    [it] = m.parse_shop(page, SHOPS["voltix"])
    assert it["sku"] == "abc" and it["price"] == 99.9 and it["in_stock"] is False


def test_broken_item_is_skipped():
    page = '<main><div class="product-card" data-sku="ok"><h3 class="product-card__title">Ok</h3><div class="product-card__price"><span class="amount">10,00</span></div></div><div class="product-card"></div></main>'
    items = m.parse_shop(page, SHOPS["alfa"])
    assert [i["sku"] for i in items] == ["ok"]


def snap(date, price):
    return {"date": date, "prices": {"alfa": {"p1": {"price": price, "in_stock": True}}}}


def test_find_drops_threshold():
    prev = snap("2026-11-01", 100.0)
    assert m.find_drops(prev, {"alfa": {"p1": {"price": 96.0}}}, 5) == []
    [d] = m.find_drops(prev, {"alfa": {"p1": {"price": 90.0}}}, 5)
    assert d["change"] == -10.0 and d["old"] == 100.0 and d["new"] == 90.0


def test_price_rise_and_missing_are_ignored():
    prev = snap("2026-11-01", 100.0)
    assert m.find_drops(prev, {"alfa": {"p1": {"price": 120.0}, "p2": {"price": 5.0}}}, 5) == []
    assert m.find_drops(None, {"alfa": {"p1": {"price": 1.0}}}, 5) == []


def test_upsert_replaces_same_day_and_previous_lookup():
    data = {"shops": {}, "products": {}, "history": [snap("2026-11-01", 100.0)]}
    m.upsert_snapshot(data, "2026-11-02", {"alfa": {}})
    m.upsert_snapshot(data, "2026-11-02", {"alfa": {"p1": {"price": 1}}})
    assert [s["date"] for s in data["history"]] == ["2026-11-01", "2026-11-02"]
    assert m.previous_snapshot(data, "2026-11-02")["date"] == "2026-11-01"
    assert m.previous_snapshot(data, "2026-11-01") is None


def test_save_and_load_roundtrip(tmp_path):
    p = tmp_path / "prices.json"
    data = {"shops": {"alfa": "AlfaTech"}, "products": {}, "history": [snap("2026-11-02", 2.0), snap("2026-11-01", 1.0)]}
    m.save_data(data, p)
    loaded = m.load_data(p)
    assert [s["date"] for s in loaded["history"]] == ["2026-11-01", "2026-11-02"]
    assert m.load_data(tmp_path / "missing.json")["history"] == []


def test_alert_text_escapes_and_formats():
    data = {"shops": {"alfa": "Alfa<Tech>"}, "products": {"p1": "SSD & more"}}
    text = m.format_alert([{"shop": "alfa", "sku": "p1", "old": 100.0, "new": 88.0, "change": -12.0}], data, "2026-11-06")
    assert "Alfa&lt;Tech&gt;" in text and "SSD &amp; more" in text
    assert "100.00 → <b>88.00 zł</b> (-12.0%)" in text


def test_telegram_skipped_without_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert m.send_telegram("hi") is False


def test_telegram_sends_when_configured(monkeypatch):
    calls = []

    class R:
        def raise_for_status(self):
            pass

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setattr(m.requests, "post", lambda url, json, timeout: calls.append((url, json)) or R())
    assert m.send_telegram("hi") is True
    assert calls[0][0].endswith("/botT/sendMessage") and calls[0][1]["parse_mode"] == "HTML"
