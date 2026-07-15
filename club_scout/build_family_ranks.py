# -*- coding: utf-8 -*-
"""
広尾牝系・調教師クロス統計ランク生成（SELECTのみ）。

出力 data/family_trainer_ranks.json:
  - family_overall: 牝系(母母=ketto6)のJRA全体強さ
  - family_hiroo:   広尾所属時のみの牝系成績 → 広尾牝系ランク
  - trainer_hiroo:  広尾×調教師
  - cross_hiroo:    広尾×調教師×牝系
  - hiroo_unique_families: 広尾比率が高い独自牝系
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[1]
CLUB = Path(__file__).resolve().parent
OUT_PATH = CLUB / "data" / "family_trainer_ranks.json"
BANUSHI_CODE = "553800"

# 小標本の過剰適合を抑える
MIN_FAMILY_HORSES = 2
MIN_FAMILY_STARTS = 15
MIN_TRAINER_HORSES = 2
MIN_CROSS_HORSES = 2
HIROO_UNIQUE_MIN_HORSES = 3
HIROO_UNIQUE_MIN_SHARE = 0.35


def _toi(v: Any) -> int:
    try:
        return int(str(v).strip() or "0")
    except Exception:
        return 0


def _connect():
    cfg = yaml.safe_load((ROOT / "config" / "db.yaml").read_text(encoding="utf-8"))
    c = cfg["connections"][cfg["default_connection"]]
    import psycopg2

    return psycopg2.connect(
        host=c["host"],
        port=c["port"],
        dbname=c["database"],
        user=c["user"],
        password=c["password"],
        connect_timeout=10,
        options="-c statement_timeout=180000",
    )


def _row_metrics(wins: int, starts: int, prize_hyaku: int, n_horses: int) -> Dict[str, Any]:
    """複合指標（平滑勝率 + 頭あたり本賞金）。"""
    win_rate_sm = (wins + 1.0) / (starts + 12.0)
    prize_per_horse = (prize_hyaku / 10.0) / max(n_horses, 1)  # 千円→万円っぽく /10? 百円単位→円は*100
    # heichi_honshokin_ruikei は百円単位 → 万円 = prize_hyaku * 100 / 10000 = prize_hyaku / 100
    prize_man_per_horse = (prize_hyaku / 100.0) / max(n_horses, 1)
    # 合成スコア（後でパーセンタイル化）
    composite_raw = win_rate_sm * 100.0 + math.log1p(max(prize_man_per_horse, 0.0)) * 2.0
    return {
        "wins": wins,
        "starts": starts,
        "n_horses": n_horses,
        "win_rate": round(wins / starts, 4) if starts else 0.0,
        "win_rate_sm": round(win_rate_sm, 4),
        "prize_man_per_horse": round(prize_man_per_horse, 2),
        "composite_raw": round(composite_raw, 4),
    }


def _assign_grades(rows: List[Dict[str, Any]], min_starts: int) -> List[Dict[str, Any]]:
    eligible = [r for r in rows if int(r.get("starts") or 0) >= min_starts]
    eligible.sort(key=lambda x: float(x.get("composite_raw") or 0), reverse=True)
    n = len(eligible)
    for i, r in enumerate(eligible):
        pct = (i + 0.5) / n if n else 1.0
        if pct <= 0.15:
            grade, score = "S", 6.0
        elif pct <= 0.40:
            grade, score = "A", 4.5
        elif pct <= 0.75:
            grade, score = "B", 3.0
        else:
            grade, score = "C", 1.5
        r["rank"] = i + 1
        r["grade"] = grade
        r["score"] = score
        r["percentile"] = round(1.0 - pct, 4)
    # 不足標本
    for r in rows:
        if "grade" not in r:
            r["rank"] = None
            r["grade"] = "U"
            r["score"] = 2.0
            r["percentile"] = None
            r["note"] = "標本不足"
    # rank一覧は eligible 順 + 不足
    out = eligible + [r for r in rows if r.get("grade") == "U"]
    return out


def _fetch_agg(cur, where_extra: str, params: Tuple[Any, ...], group_sql: str, group_keys: List[str]):
    sql = f"""
        SELECT {group_sql},
               COUNT(*) AS n_horses,
               COALESCE(SUM(CAST(NULLIF(TRIM(chuo_gokei_1chaku), '') AS INTEGER)), 0) AS wins,
               COALESCE(SUM(
                 CAST(NULLIF(TRIM(chuo_gokei_1chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_2chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_3chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_4chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_5chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_chakugai), '') AS INTEGER)
               ), 0) AS starts,
               COALESCE(SUM(CAST(NULLIF(TRIM(heichi_honshokin_ruikei), '') AS INTEGER)), 0) AS prize
        FROM kyosoba_master2
        WHERE TRIM(COALESCE(ketto6_bamei, '')) <> ''
          AND TRIM(COALESCE(ketto6_hanshoku_toroku_bango, '')) <> ''
          {where_extra}
        GROUP BY {group_sql}
        HAVING COUNT(*) >= %s
    """
    cur.execute(sql, params + (MIN_FAMILY_HORSES if "ketto6" in group_sql else MIN_TRAINER_HORSES,))
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        d = dict(zip(cols, raw))
        m = _row_metrics(_toi(d["wins"]), _toi(d["starts"]), _toi(d["prize"]), _toi(d["n_horses"]))
        item = {k: (str(d[k]).strip() if d[k] is not None else "") for k in group_keys}
        item.update(m)
        rows.append(item)
    return rows


def build() -> Dict[str, Any]:
    conn = _connect()
    cur = conn.cursor()

    # --- 広尾×調教師 ---
    cur.execute(
        """
        SELECT TRIM(chokyoshimei_ryakusho) AS trainer,
               chokyoshi_code,
               COUNT(*) AS n_horses,
               COALESCE(SUM(CAST(NULLIF(TRIM(chuo_gokei_1chaku), '') AS INTEGER)), 0) AS wins,
               COALESCE(SUM(
                 CAST(NULLIF(TRIM(chuo_gokei_1chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_2chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_3chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_4chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_5chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_chakugai), '') AS INTEGER)
               ), 0) AS starts,
               COALESCE(SUM(CAST(NULLIF(TRIM(heichi_honshokin_ruikei), '') AS INTEGER)), 0) AS prize
        FROM kyosoba_master2
        WHERE banushi_code = %s
          AND TRIM(COALESCE(chokyoshimei_ryakusho, '')) <> ''
        GROUP BY 1, 2
        HAVING COUNT(*) >= %s
        """,
        (BANUSHI_CODE, MIN_TRAINER_HORSES),
    )
    tcols = [d[0] for d in cur.description]
    trainer_hiroo: List[Dict[str, Any]] = []
    for raw in cur.fetchall():
        d = dict(zip(tcols, raw))
        m = _row_metrics(_toi(d["wins"]), _toi(d["starts"]), _toi(d["prize"]), _toi(d["n_horses"]))
        trainer_hiroo.append(
            {
                "trainer": str(d["trainer"] or "").strip(),
                "chokyoshi_code": str(d["chokyoshi_code"] or "").strip(),
                **m,
            }
        )
    trainer_hiroo = _assign_grades(trainer_hiroo, min_starts=20)

    # --- 広尾牝系 (ketto6) ---
    cur.execute(
        """
        SELECT TRIM(ketto6_bamei) AS family_name,
               ketto6_hanshoku_toroku_bango AS family_code,
               COUNT(*) AS n_horses,
               COALESCE(SUM(CAST(NULLIF(TRIM(chuo_gokei_1chaku), '') AS INTEGER)), 0) AS wins,
               COALESCE(SUM(
                 CAST(NULLIF(TRIM(chuo_gokei_1chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_2chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_3chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_4chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_5chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_chakugai), '') AS INTEGER)
               ), 0) AS starts,
               COALESCE(SUM(CAST(NULLIF(TRIM(heichi_honshokin_ruikei), '') AS INTEGER)), 0) AS prize
        FROM kyosoba_master2
        WHERE banushi_code = %s
          AND TRIM(COALESCE(ketto6_bamei, '')) <> ''
        GROUP BY 1, 2
        HAVING COUNT(*) >= %s
        """,
        (BANUSHI_CODE, MIN_FAMILY_HORSES),
    )
    fcols = [d[0] for d in cur.description]
    family_hiroo: List[Dict[str, Any]] = []
    fam_codes: List[str] = []
    for raw in cur.fetchall():
        d = dict(zip(fcols, raw))
        m = _row_metrics(_toi(d["wins"]), _toi(d["starts"]), _toi(d["prize"]), _toi(d["n_horses"]))
        code = str(d["family_code"] or "").strip()
        fam_codes.append(code)
        family_hiroo.append(
            {
                "family_name": str(d["family_name"] or "").strip(),
                "family_code": code,
                **m,
            }
        )
    family_hiroo = _assign_grades(family_hiroo, min_starts=MIN_FAMILY_STARTS)

    # --- 同牝系のJRA全体成績（広尾出現牝系に限定） ---
    family_overall: List[Dict[str, Any]] = []
    if fam_codes:
        cur.execute(
            """
            SELECT TRIM(ketto6_bamei) AS family_name,
                   ketto6_hanshoku_toroku_bango AS family_code,
                   COUNT(*) AS n_horses,
                   SUM(CASE WHEN banushi_code = %s THEN 1 ELSE 0 END) AS hiroo_horses,
                   COALESCE(SUM(CAST(NULLIF(TRIM(chuo_gokei_1chaku), '') AS INTEGER)), 0) AS wins,
                   COALESCE(SUM(
                     CAST(NULLIF(TRIM(chuo_gokei_1chaku), '') AS INTEGER)
                   + CAST(NULLIF(TRIM(chuo_gokei_2chaku), '') AS INTEGER)
                   + CAST(NULLIF(TRIM(chuo_gokei_3chaku), '') AS INTEGER)
                   + CAST(NULLIF(TRIM(chuo_gokei_4chaku), '') AS INTEGER)
                   + CAST(NULLIF(TRIM(chuo_gokei_5chaku), '') AS INTEGER)
                   + CAST(NULLIF(TRIM(chuo_gokei_chakugai), '') AS INTEGER)
                   ), 0) AS starts,
                   COALESCE(SUM(CAST(NULLIF(TRIM(heichi_honshokin_ruikei), '') AS INTEGER)), 0) AS prize
            FROM kyosoba_master2
            WHERE ketto6_hanshoku_toroku_bango = ANY(%s)
            GROUP BY 1, 2
            """,
            (BANUSHI_CODE, fam_codes),
        )
        ocols = [d[0] for d in cur.description]
        for raw in cur.fetchall():
            d = dict(zip(ocols, raw))
            n = _toi(d["n_horses"])
            h = _toi(d["hiroo_horses"])
            m = _row_metrics(_toi(d["wins"]), _toi(d["starts"]), _toi(d["prize"]), n)
            share = (h / n) if n else 0.0
            family_overall.append(
                {
                    "family_name": str(d["family_name"] or "").strip(),
                    "family_code": str(d["family_code"] or "").strip(),
                    "hiroo_horses": h,
                    "hiroo_share": round(share, 4),
                    "hiroo_unique": bool(
                        h >= HIROO_UNIQUE_MIN_HORSES and share >= HIROO_UNIQUE_MIN_SHARE
                    ),
                    **m,
                }
            )
        family_overall = _assign_grades(family_overall, min_starts=MIN_FAMILY_STARTS)

    # --- クロス: 広尾×調教師×牝系 ---
    cur.execute(
        """
        SELECT TRIM(chokyoshimei_ryakusho) AS trainer,
               TRIM(ketto6_bamei) AS family_name,
               ketto6_hanshoku_toroku_bango AS family_code,
               COUNT(*) AS n_horses,
               COALESCE(SUM(CAST(NULLIF(TRIM(chuo_gokei_1chaku), '') AS INTEGER)), 0) AS wins,
               COALESCE(SUM(
                 CAST(NULLIF(TRIM(chuo_gokei_1chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_2chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_3chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_4chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_5chaku), '') AS INTEGER)
               + CAST(NULLIF(TRIM(chuo_gokei_chakugai), '') AS INTEGER)
               ), 0) AS starts,
               COALESCE(SUM(CAST(NULLIF(TRIM(heichi_honshokin_ruikei), '') AS INTEGER)), 0) AS prize
        FROM kyosoba_master2
        WHERE banushi_code = %s
          AND TRIM(COALESCE(chokyoshimei_ryakusho, '')) <> ''
          AND TRIM(COALESCE(ketto6_bamei, '')) <> ''
        GROUP BY 1, 2, 3
        HAVING COUNT(*) >= %s
        """,
        (BANUSHI_CODE, MIN_CROSS_HORSES),
    )
    ccols = [d[0] for d in cur.description]
    cross_hiroo: List[Dict[str, Any]] = []
    for raw in cur.fetchall():
        d = dict(zip(ccols, raw))
        m = _row_metrics(_toi(d["wins"]), _toi(d["starts"]), _toi(d["prize"]), _toi(d["n_horses"]))
        cross_hiroo.append(
            {
                "trainer": str(d["trainer"] or "").strip(),
                "family_name": str(d["family_name"] or "").strip(),
                "family_code": str(d["family_code"] or "").strip(),
                **m,
            }
        )
    cross_hiroo = _assign_grades(cross_hiroo, min_starts=10)

    cur.close()
    conn.close()

    # インデックス（名前引き）
    by_family_overall = {r["family_name"]: r for r in family_overall if r.get("family_name")}
    by_family_hiroo = {r["family_name"]: r for r in family_hiroo if r.get("family_name")}
    by_trainer = {r["trainer"]: r for r in trainer_hiroo if r.get("trainer")}
    hiroo_unique = [r for r in family_overall if r.get("hiroo_unique")]
    hiroo_unique.sort(key=lambda x: float(x.get("composite_raw") or 0), reverse=True)
    for i, r in enumerate(hiroo_unique, 1):
        pct = (i - 0.5) / len(hiroo_unique) if hiroo_unique else 1.0
        if pct <= 0.20:
            hg = "S"
        elif pct <= 0.50:
            hg = "A"
        elif pct <= 0.80:
            hg = "B"
        else:
            hg = "C"
        r["hiroo_family_rank"] = i
        r["hiroo_family_grade"] = hg
    # family_overall 本体にも同値を書く
    uniq_by_name = {r["family_name"]: r for r in hiroo_unique}
    for r in family_overall:
        u = uniq_by_name.get(r.get("family_name") or "")
        if u:
            r["hiroo_family_rank"] = u.get("hiroo_family_rank")
            r["hiroo_family_grade"] = u.get("hiroo_family_grade")

    return {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "banushi_code": BANUSHI_CODE,
        "definition": {
            "family_key": "ketto6（母母）",
            "hiroo_unique": (
                f"広尾頭数>={HIROO_UNIQUE_MIN_HORSES} かつ "
                f"広尾比率>={HIROO_UNIQUE_MIN_SHARE}"
            ),
            "grade": "複合指標の上位15%=S / 40%=A / 75%=B / 他=C（標本不足=U）",
            "metrics": "平滑勝率 + log(頭あたり本賞金万円)",
        },
        "trainer_hiroo": trainer_hiroo,
        "family_hiroo": family_hiroo,
        "family_overall": family_overall,
        "cross_hiroo": cross_hiroo,
        "hiroo_unique_families": hiroo_unique,
        "index": {
            "family_overall_by_name": by_family_overall,
            "family_hiroo_by_name": by_family_hiroo,
            "trainer_hiroo_by_name": by_trainer,
        },
    }


def main() -> None:
    data = build()
    # index は参照用に残すが、巨大化防止のため by_name は必要最小
    slim = {k: v for k, v in data.items() if k != "index"}
    # 名前引き用の薄い index
    slim["index"] = {
        "family_overall_by_name": {
            k: {"grade": v.get("grade"), "score": v.get("score"), "rank": v.get("rank"),
                "hiroo_unique": v.get("hiroo_unique"), "hiroo_family_grade": v.get("hiroo_family_grade"),
                "hiroo_family_rank": v.get("hiroo_family_rank"),
                "win_rate_sm": v.get("win_rate_sm"), "n_horses": v.get("n_horses")}
            for k, v in data["index"]["family_overall_by_name"].items()
        },
        "family_hiroo_by_name": {
            k: {"grade": v.get("grade"), "score": v.get("score"), "rank": v.get("rank"),
                "win_rate_sm": v.get("win_rate_sm"), "n_horses": v.get("n_horses")}
            for k, v in data["index"]["family_hiroo_by_name"].items()
        },
        "trainer_hiroo_by_name": {
            k: {"grade": v.get("grade"), "score": v.get("score"), "rank": v.get("rank"),
                "win_rate_sm": v.get("win_rate_sm"), "n_horses": v.get("n_horses")}
            for k, v in data["index"]["trainer_hiroo_by_name"].items()
        },
        "cross_by_key": {
            f"{r['trainer']}|{r['family_name']}": {
                "grade": r.get("grade"), "score": r.get("score"), "rank": r.get("rank"),
                "win_rate_sm": r.get("win_rate_sm"), "n_horses": r.get("n_horses"),
            }
            for r in data["cross_hiroo"]
            if r.get("grade") != "U"
        },
    }
    # 独自牝系の hiroo_family_* を overall index にマージ
    uniq_map = {r["family_name"]: r for r in data["hiroo_unique_families"]}
    for name, meta in slim["index"]["family_overall_by_name"].items():
        if name in uniq_map:
            meta["hiroo_unique"] = True
            meta["hiroo_family_rank"] = uniq_map[name].get("hiroo_family_rank")
            meta["hiroo_family_grade"] = uniq_map[name].get("hiroo_family_grade")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    print(
        f"trainers={len(slim['trainer_hiroo'])} "
        f"family_hiroo={len(slim['family_hiroo'])} "
        f"family_overall={len(slim['family_overall'])} "
        f"cross={len(slim['cross_hiroo'])} "
        f"unique={len(slim['hiroo_unique_families'])}"
    )


if __name__ == "__main__":
    main()
