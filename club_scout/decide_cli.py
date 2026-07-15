# -*- coding: utf-8 -*-
"""カタログ項目から GO/HOLD/PASS を出すCLI。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decision import decide, pocket_card_text


def main() -> None:
    p = argparse.ArgumentParser(description="Club Scout buy decision")
    p.add_argument("--card", action="store_true", help="ポケットカード表示")
    p.add_argument("--name", default="")
    p.add_argument("--dam", default="", help="カタログの母名")
    p.add_argument("--family-mare", default="", help="母母名が分かっている場合")
    p.add_argument("--signature", default="", help="看板牝系（母母母など）")
    p.add_argument("--trainer", required=False, default="")
    p.add_argument("--sire", default="")
    p.add_argument("--price", type=float, default=0.0)
    p.add_argument("--status", default="募集中")
    p.add_argument("--kinjou", default="")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    if args.card:
        print(pocket_card_text())
        return

    cand = {
        "name": args.name,
        "dam": args.dam,
        "family_mare": args.family_mare,
        "signature_line": args.signature,
        "trainer": args.trainer,
        "sire": args.sire,
        "price_man_yen": args.price,
        "status": args.status,
        "kinjou_latest": args.kinjou,
    }
    out = decide(cand)
    if args.json:
        # scoredが大きいので要約
        slim = {k: v for k, v in out.items() if k != "scored"}
        slim["score_total"] = (out.get("scored") or {}).get("total")
        print(json.dumps(slim, ensure_ascii=False, indent=2))
        return

    print(f"判定: {out['verdict']} ({out['label']})  ポイント={out['points']}")
    print(out["meaning"])
    if out.get("hard_pass_reason"):
        print("即PASS理由:", out["hard_pass_reason"])
    if out.get("resolved"):
        print("母→母母解決:", out["resolved"])
    print("family_mare:", out.get("family_mare"), " signature:", out.get("signature_line"))
    for d in out.get("detail") or []:
        print(f"  {d['item']}: {d['pts']:+d}  ({d.get('note')})")
    for h in out.get("combo_hints") or []:
        print("!", h)


if __name__ == "__main__":
    main()
