# -*- coding: utf-8 -*-
"""広尾レース軸の要約を mykeibadb から読み出す（SELECTのみ）。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

ROOT = Path(__file__).resolve().parents[1]
CLUB = Path(__file__).resolve().parent
DEFAULT_OUT = CLUB / "data" / "axis_summary.json"
BANUSHI_CODE = "553800"


def _load_db_cfg() -> Dict[str, Any]:
    cfg = yaml.safe_load((ROOT / "config" / "db.yaml").read_text(encoding="utf-8"))
    return cfg["connections"][cfg["default_connection"]]


def fetch_axis_summary(banushi_code: str = BANUSHI_CODE) -> Dict[str, Any]:
    """馬主コード固定でマスタ要約を返す。巨大テーブル全走査はしない。"""
    import psycopg2

    conn_cfg = _load_db_cfg()
    conn = psycopg2.connect(
        host=conn_cfg["host"],
        port=conn_cfg["port"],
        dbname=conn_cfg["database"],
        user=conn_cfg["user"],
        password=conn_cfg["password"],
        connect_timeout=10,
        options="-c statement_timeout=60000",
    )
    cur = conn.cursor()
    out: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "banushi_code": banushi_code,
    }

    cur.execute(
        """
        SELECT banushi_code,
               banushi_hojinkaku_ari,
               banushi_hojinkaku_nashi,
               banushi_eng,
               chuo_gokei_1chaku_ruikei,
               chuo_gokei_2chaku_ruikei,
               chuo_gokei_3chaku_ruikei,
               honshokin_gokei_ruikei
        FROM banushi_master
        WHERE banushi_code = %s
        LIMIT 1
        """,
        (banushi_code,),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        raise RuntimeError(f"banushi_code={banushi_code} が見つかりません")
    cols = [d[0] for d in cur.description]
    owner = dict(zip(cols, row))
    out["owner"] = {k: (str(v) if v is not None else None) for k, v in owner.items()}

    cur.execute(
        """
        SELECT COUNT(*) AS n,
               SUM(CASE WHEN COALESCE(massho_kubun, '0') = '0' THEN 1 ELSE 0 END) AS active_n
        FROM kyosoba_master2
        WHERE banushi_code = %s
        """,
        (banushi_code,),
    )
    n, active_n = cur.fetchone()
    out["kyosoba_count"] = int(n or 0)
    out["kyosoba_active"] = int(active_n or 0)

    cur.execute(
        """
        SELECT
          COALESCE(SUM(CAST(NULLIF(TRIM(chuo_gokei_1chaku), '') AS INTEGER)), 0) AS wins,
          COALESCE(SUM(
            CAST(NULLIF(TRIM(chuo_gokei_1chaku), '') AS INTEGER)
          + CAST(NULLIF(TRIM(chuo_gokei_2chaku), '') AS INTEGER)
          + CAST(NULLIF(TRIM(chuo_gokei_3chaku), '') AS INTEGER)
          + CAST(NULLIF(TRIM(chuo_gokei_4chaku), '') AS INTEGER)
          + CAST(NULLIF(TRIM(chuo_gokei_5chaku), '') AS INTEGER)
          + CAST(NULLIF(TRIM(chuo_gokei_chakugai), '') AS INTEGER)
          ), 0) AS starts
        FROM kyosoba_master2
        WHERE banushi_code = %s
        """,
        (banushi_code,),
    )
    wins, starts = cur.fetchone()
    out["master_cum_stats"] = {"wins": int(wins or 0), "starts": int(starts or 0)}

    cur.execute(
        """
        SELECT chokyoshimei_ryakusho, chokyoshi_code, COUNT(*) AS n
        FROM kyosoba_master2
        WHERE banushi_code = %s
        GROUP BY chokyoshimei_ryakusho, chokyoshi_code
        ORDER BY n DESC
        LIMIT 30
        """,
        (banushi_code,),
    )
    tcols = [d[0] for d in cur.description]
    trainers: List[Dict[str, Any]] = []
    for r in cur.fetchall():
        t = dict(zip(tcols, r))
        trainers.append(
            {
                "chokyoshimei_ryakusho": str(t["chokyoshimei_ryakusho"] or ""),
                "chokyoshi_code": str(t["chokyoshi_code"] or ""),
                "n": int(t["n"] or 0),
            }
        )
    out["trainers_from_kyosoba"] = trainers

    cur.close()
    conn.close()
    return out


def save_axis_summary(
    path: Optional[Path] = None, banushi_code: str = BANUSHI_CODE
) -> Path:
    path = path or DEFAULT_OUT
    path.parent.mkdir(parents=True, exist_ok=True)
    data = fetch_axis_summary(banushi_code=banushi_code)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    out = save_axis_summary()
    print(f"wrote {out}")
