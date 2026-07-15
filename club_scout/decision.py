# -*- coding: utf-8 -*-
"""カタログ判定: GO / HOLD / PASS（基準ポイント集）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from scorer import load_ranks, load_rules, score_candidate

CLUB = Path(__file__).resolve().parent
CHECKLIST_PATH = CLUB / "rules" / "buy_checklist.yaml"


def load_checklist(path: Optional[Path] = None) -> Dict[str, Any]:
    path = path or CHECKLIST_PATH
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def resolve_family_mare_from_dam(dam_name: str) -> Optional[Dict[str, str]]:
    """
    カタログの母名 → 募集馬の母母(ketto6相当)。
    母馬レコードの ketto2 が募集仔の母母。
    """
    dam_name = (dam_name or "").strip()
    if not dam_name:
        return None
    try:
        import psycopg2
        import yaml as _yaml

        root = CLUB.parent
        cfg = _yaml.safe_load((root / "config" / "db.yaml").read_text(encoding="utf-8"))
        c = cfg["connections"][cfg["default_connection"]]
        conn = psycopg2.connect(
            host=c["host"],
            port=c["port"],
            dbname=c["database"],
            user=c["user"],
            password=c["password"],
            connect_timeout=10,
            options="-c statement_timeout=30000",
        )
        cur = conn.cursor()
        cur.execute(
            """
            SELECT bamei, ketto2_bamei, ketto6_bamei, banushi_code
            FROM kyosoba_master2
            WHERE TRIM(bamei) = %s
            ORDER BY
              CASE WHEN banushi_code = '553800' THEN 0 ELSE 1 END,
              seinengappi DESC NULLS LAST
            LIMIT 1
            """,
            (dam_name,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        # 仔の母母 = 母の母 = ketto2 of dam
        return {
            "dam": str(row[0] or ""),
            "family_mare": str(row[1] or "").strip(),  # 母母
            "dam_maternal_granddam": str(row[2] or "").strip(),  # 母の母母=看板候補
            "dam_banushi_code": str(row[3] or ""),
        }
    except Exception:
        return None


def _grade_pts(table: Dict[str, Any], grade: Optional[str]) -> int:
    if not grade:
        return int(table.get("none", 0))
    g = str(grade).upper()
    return int(table.get(g, table.get("none", 0)))


def _sire_tier(rules: Dict[str, Any], sire: str) -> str:
    table = rules.get("sires") or {}
    name = (sire or "").strip()
    val = table.get(name)
    if val is None:
        for k, v in table.items():
            if k == "default":
                continue
            if k and k in name:
                val = v
                break
    if val is None:
        val = table.get("default", 2.0)
    v = float(val)
    if v >= 3.5:
        return "top"
    if v >= 2.8:
        return "mid"
    return "low"


def _price_pts(cfg: Dict[str, Any], price: float) -> int:
    for tier in cfg.get("price_man_yen") or []:
        if price <= float(tier["max"]):
            return int(tier["pts"])
    return -2


def _kinjou_pts(cfg: Dict[str, Any], text: str, kinjou_meta: Dict[str, Any]) -> Tuple[int, List[str]]:
    pts_cfg = cfg.get("kinjou") or {}
    notes: List[str] = []
    if not (text or "").strip():
        return int(pts_cfg.get("none", 0)), ["近況なし"]
    hits = kinjou_meta.get("hits") or []
    pts = 0
    if any(str(h).startswith("+") for h in hits):
        pts += int(pts_cfg.get("positive_hit", 1))
        notes.append("近況プラス語")
    mild = ("停滞", "減量", "気になる", "安静", "休養")
    if any(m in text for m in mild) or any(str(h).startswith("-") for h in hits):
        pts += int(pts_cfg.get("negative_mild", -1))
        notes.append("近況注意語")
    if any(str(h).startswith("light_weight") for h in hits):
        pts += int(pts_cfg.get("light_weight", -1))
        notes.append("軽量帯")
    return pts, notes


def _hard_pass(check: Dict[str, Any], cand: Dict[str, Any]) -> Optional[str]:
    for rule in check.get("hard_pass") or []:
        field = rule.get("field")
        val = cand.get(field)
        if "in" in rule and str(val) in set(rule["in"]):
            return str(rule.get("reason") or field)
        if "gt" in rule:
            try:
                if float(val or 0) > float(rule["gt"]):
                    return str(rule.get("reason") or field)
            except Exception:
                pass
        if "contains_any" in rule:
            blob = str(val or "")
            for kw in rule["contains_any"]:
                if kw and kw in blob:
                    return str(rule.get("reason") or kw)
    return None


def _combo_hints(check: Dict[str, Any], ctx: Dict[str, Any]) -> List[str]:
    hints: List[str] = []
    hu = ctx.get("hiroo_unique_grade")
    tr = ctx.get("trainer_grade")
    cr = ctx.get("cross_grade")
    fo = ctx.get("family_overall_grade")
    st = ctx.get("sire_tier")
    price = float(ctx.get("price_man_yen") or 0)
    sig = ctx.get("signature_grade")

    if hu in ("S", "A") and tr in ("S", "A"):
        hints.append("C1 独自牝系×実績厩舎 → GO寄り")
    if cr in ("S", "A"):
        hints.append("C2 クロス本命 → GO寄り")
    if fo in ("S", "A") and st == "top" and price <= 2.0:
        hints.append("C3 強牝系×上位父×手頃価格 → GO寄り")
    if sig in ("S", "A") and fo in ("B", "C", None):
        hints.append("C4 看板血統が一段深い → HOLD〜条件付き")
    if price >= 2.5 and cr not in ("S", "A") and hu not in ("S", "A"):
        hints.append("C5 高額なのに独自/クロス弱い → PASS寄り")
    return hints


def decide(cand: Dict[str, Any], checklist: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    候補辞書から判定を返す。
    推奨入力: trainer, sire, dam（または family_mare）, price_man_yen, status, kinjou_latest
    任意: signature_line（母母母など看板牝系名）
    """
    check = checklist or load_checklist()
    rules = load_rules()
    ranks = load_ranks()
    pts_tbl = check.get("points") or {}

    work = dict(cand)
    resolve_meta = None
    if not work.get("family_mare") and work.get("dam"):
        resolve_meta = resolve_family_mare_from_dam(str(work["dam"]))
        if resolve_meta and resolve_meta.get("family_mare"):
            work["family_mare"] = resolve_meta["family_mare"]
            # 自動で看板候補（母の母母）も保持
            if not work.get("signature_line") and resolve_meta.get("dam_maternal_granddam"):
                work["signature_line"] = resolve_meta["dam_maternal_granddam"]

    hard = _hard_pass(check, work)
    scored = score_candidate(work, rules)
    fm = scored.get("family_meta") or {}
    cm = scored.get("cross_meta") or {}
    bd = scored.get("breakdown") or {}

    family_overall = fm.get("overall_grade")
    hiroo_u = fm.get("hiroo_family_grade") if fm.get("hiroo_unique") else None
    trainer_g = bd.get("trainer_grade")
    cross_g = cm.get("grade")
    sire_tier = _sire_tier(rules, str(work.get("sire") or ""))
    price = float(work.get("price_man_yen") or 0)

    # signature line grade from ranks
    sig_name = str(work.get("signature_line") or "").strip()
    sig_grade = None
    if sig_name and ranks:
        idx = (ranks.get("index") or {}).get("family_overall_by_name") or {}
        sig = idx.get(sig_name)
        if sig:
            if sig.get("hiroo_unique") and sig.get("hiroo_family_grade"):
                sig_grade = sig.get("hiroo_family_grade")
            else:
                sig_grade = sig.get("grade")

    detail: List[Dict[str, Any]] = []
    total_pts = 0

    def add(label: str, pts: int, note: str = "") -> None:
        nonlocal total_pts
        total_pts += pts
        detail.append({"item": label, "pts": pts, "note": note})

    add("牝系全体", _grade_pts(pts_tbl.get("family_overall") or {}, family_overall), str(family_overall))
    add("広尾独自", _grade_pts(pts_tbl.get("hiroo_unique") or {}, hiroo_u), str(hiroo_u))
    add("看板牝系", _grade_pts(pts_tbl.get("signature_line") or {}, sig_grade), sig_name or "-")
    add("広尾×調教師", _grade_pts(pts_tbl.get("trainer_hiroo") or {}, trainer_g), str(trainer_g))
    add("クロス", _grade_pts(pts_tbl.get("cross") or {}, cross_g), str(cross_g))
    sire_pts = {"top": 2, "mid": 1, "low": 0}.get(sire_tier, 0)
    # override from yaml points.sire_tier if present
    st_cfg = pts_tbl.get("sire_tier") or {}
    sire_pts = int(st_cfg.get(sire_tier, sire_pts))
    add("父", sire_pts, sire_tier)
    add("価格", _price_pts(pts_tbl, price), f"{price}万円")
    kpts, knotes = _kinjou_pts(pts_tbl, str(work.get("kinjou_latest") or ""), scored.get("kinjou_meta") or {})
    add("近況", kpts, ",".join(knotes) if knotes else "")

    ctx = {
        "hiroo_unique_grade": hiroo_u,
        "trainer_grade": trainer_g,
        "cross_grade": cross_g,
        "family_overall_grade": family_overall,
        "sire_tier": sire_tier,
        "price_man_yen": price,
        "signature_grade": sig_grade,
    }
    combos = _combo_hints(check, ctx)

    verdict_cfg = check.get("verdict") or {}
    if hard:
        verdict = "PASS"
        label = "見送り"
        meaning = f"即見送り: {hard}"
    else:
        go_min = int((verdict_cfg.get("GO") or {}).get("min", 12))
        hold_min = int((verdict_cfg.get("HOLD") or {}).get("min", 8))
        if total_pts >= go_min:
            verdict = "GO"
        elif total_pts >= hold_min:
            verdict = "HOLD"
        else:
            verdict = "PASS"
        label = (verdict_cfg.get(verdict) or {}).get("label", verdict)
        meaning = (verdict_cfg.get(verdict) or {}).get("meaning", "")

    return {
        "verdict": verdict,
        "label": label,
        "meaning": meaning,
        "points": total_pts,
        "detail": detail,
        "combo_hints": combos,
        "hard_pass_reason": hard,
        "scored": scored,
        "resolved": resolve_meta,
        "family_mare": work.get("family_mare"),
        "signature_line": work.get("signature_line") or sig_name or None,
        "pocket_card": check.get("pocket_card") or [],
    }


def pocket_card_text(checklist: Optional[Dict[str, Any]] = None) -> str:
    check = checklist or load_checklist()
    lines = ["【Club Scout ポケット判定カード】", ""]
    for x in check.get("pocket_card") or []:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("コンボ:")
    for c in check.get("combo_rules") or []:
        lines.append(f"- {c.get('id')} {c.get('name')}: {c.get('verdict_hint')}（{c.get('when')}）")
    return "\n".join(lines)
