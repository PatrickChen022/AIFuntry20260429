from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

COMMUNITY_ID = 5886292
PAGE_SIZE = 20
BASE_URL = "https://bff-market.591.com.tw/v1/price/list"
OUT_DIR = Path("591_export")
SOURCE_URL = "https://market.591.com.tw/5886292/price?guide=1&trans_type=2"


def fetch_page(session: requests.Session, page: int) -> dict:
    params = {
        "community_id": COMMUNITY_ID,
        "split_park": 1,
        "page": page,
        "page_size": PAGE_SIZE,
        "_source": 0,
    }
    last_error = None
    for attempt in range(1, 6):
        try:
            response = session.get(BASE_URL, params=params, timeout=60)
            print(f"page={page} attempt={attempt} status={response.status_code} bytes={len(response.content)}")
            if response.status_code == 200:
                return response.json()
            print(response.text[:300])
            response.raise_for_status()
        except Exception as exc:
            last_error = exc
            if attempt < 5:
                time.sleep(attempt * 2)
    raise RuntimeError(f"Failed to fetch page {page}: {last_error}")


def pick(mapping, *path, default=""):
    value = mapping
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    return default if value is None else value


def number_text(value):
    if value is None:
        return ""
    return str(value).replace(",", "").replace("萬", "").replace("坪", "").replace("樓", "").strip()


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        "Referer": SOURCE_URL,
        "Origin": "https://market.591.com.tw",
        "device": "pc",
        "deviceid": "591-export-jingmao",
        "Cache-Control": "no-cache",
    })

    all_items = []
    total = 0
    total_page = 0
    for page in range(1, 7):
        payload = fetch_page(session, page)
        (OUT_DIR / f"page_{page}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        data = payload.get("data") or {}
        if page == 1:
            total = int(data.get("total") or data.get("total_count") or 0)
            total_page = int(data.get("total_page") or 0)
        all_items.extend(data.get("items") or [])
        time.sleep(1)

    seen = set()
    deduped = []
    for item in all_items:
        key = item.get("id") or json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    fields = [
        "id", "成交日期", "成交年月_民國", "成交年月_西元", "樓層", "總樓層",
        "單價_萬每坪_不含車位", "原始單價_萬每坪_含車位", "房屋總價_萬_不含車位",
        "車位總價_萬", "成交總價_萬_含車位", "房屋坪數_坪_不含車位", "車位坪數_坪",
        "總坪數_坪_含車位", "車位數", "車位類型", "房型", "特殊交易", "特殊交易說明",
        "樓層標籤", "地址", "建案名稱", "來源網址"
    ]
    csv_path = OUT_DIR / "jingmao_591_103.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for item in deduped:
            trans_date = str(item.get("trans_date") or "")
            month_roc = str(item.get("month") or "")
            month_ad = trans_date[:7] if len(trans_date) >= 7 else ""
            tags = item.get("tag") or []
            writer.writerow({
                "id": item.get("id", ""),
                "成交日期": trans_date,
                "成交年月_民國": month_roc,
                "成交年月_西元": month_ad,
                "樓層": number_text(item.get("shift_floor_val") or item.get("original_shift_floor") or item.get("shift_floor")),
                "總樓層": number_text(item.get("original_total_floor") or item.get("total_floor")),
                "單價_萬每坪_不含車位": number_text(pick(item, "unit_price", "price")),
                "原始單價_萬每坪_含車位": number_text(pick(item, "src_unit_price", "price")),
                "房屋總價_萬_不含車位": number_text(pick(item, "building_total_price", "price")),
                "車位總價_萬": number_text(item.get("real_park_total_price") or pick(item, "real_park_total_price_v", "price")),
                "成交總價_萬_含車位": number_text(item.get("total_price_v") or item.get("total_price")),
                "房屋坪數_坪_不含車位": number_text(pick(item, "building_area", "area")),
                "車位坪數_坪": number_text(pick(item, "real_park_area", "area")),
                "總坪數_坪_含車位": number_text(pick(item, "build_area_v", "area") or item.get("build_area")),
                "車位數": item.get("park_count", ""),
                "車位類型": item.get("park_type_str", ""),
                "房型": item.get("layout_v2") or item.get("layout") or "",
                "特殊交易": "是" if int(item.get("is_special") or 0) == 1 else "否",
                "特殊交易說明": item.get("context") or item.get("tips") or "",
                "樓層標籤": "、".join(str(x) for x in tags),
                "地址": item.get("address", ""),
                "建案名稱": pick(item, "community", "name"),
                "來源網址": SOURCE_URL,
            })

    csv_bytes = csv_path.read_bytes()
    compressed = gzip.compress(csv_bytes, compresslevel=9)
    b64_text = base64.b64encode(compressed).decode("ascii")
    (OUT_DIR / "jingmao_591_103.csv.gz.b64.txt").write_text(b64_text, encoding="ascii")

    chunk_size = 544
    chunks = [b64_text[i:i + chunk_size] for i in range(0, len(b64_text), chunk_size)]
    for idx, chunk in enumerate(chunks, start=1):
        (OUT_DIR / f"b64_chunk_{idx:02d}.txt").write_text(chunk, encoding="ascii")

    summary = {
        "reported_total": total,
        "reported_total_page": total_page,
        "raw_item_count": len(all_items),
        "deduped_count": len(deduped),
        "base64_chars": len(b64_text),
        "chunk_size": chunk_size,
        "chunk_count": len(chunks),
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "gzip_sha256": hashlib.sha256(compressed).hexdigest(),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    if len(deduped) != 103:
        print(f"Expected 103 records, got {len(deduped)}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
