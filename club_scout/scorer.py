# -*- coding: utf-8 -*-
"""募集馬スコアリング＋相対ランキング（DBクロス統計対応）。"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

CLUB = Path(__file__).resolve().parent
RULES_PATH = CLUB / "rules" / "hiroo_hit_map.yaml"
RANKS_PATH = CLUB / "data" / "family_trainer_ranks.json"

_WEIGHT_RE = re.compile(r"(?<!\d)(\d{3})(?:\.\d+)?\s*kg", re.IGNORECASE)


def load_rules(path: Optional[Path] = None) -> Dict[str, Any]:
    path = path or RULES_PATH
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_ranks(path: str = "") -> Dict[str, Any]:
    p = Path(path) if path else RANKS_PATH
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def reload_ranks() -> None:
    load_ranks.cache_clear()


def _norm_name(s: str) -> str:
    return (s or "").strip().replace("　", " ").replace("'", "'")


def _lookup_trainer(ranks: Dict[str, Any], trainer: str) -> Optional[Dict[str, Any]]:
    idx = (ranks.get("index") or {}).get("trainer_hiroo_by_name") or {}
    name = _norm_name(trainer)
    if name in idx:
        return idx[name]
    for k, v in idx.items():
        if name.startswith(k) or k.startswith(name):
            return v
    return None


def _lookup_family(ranks: Dict[str, Any], family_mare: str) -> Tuple[Optional[Dict], Optional[Dict]]:
    """母母名で overall / hiroo を返す。"""
    name = _norm_name(family_mare)
    if not name:
        return None, None
    overall_idx = (ranks.get("index") or {}).get("family_overall_by_name") or {}
    hiroo_idx = (ranks.get("index") or {}).get("family_hiroo_by_name") or {}
    overall = overall_idx.get(name)
    hiroo = hiroo_idx.get(name)
    if overall is None:
        for k, v in overall_idx.items():
            if name in k or k in name:
                overall = v
                name = k
                break
    if hiroo is None and name:
        hiroo = hiroo_idx.get(name)
    return overall, hiroo


def _lookup_cross(ranks: Dict[str, Any], trainer: str, family_mare: str) -> Optional[Dict[str, Any]]:
    cross = (ranks.get("index") or {}).get("cross_by_key") or {}
    t = _norm_name(trainer)
    f = _norm_name(family_mare)
    key = f"{t}|{f}"
    if key in cross:
        return cross[key]
    for k, v in cross.items():
        tk, fk = k.split("|", 1)
        if (t.startswith(tk) or tk.startswith(t)) and (f in fk or fk in f):
            return v
    return None


def _yaml_trainer_score(rules: Dict[str, Any], trainer: str) -> Tuple[float, str]:
    table = rules.get("trainers") or {}
    name = (trainer or "").strip()
    if name and name not in table:
        for k in table:
            if k == "default":
                continue
            if name.startswith(k) or k.startswith(name):
                name = k
                break
    entry = table.get(name) or table.get("default") or {"grade": "C", "score": 2.0}
    return float(entry.get("score", 2.0)), str(entry.get("grade", "C"))


def _sire_score(rules: Dict[str, Any], sire: str) -> float:
    table = rules.get("sires") or {}
    name = (sire or "").strip()
    if name in table:
        return float(table[name])
    for k, v in table.items():
        if k == "default":
            continue
        if k and k in name:
            return float(v)
    return float(table.get("default", 2.0))


def _yaml_family_score(rules: Dict[str, Any], label: str) -> float:
    table = rules.get("broodmare_family") or {}
    key = (label or "unknown").strip().upper() or "UNKNOWN"
    if key in table:
        return float(table[key])
    if key.lower() in table:
        return float(table[key.lower()])
    return float(table.get("default", table.get("unknown", 2.0)))


def _price_score(rules: Dict[str, Any], price_man_yen: float) -> float:
    tiers = rules.get("price_tiers_man_yen") or []
    for tier in tiers:
        if price_man_yen <= float(tier["max"]):
            return float(tier["score"])
    return -1.0


def _kinjou_score(rules: Dict[str, Any], text: str) -> Tuple[float, Dict[str, Any]]:
    cfg = rules.get("kinjou") or {}
    score = float(cfg.get("base", 2.0))
    hits: List[str] = []
    blob = text or ""
    for item in cfg.get("positive") or []:
        kw = str(item.get("keyword", ""))
        if kw and kw in blob:
            score += float(item.get("delta", 0))
            hits.append(f"+{kw}")
    for item in cfg.get("negative") or []:
        kw = str(item.get("keyword", ""))
        if kw and kw in blob:
            score += float(item.get("delta", 0))
            hits.append(f"-{kw}")
    weights = [int(m.group(1)) for m in _WEIGHT_RE.finditer(blob)]
    alert_kg = cfg.get("weight_light_alert_kg")
    if weights and alert_kg is not None and min(weights) <= int(alert_kg):
        score += float(cfg.get("weight_light_delta", -0.3))
        hits.append(f"light_weight:{min(weights)}")
    lo, hi = float(cfg.get("min", 0.0)), float(cfg.get("max", 3.0))
    score = max(lo, min(hi, score))
    return score, {"hits": hits, "weights_kg": weights}


def _skip_flags(rules: Dict[str, Any], cand: Dict[str, Any], price: float) -> List[str]:
    flags: List[str] = []
    skip = rules.get("skip_if") or {}
    status = str(cand.get("status") or "")
    if status in (skip.get("status_in") or []):
        flags.append(f"status:{status}")
    over = skip.get("price_over_man_yen")
    if over is not None and price > float(over):
        flags.append(f"price_over:{price}")
    return flags


def recommended_units(rules: Dict[str, Any], total: float, price_man_yen: float) -> str:
    budget = rules.get("budget") or {}
    monthly = float(budget.get("default_monthly_yen", 10000))
    cap = int(budget.get("max_units_per_horse", 4))
    unit_yen = max(price_man_yen * 10000.0, 1.0)
    by_budget = max(1, int(monthly // (unit_yen / 12.0))) if unit_yen else 1
    if total >= 16:
        want = min(cap, max(2, by_budget))
    elif total >= 13:
        want = min(cap, max(1, min(2, by_budget)))
    else:
        want = 1
    return f"1〜{want}口" if want > 1 else "1口（様子見）"


def _db_family_points(
    rules: Dict[str, Any], ranks: Dict[str, Any], family_mare: str
) -> Tuple[float, Dict[str, Any]]:
    """
    牝系点 =
      全体強さ (family_overall.score 中心)
    + 広尾独自ボーナス (hiroo_family_grade)
    yaml手動ラベルは family_mare が無いときのみ。
    """
    cfg = rules.get("db_ranks") or {}
    overall, hiroo = _lookup_family(ranks, family_mare)
    meta: Dict[str, Any] = {
        "family_mare": family_mare,
        "hiroo_unique": False,
        "overall_grade": None,
        "hiroo_family_grade": None,
        "hiroo_family_rank": None,
    }
    if not overall and not hiroo:
        return 0.0, {**meta, "source": "none"}

    base = float((overall or hiroo or {}).get("score") or cfg.get("family_default", 2.0))
    # 広尾での実績がある場合は全体と広尾の加重
    if overall and hiroo:
        w_all = float(cfg.get("family_overall_weight", 0.55))
        w_hi = float(cfg.get("family_hiroo_weight", 0.45))
        base = w_all * float(overall.get("score") or 2.0) + w_hi * float(hiroo.get("score") or 2.0)

    bonus = 0.0
    if overall and overall.get("hiroo_unique"):
        meta["hiroo_unique"] = True
        meta["hiroo_family_grade"] = overall.get("hiroo_family_grade")
        meta["hiroo_family_rank"] = overall.get("hiroo_family_rank")
        hg = str(overall.get("hiroo_family_grade") or "C")
        bonus_map = cfg.get("hiroo_unique_bonus") or {"S": 1.5, "A": 1.0, "B": 0.5, "C": 0.2}
        bonus = float(bonus_map.get(hg, 0.2))

    if overall:
        meta["overall_grade"] = overall.get("grade")
        meta["overall_rank"] = overall.get("rank")
    if hiroo:
        meta["hiroo_only_grade"] = hiroo.get("grade")
        meta["hiroo_only_rank"] = hiroo.get("rank")
    meta["source"] = "db"
    return round(base + bonus, 2), meta


def score_candidate(cand: Dict[str, Any], rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rules = rules or load_rules()
    ranks = load_ranks()
    cfg = rules.get("db_ranks") or {}

    family_mare = str(cand.get("family_mare") or cand.get("maternal_granddam") or "").strip()
    trainer_name = str(cand.get("trainer") or "")

    # --- 牝系 ---
    family_meta: Dict[str, Any] = {}
    if family_mare and ranks:
        family_pts, family_meta = _db_family_points(rules, ranks, family_mare)
    else:
        family_pts = _yaml_family_score(rules, str(cand.get("family_label") or "unknown"))
        family_meta = {"source": "yaml_label", "family_label": cand.get("family_label")}

    # --- 調教師（広尾実績優先） ---
    t_db = _lookup_trainer(ranks, trainer_name) if ranks else None
    if t_db and t_db.get("grade") != "U":
        trainer_pts = float(t_db.get("score") or 2.0)
        trainer_grade = str(t_db.get("grade") or "C")
        trainer_source = "db_hiroo"
    else:
        trainer_pts, trainer_grade = _yaml_trainer_score(rules, trainer_name)
        trainer_source = "yaml"

    # --- クロスボーナス ---
    cross_pts = 0.0
    cross_meta: Dict[str, Any] = {}
    if family_mare and trainer_name and ranks:
        cross = _lookup_cross(ranks, trainer_name, family_mare)
        if cross and cross.get("grade") != "U":
            bonus_map = cfg.get("cross_bonus") or {"S": 1.5, "A": 1.0, "B": 0.5, "C": 0.2}
            cross_pts = float(bonus_map.get(str(cross.get("grade")), 0.2))
            cross_meta = {
                "grade": cross.get("grade"),
                "rank": cross.get("rank"),
                "win_rate_sm": cross.get("win_rate_sm"),
                "n_horses": cross.get("n_horses"),
            }

    sire_pts = _sire_score(rules, str(cand.get("sire") or ""))
    price = float(cand.get("price_man_yen") or 0)
    price_pts = _price_score(rules, price)
    kinjou_text = str(cand.get("kinjou_latest") or "")
    body_pts, kinjou_meta = _kinjou_score(rules, kinjou_text)

    total = family_pts + trainer_pts + cross_pts + sire_pts + body_pts + price_pts
    max_score = float((rules.get("meta") or {}).get("max_score", 22.0))
    total = round(min(max_score, total), 2)
    skips = _skip_flags(rules, cand, price)

    return {
        "id": cand.get("id"),
        "name": cand.get("name"),
        "total": total,
        "max_score": max_score,
        "breakdown": {
            "family": round(family_pts, 2),
            "trainer": round(trainer_pts, 2),
            "trainer_grade": trainer_grade,
            "trainer_source": trainer_source,
            "cross": round(cross_pts, 2),
            "sire": round(sire_pts, 2),
            "body_kinjou": round(body_pts, 2),
            "price": round(price_pts, 2),
        },
        "family_meta": family_meta,
        "cross_meta": cross_meta,
        "kinjou_meta": kinjou_meta,
        "skip_flags": skips,
        "eligible": len(skips) == 0,
        "recommend_units": recommended_units(rules, total, price),
        "pool": cand.get("pool") or "default",
        "status": cand.get("status"),
        "price_man_yen": price,
        "trainer": cand.get("trainer"),
        "sire": cand.get("sire"),
        "family_mare": family_mare or None,
        "family_label": cand.get("family_label") or "unknown",
    }


def rank_candidates(
    candidates: List[Dict[str, Any]],
    rules: Optional[Dict[str, Any]] = None,
    pool: Optional[str] = None,
    only_eligible: bool = False,
) -> List[Dict[str, Any]]:
    rules = rules or load_rules()
    scored = [score_candidate(c, rules) for c in candidates]
    if pool:
        scored = [s for s in scored if str(s.get("pool")) == pool]
    if only_eligible:
        scored = [s for s in scored if s.get("eligible")]
    scored.sort(key=lambda x: (-float(x["total"]), str(x.get("name") or "")))
    for i, s in enumerate(scored, start=1):
        s["rank"] = i
        if i == 1 and s.get("eligible"):
            s["label"] = "本命"
        elif i == 2 and s.get("eligible"):
            s["label"] = "控え"
        else:
            s["label"] = "見送り" if not s.get("eligible") else f"{i}位"
    return scored
