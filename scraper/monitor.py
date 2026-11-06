"""Competitor price monitor.

Fetches every shop from sources.json, parses product prices with per-shop CSS
selectors, appends today's snapshot to data/prices.json and sends a Telegram
alert when a competitor drops a price by more than the configured threshold.

Usage:
    python scraper/monitor.py                      # today
    python scraper/monitor.py --date 2026-10-01    # a past day (demo shops only)
    python scraper/monitor.py --backfill 30        # fill the last 30 days (demo)

Env:
    SHOP_BASE            base URL of the demo shops (default: deployed site)
    TELEGRAM_BOT_TOKEN   optional, enables alerts
    TELEGRAM_CHAT_ID     optional, enables alerts
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "scraper" / "sources.json"
DATA = ROOT / "data" / "prices.json"
DEFAULT_BASE = "https://price-monitor-demo.vercel.app"
HEADERS = {"User-Agent": "price-monitor-demo/1.0 (portfolio project)"}


# ---------- parsing ----------

def parse_price(text: str) -> float | None:
    """'1 149,99 zł' / '1149.99 PLN' / '429 99 zł' (sup) -> 1149.99"""
    if not text:
        return None
    cleaned = text.replace("\xa0", " ").strip()
    m = re.search(r"(\d[\d ]*)(?:[.,](\d{1,2}))?", cleaned)
    if not m:
        return None
    whole = m.group(1).replace(" ", "")
    frac = m.group(2) or "0"
    return round(float(f"{whole}.{frac}"), 2)


def parse_shop(page_html: str, shop: dict) -> list[dict]:
    soup = BeautifulSoup(page_html, "html.parser")
    items = []
    for node in soup.select(shop["item"]):
        sku_cfg = shop["sku"]
        sku = node.get(sku_cfg["attr"], "")
        if sku_cfg.get("strip_prefix") and sku.startswith(sku_cfg["strip_prefix"]):
            sku = sku[len(sku_cfg["strip_prefix"]):]

        name_el = node.select_one(shop["name_selector"])
        price_el = node.select_one(shop["price_selector"])
        if not sku or not price_el:
            continue

        # MediaPlus splits zloty and grosze: <strong>429</strong><sup>99</sup>
        if price_el.find("sup") is not None:
            whole = price_el.find("strong").get_text(strip=True)
            frac = price_el.find("sup").get_text(strip=True)
            price = parse_price(f"{whole},{frac}")
        else:
            price = parse_price(price_el.get_text(" ", strip=True))

        if "stock_attr" in shop:
            in_stock = node.get(shop["stock_attr"]) == "1"
        else:
            stock_el = node.select_one(shop["stock_selector"])
            in_stock = bool(stock_el) and stock_el.get_text(strip=True).lower() == shop["in_stock_text"].lower()

        items.append({
            "sku": sku,
            "name": name_el.get_text(strip=True) if name_el else sku,
            "price": price,
            "in_stock": in_stock,
        })
    return items


# ---------- storage ----------

def load_data(path: Path = DATA) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"shops": {}, "products": {}, "history": []}


def save_data(data: dict, path: Path = DATA) -> None:
    data["history"].sort(key=lambda s: s["date"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def upsert_snapshot(data: dict, date: str, prices: dict) -> None:
    """prices: {shop_id: {sku: {"price": float, "in_stock": bool}}}"""
    data["history"] = [s for s in data["history"] if s["date"] != date]
    data["history"].append({"date": date, "prices": prices})


def previous_snapshot(data: dict, date: str) -> dict | None:
    older = [s for s in data["history"] if s["date"] < date]
    return max(older, key=lambda s: s["date"]) if older else None


# ---------- alerts ----------

def find_drops(prev: dict | None, curr: dict, threshold: float) -> list[dict]:
    if not prev:
        return []
    drops = []
    for shop_id, items in curr.items():
        for sku, now in items.items():
            before = prev["prices"].get(shop_id, {}).get(sku)
            if not before or not before.get("price") or not now.get("price"):
                continue
            change = (now["price"] - before["price"]) / before["price"] * 100
            if change <= -threshold:
                drops.append({"shop": shop_id, "sku": sku, "old": before["price"],
                              "new": now["price"], "change": round(change, 1)})
    return sorted(drops, key=lambda d: d["change"])


def format_alert(drops: list[dict], data: dict, date: str) -> str:
    lines = [f"📉 <b>Competitors cut prices</b> ({date})", ""]
    for d in drops:
        shop = data["shops"].get(d["shop"], d["shop"])
        name = data["products"].get(d["sku"], d["sku"])
        lines.append(f"• <b>{html.escape(name)}</b> at {html.escape(shop)}: "
                     f"{d['old']:.2f} → <b>{d['new']:.2f} zł</b> ({d['change']}%)")
    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": text, "parse_mode": "HTML"}, timeout=20)
    r.raise_for_status()
    return True


# ---------- main ----------

def fetch(url: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return r.text
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def run_day(date: str, base: str, alert: bool = True) -> dict:
    cfg = json.loads(SOURCES.read_text(encoding="utf-8"))
    data = load_data()
    today = dt.date.today().isoformat()
    snapshot: dict = {}
    for shop in cfg["shops"]:
        url = shop["url"].format(base=base.rstrip("/"))
        if date != today:
            url += f"&date={date}"
        items = parse_shop(fetch(url), shop)
        data["shops"][shop["id"]] = shop["name"]
        snapshot[shop["id"]] = {}
        for it in items:
            data["products"][it["sku"]] = it["name"]
            snapshot[shop["id"]][it["sku"]] = {"price": it["price"], "in_stock": it["in_stock"]}

    drops = find_drops(previous_snapshot(data, date), snapshot, cfg["alert_drop_percent"])
    upsert_snapshot(data, date, snapshot)
    data["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    save_data(data)

    sent = False
    if alert and drops:
        sent = send_telegram(format_alert(drops, data, date))
    print(f"{date}: {sum(len(v) for v in snapshot.values())} prices, {len(drops)} drops"
          + (", alert sent" if sent else ""))
    return {"drops": drops, "sent": sent}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--backfill", type=int, help="fill the last N days (no alerts)")
    args = ap.parse_args(argv)
    base = os.getenv("SHOP_BASE", DEFAULT_BASE)

    if args.backfill:
        start = dt.date.today() - dt.timedelta(days=args.backfill)
        for i in range(args.backfill):
            run_day((start + dt.timedelta(days=i)).isoformat(), base, alert=False)
    run_day(args.date or dt.date.today().isoformat(), base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
