#!/usr/bin/env python3
"""Flag / remove corrupt mirror rows before predictive tests.

RENBAN Numbers3 history contains multi-day identical winning-number streaks
(e.g. 458 x10) that are incompatible with an independent draw process and
inflate naive 'repeat previous' backtests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def clean_numbers3(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = df.copy()
    df["number"] = df["number"].astype(str).str.zfill(3)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("draw_no").reset_index(drop=True)

    # streak id / length
    change = df["number"].ne(df["number"].shift())
    streak_id = change.cumsum()
    streak_len = streak_id.map(streak_id.value_counts())
    df["streak_id"] = streak_id
    df["streak_len"] = streak_len.astype(int)
    df["is_streak_continuation"] = df["number"].eq(df["number"].shift()).fillna(False)
    df["suspect_long_streak"] = df["streak_len"] >= 3
    df["dup_date"] = df["date"].duplicated(keep=False)

    # Drop only long-streak contamination (len>=3 entire group).
    # Keep length-2 adjacent repeats — those can occur under H0 (~0.1%/draw).
    long_ids = set(df.loc[df["suspect_long_streak"], "streak_id"])
    cleaned = df.loc[~df["streak_id"].isin(long_ids)].copy()

    # Adjacent identical number WITH identical payout fields => duplicated mirror row.
    same_num = cleaned["number"].eq(cleaned["number"].shift())
    same_prize = cleaned["straight_prize_yen"].eq(cleaned["straight_prize_yen"].shift())
    same_winners = cleaned["straight_winners"].eq(cleaned["straight_winners"].shift())
    # If winners are both NaN, fall back to identical prize only.
    both_winners_na = (
        cleaned["straight_winners"].isna() & cleaned["straight_winners"].shift().isna()
    )
    dup_mirror = same_num & same_prize & (same_winners | both_winners_na)
    n_dup_mirror = int(dup_mirror.sum())
    cleaned = cleaned.loc[~dup_mirror].copy()

    # Prefer unique dates: keep first draw_no on duplicated dates
    cleaned = cleaned.drop_duplicates(subset=["date"], keep="first")

    report = {
        "raw_rows": int(len(df)),
        "cleaned_rows": int(len(cleaned)),
        "dropped_streak_continuations_note": (
            "Length-2 repeats retained unless payout fields are identical "
            "(mirror duplicate). Streaks with length>=3 removed entirely."
        ),
        "long_streak_groups_removed": int(len(long_ids)),
        "long_streak_rows_removed": int(df["suspect_long_streak"].sum()),
        "duplicate_mirror_rows_removed": n_dup_mirror,
        "duplicate_date_rows_raw": int(df["dup_date"].sum()),
        "long_streaks": [
            {
                "number": str(g["number"].iloc[0]),
                "len": int(len(g)),
                "draw_from": int(g["draw_no"].iloc[0]),
                "draw_to": int(g["draw_no"].iloc[-1]),
                "date_from": str(g["date"].iloc[0].date()),
                "date_to": str(g["date"].iloc[-1].date()),
            }
            for _, g in df[df["suspect_long_streak"]].groupby("streak_id")
        ],
    }
    return cleaned.drop(
        columns=[
            "streak_id",
            "streak_len",
            "is_streak_continuation",
            "suspect_long_streak",
            "dup_date",
        ]
    ), report


def main() -> None:
    raw = pd.read_csv(DATA / "numbers3_draws.csv")
    cleaned, report = clean_numbers3(raw)
    cleaned.to_csv(DATA / "numbers3_draws_clean.csv", index=False)
    # quality flags on full raw
    raw_q = raw.copy()
    raw_q["number"] = raw_q["number"].astype(str).str.zfill(3)
    change = raw_q["number"].ne(raw_q["number"].shift())
    sid = change.cumsum()
    slen = sid.map(sid.value_counts())
    raw_q["streak_len"] = slen.astype(int)
    raw_q["suspect_long_streak"] = raw_q["streak_len"] >= 3
    raw_q.to_csv(DATA / "numbers3_draws_with_quality_flags.csv", index=False)
    (DATA / "numbers3_data_quality.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
