from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

COMMUNITY_ID = 5886292
PAGE_SIZE = 20
BASE_URL = "https://bff-market.591.com.tw/v1/price/list"
OUT_DIR = Path("591_export")


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


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        "Referer": f"https://market.591.com.tw/{COMMUNITY_ID}/price?guide=1&trans_type=2",
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

    summary = {
        "reported_total": total,
        "reported_total_page": total_page,
        "raw_item_count": len(all_items),
        "deduped_count": len(deduped),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    if len(deduped) != 103:
        print(f"Expected 103 records, got {len(deduped)}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
