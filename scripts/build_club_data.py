#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regenerate assets/club_data.js from club_scout canonical sources."""
from __future__ import annotations

import json
from pathlib import Path

try:
    import yaml
except ImportError as e:
    raise SystemExit("PyYAML required: pip install pyyaml") from e

ROOT = Path(__file__).resolve().parents[1]
CLUB = ROOT / "club_scout"
OUT = ROOT / "assets" / "club_data.js"

GRADE_JA = {
    "S": {"ja": "最上級", "short": "最上級（S）", "hint": "本線で強く加点"},
    "A": {"ja": "上級", "short": "上級（A）", "hint": "有力。積極検討"},
    "B": {"ja": "標準", "short": "標準（B）", "hint": "材料が揃えばHOLD〜"},
    "C": {"ja": "控えめ", "short": "控えめ（C）", "hint": "他材料が弱いとPASS寄り"},
    "U": {"ja": "データ不足", "short": "データ不足（U）", "hint": "標本少なく断定しない"},
    "none": {"ja": "未設定", "short": "未設定", "hint": "入力なし"},
}
SIRE_JA = {
    "top": {"ja": "上位", "short": "上位（top）", "hint": "ルール値 3.5以上"},
    "mid": {"ja": "中位", "short": "中位（mid）", "hint": "ルール値 2.8以上"},
    "low": {"ja": "下位", "short": "下位（low）", "hint": "2.8未満・未登録寄り"},
}


def sire_tier(v: float) -> str:
    v = float(v)
    if v >= 3.5:
        return "top"
    if v >= 2.8:
        return "mid"
    return "low"


