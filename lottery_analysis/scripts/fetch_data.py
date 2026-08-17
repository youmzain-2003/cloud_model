#!/usr/bin/env python3
"""Fetch Numbers3 and Bingo5 historical draws from public mirror sites.

Primary sources (Mizuho official backnumber is blocked/JS-rendered from this
environment):
  - Numbers3: https://numbers-renban.tokyo/numbers3/result_all
  - Bingo5:   https://bingo5.money-plan.net/history/{start}/
"""

from __future__ import annotations

import csv
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
UA = "Mozilla/5.0 (compatible; lottery-analysis/1.0; research)"


def get(url: str, retries: int = 4) -> str:
    last: Exception | None = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep(2**i)
    raise RuntimeError(f"failed to fetch {url}: {last}")


def parse_int(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def fetch_numbers3(out_path: Path) -> int:
    """Paginate Numbers3 results (newest first) and write CSV ascending by draw."""
    rows: dict[int, dict] = {}
    page = 1
    max_page = None
    while True:
        # l=20 is stable; larger l values truncate oddly on this site.
        url = (
            "https://numbers-renban.tokyo/numbers3/result_all"
            f"?s=desc&l=20&page={page}"
        )
        html = get(url)
        soup = BeautifulSoup(html, "lxml")
        if max_page is None:
            pages = [
                int(m.group(1))
                for a in soup.find_all("a", href=True)
                if (m := re.search(r"page=(\d+)", a["href"]))
            ]
            max_page = max(pages) if pages else 1
            print(f"Numbers3 pages: {max_page}")

        table = soup.select_one("table.table-striped")
        if not table:
            raise RuntimeError(f"Numbers3 table missing on page {page}")

        got = 0
        for tr in table.select("tr")[1:]:
            cols = [c.get_text(" ", strip=True) for c in tr.select("td")]
            if len(cols) < 5:
                continue
            draw_no = parse_int(cols[0])
            date_m = re.search(r"(\d{4}-\d{2}-\d{2})", cols[1])
            number = re.sub(r"\D", "", cols[2]).zfill(3)[-3:]
            winners = parse_int(cols[3])
            prize = parse_int(cols[4])
            if draw_no is None or not date_m or not re.fullmatch(r"\d{3}", number):
                continue
            rows[draw_no] = {
                "draw_no": draw_no,
                "date": date_m.group(1),
                "number": number,
                "d100": int(number[0]),
                "d10": int(number[1]),
                "d1": int(number[2]),
                "straight_winners": winners,
                "straight_prize_yen": prize,
            }
            got += 1

        print(f"  page {page}/{max_page}: +{got} (unique={len(rows)})")
        if page >= max_page or got == 0:
            break
        page += 1
        time.sleep(0.2)

    ordered = [rows[k] for k in sorted(rows)]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "draw_no",
                "date",
                "number",
                "d100",
                "d10",
                "d1",
                "straight_winners",
                "straight_prize_yen",
            ],
        )
        writer.writeheader()
        writer.writerows(ordered)
    return len(ordered)


def fetch_bingo5(out_path: Path) -> int:
    """Fetch Bingo5 history blocks (50 draws each)."""
    rows: dict[int, dict] = {}
    starts = list(range(1, 451, 50)) + [451]
    for start in starts:
        url = f"https://bingo5.money-plan.net/history/{start}/"
        html = get(url)
        soup = BeautifulSoup(html, "lxml")
        got = 0
        for table in soup.find_all("table"):
            header_cells = [
                c.get_text(" ", strip=True) for c in table.select("tr th, tr td")
            ]
            # Summary table: 回号 / 抽選日 / 当選数字 / 1等
            texts = " ".join(header_cells[:8])
            if "抽選日" not in texts or "当選数字" not in texts:
                continue
            for tr in table.select("tr")[1:]:
                cols = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                if len(cols) < 4:
                    continue
                draw_no = parse_int(cols[0])
                date_m = re.search(r"(\d{4}-\d{2}-\d{2})", cols[1])
                nums = [int(x) for x in re.findall(r"\d{1,2}", cols[2])]
                # Keep first 8 distinct valid bingo numbers 1-40
                cleaned: list[int] = []
                for n in nums:
                    if 1 <= n <= 40 and n not in cleaned:
                        cleaned.append(n)
                    if len(cleaned) == 8:
                        break
                winners = parse_int(cols[3]) if len(cols) > 3 else None
                prize = parse_int(cols[4]) if len(cols) > 4 else None
                if draw_no is None or not date_m or len(cleaned) != 8:
                    continue
                rows[draw_no] = {
                    "draw_no": draw_no,
                    "date": date_m.group(1),
                    "n1": cleaned[0],
                    "n2": cleaned[1],
                    "n3": cleaned[2],
                    "n4": cleaned[3],
                    "n5": cleaned[4],
                    "n6": cleaned[5],
                    "n7": cleaned[6],
                    "n8": cleaned[7],
                    "numbers": " ".join(f"{n:02d}" for n in cleaned),
                    "first_winners": winners,
                    "first_prize_yen": prize,
                }
                got += 1
            break
        print(f"Bingo5 history/{start}/: +{got} (unique={len(rows)})")
        time.sleep(0.35)

    ordered = [rows[k] for k in sorted(rows)]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "draw_no",
                "date",
                "n1",
                "n2",
                "n3",
                "n4",
                "n5",
                "n6",
                "n7",
                "n8",
                "numbers",
                "first_winners",
                "first_prize_yen",
            ],
        )
        writer.writeheader()
        writer.writerows(ordered)
    return len(ordered)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    n3 = fetch_numbers3(DATA / "numbers3_draws.csv")
    b5 = fetch_bingo5(DATA / "bingo5_draws.csv")
    print(f"Wrote Numbers3={n3}, Bingo5={b5}")


if __name__ == "__main__":
    main()
