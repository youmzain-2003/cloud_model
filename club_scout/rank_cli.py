# -*- coding: utf-8 -*-
"""CLI: 相対ランキング表示（Streamlitなしでも確認可）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scorer import load_rules, rank_candidates
from store import load_candidates


def main() -> None:
    p = argparse.ArgumentParser(description="Club Scout rank CLI")
    p.add_argument("--pool", default=None, help="比較プール名")
    p.add_argument("--all-status", action="store_true", help="満口なども含める")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    rules = load_rules()
    cands = load_candidates().get("candidates") or []
    ranked = rank_candidates(
        cands, rules, pool=args.pool, only_eligible=not args.all_status
    )
    if args.json:
        print(json.dumps(ranked, ensure_ascii=False, indent=2))
        return
    if not ranked:
        print("候補なし")
        return
    print(f"{'rank':>4}  {'label':<6}  {'total':>5}  name")
    for r in ranked:
        print(
            f"{r.get('rank'):>4}  {str(r.get('label')):<6}  {r.get('total'):>5}  "
            f"{r.get('name')}  [{r.get('trainer')}/{r.get('sire')}]  {r.get('recommend_units')}"
        )


if __name__ == "__main__":
    main()