def main() -> None:
    ranks = json.loads((CLUB / "data/family_trainer_ranks.json").read_text(encoding="utf-8"))
    rules = yaml.safe_load((CLUB / "rules/hiroo_hit_map.yaml").read_text(encoding="utf-8"))
    check = yaml.safe_load((CLUB / "rules/buy_checklist.yaml").read_text(encoding="utf-8"))
    idx = ranks.get("index") or {}
    fo = idx.get("family_overall_by_name") or {}
    fh = idx.get("family_hiroo_by_name") or {}
    th = idx.get("trainer_hiroo_by_name") or {}
    cx = idx.get("cross_by_key") or {}

    yaml_trainers = {k: v for k, v in (rules.get("trainers") or {}).items() if k != "default"}
    trainer_names = sorted(set(list(th.keys()) + list(yaml_trainers.keys())))
    trainers = []
    for name in trainer_names:
        db = th.get(name)
        y = yaml_trainers.get(name)
        if db and db.get("grade") != "U":
            eff_g, eff_src, eff_score = db.get("grade"), "db_hiroo", db.get("score")
        elif y:
            eff_g, eff_src, eff_score = y.get("grade"), "yaml", y.get("score")
        elif db:
            eff_g, eff_src, eff_score = db.get("grade"), "db_hiroo", db.get("score")
        else:
            continue
        trainers.append(
            {
                "name": name,
                "effective_grade": eff_g,
                "effective_source": eff_src,
                "effective_score": eff_score,
                "db": db,
                "yaml": {"grade": y.get("grade"), "score": y.get("score")} if y else None,
                "n_horses": (db or {}).get("n_horses"),
                "win_rate_sm": (db or {}).get("win_rate_sm"),
            }
        )
    order = {"S": 0, "A": 1, "B": 2, "C": 3, "U": 4}
    trainers.sort(
        key=lambda t: (order.get(t["effective_grade"], 9), -(t.get("effective_score") or 0), t["name"])
    )

    sires = []
    for name, val in (rules.get("sires") or {}).items():
        if name == "default":
            continue
        tier = sire_tier(val)
        sires.append(
            {"name": name, "score": float(val), "tier": tier, "tier_ja": SIRE_JA[tier]["short"]}
        )
    sires.sort(key=lambda x: (-x["score"], x["name"]))

    families = []
    for name, v in fo.items():
        hu = fh.get(name)
        families.append(
            {
                "name": name,
                "overall_grade": v.get("grade"),
                "overall_score": v.get("score"),
                "overall_rank": v.get("rank"),
                "n_horses": v.get("n_horses"),
                "win_rate_sm": v.get("win_rate_sm"),
                "hiroo_unique": bool(v.get("hiroo_unique")),
                "hiroo_family_grade": v.get("hiroo_family_grade"),
                "hiroo_family_rank": v.get("hiroo_family_rank"),
                "hiroo_only_grade": (hu or {}).get("grade"),
                "hiroo_only_score": (hu or {}).get("score"),
            }
        )
    families.sort(
        key=lambda f: (order.get(f["overall_grade"], 9), -(f.get("overall_score") or 0), f["name"])
    )

    crosses = []
    for key, v in cx.items():
        t, f = key.split("|", 1)
        crosses.append(
            {
                "key": key,
                "trainer": t,
                "family": f,
                "grade": v.get("grade"),
                "score": v.get("score"),
                "n_horses": v.get("n_horses"),
                "win_rate_sm": v.get("win_rate_sm"),
                "rank": v.get("rank"),
            }
        )
    crosses.sort(key=lambda c: (order.get(c["grade"], 9), -(c.get("score") or 0), c["key"]))

    weight = {
        "canonical": {
            "alert_kg": rules["kinjou"]["weight_light_alert_kg"],
            "scorer_delta": rules["kinjou"]["weight_light_delta"],
            "checklist_pts": check["points"]["kinjou"]["light_weight"],
            "note": "正本ルールは一律。420kg以下で軽量アラート。",
        },
        "base_band": {
            "ok_min": 430,
            "ok_max": 500,
            "watch_low": 420,
            "watch_high": 520,
            "label": "標準目安帯",
        },
        "profiles": [
            {
                "id": "turf_mile_filly",
                "title": "芝マイル〜中距離・牝寄り",
                "trainers": ["須貝尚介", "友道康夫", "池江泰寿"],
                "sires_hint": ["ロードカナロア", "エピファネイア", "サートゥルナーリア"],
                "ok_min": 415,
                "ok_max": 480,
                "note": "細身・軽めでも適性が一致すれば運用上許容しやすい。ただし採点上は≤420で軽量アラートが付く。",
            },
            {
                "id": "ceiling_power",
                "title": "天井型・パワー厩舎",
                "trainers": ["矢作芳人", "藤原英昭", "高柳瑞樹"],
                "sires_hint": ["キタサンブラック", "コントレイル", "ドゥラメンテ"],
                "ok_min": 440,
                "ok_max": 510,
                "note": "増体・パワーを評価しやすい帯。極端な軽量は適性不一致を疑う。",
            },
            {
                "id": "dirt_or_heavy",
                "title": "ダート／パワー父寄り",
                "trainers": ["黒岩陽一", "荒川義之", "武英智"],
                "sires_hint": ["マインドユアビスケッツ", "イスラボナータ", "ホッコータルマエ"],
                "ok_min": 450,
                "ok_max": 530,
                "note": "軽い仕上がりは適性ズレ警戒。正本減点に加え運用でも要注意。",
            },
            {
                "id": "default",
                "title": "標準（上記以外）",
                "trainers": [],
                "sires_hint": [],
                "ok_min": 430,
                "ok_max": 500,
                "note": "正本の警戒線420を下限ウォッチに、標準帯で見る。",
            },
        ],
        "integration_rules": [
            "採点（点数）に効くのは正本の一律ルールのみ：体重≤420 → 軽量アラート（checklist −1 / scorer −0.3）。",
            "プロファイル帯は運用ガイド。厩舎・父・牝系の「型」が近いプロファイルを優先して参照する。",
            "複数プロファイルが競合する場合は「より狭いOK帯」と「軽い方の警戒」を採用（保守統合）。",
            "性・距離適性が厩舎得手と一致している場合、軽量でも即PASSにはしない（減点のみ）。",
            "骨折・跛行・手術・予後不良は体重帯と無関係に即PASS。",
        ],
    }

    family_aliases = [
        {
            "alias": "ディメンシオン",
            "maps_to": None,
            "note": "ランクJSON未収録。看板Stitching系の深層として扱った実績あり（signature参照）。",
            "suggest_signature": "Stitching",
            "manual_unique": "S",
        },
        {
            "alias": "ステラリード",
            "maps_to": None,
            "note": "ランクJSON未収録。運用上ウェルシュステラ系と並ぶ優先牝系。",
            "suggest_signature": None,
            "manual_unique": "S",
        },
        {
            "alias": "ミスペンバリー",
            "maps_to": None,
            "note": "ランクJSON未収録。優先牝系S扱い（運用）。",
            "manual_unique": "S",
        },
    ]

    data = {
        "meta": {
            "version": check.get("meta", {}).get("version"),
            "generated_for": "cloud_model smartphone sheet+tool",
            "ranks_generated_at": ranks.get("generated_at"),
            "definition": ranks.get("definition"),
            "disclaimer": "意思決定支援であり的中保証ではない。",
            "grade_ja": GRADE_JA,
            "sire_ja": SIRE_JA,
            "buy_points": check.get("points"),
            "verdict": check.get("verdict"),
            "hard_pass": check.get("hard_pass"),
            "combo_rules": check.get("combo_rules"),
            "pocket_card": check.get("pocket_card"),
            "instant_checklist": check.get("instant_checklist"),
            "catalog_url": (rules.get("meta") or {}).get("catalog_url"),
        },
        "trainers": trainers,
        "sires": sires,
        "sire_default": float((rules.get("sires") or {}).get("default", 2.0)),
        "families": families,
        "hiroo_unique_families": ranks.get("hiroo_unique_families") or [],
        "crosses": crosses,
        "weight": weight,
        "family_aliases": family_aliases,
        "points_trainer": check["points"]["trainer_hiroo"],
        "points_family_overall": check["points"]["family_overall"],
        "points_hiroo_unique": check["points"]["hiroo_unique"],
        "points_cross": check["points"]["cross"],
        "points_sire": check["points"]["sire_tier"],
        "points_signature": check["points"]["signature_line"],
        "points_price": check["points"]["price_man_yen"],
        "points_kinjou": check["points"]["kinjou"],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "window.CLUB_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
