#!/usr/bin/env python3
"""Numbers3 prediction hypotheses + ¥1000/day hit-frequency portfolio.

Goal framing (user):
  - Pursue hits as the objective (not payout-conditioning).
  - Want roughly one hit every 2–3 draws among straight/box/set/mini.
  - Daily budget = 1000 yen (5 x 200-yen units).

Scientific gate (proposals 1–3):
  1. Every candidate law is a prediction hypothesis H1.
  2. Validate only with walk-forward / holdout (no peeking).
  3. Promote to an "axis" only if it beats the null on a pre-registered metric.
"""

from __future__ import annotations

import itertools
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORTS = ROOT / "reports"

STAKE = 200
BUDGET = 1000
N_UNITS = BUDGET // STAKE  # 5

# Theoretical prizes (yen per 200-yen unit) — for EV notes only.
PRIZE = {
    "straight": 90_000,
    "box_6": 15_000,
    "box_3": 30_000,
    "set_straight": 52_500,
    "set_box_6": 7_500,  # when all-diff; set covers 5 remaining perms at half
    "mini": 9_000,
}


@dataclass
class HypothesisResult:
    name: str
    description: str
    metric: str
    null_value: float
    observed_value: float
    lift: float
    p_value: float | None
    n_eval: int
    promoted_to_axis: bool
    reason: str
    details: dict = field(default_factory=dict)


def load_n3() -> pd.DataFrame:
    df = pd.read_csv(DATA / "numbers3_draws_clean.csv")
    df["date"] = pd.to_datetime(df["date"])
    df["number"] = df["number"].astype(str).str.zfill(3)
    df["d100"] = df["number"].str[0].astype(int)
    df["d10"] = df["number"].str[1].astype(int)
    df["d1"] = df["number"].str[2].astype(int)
    df["last2"] = df["number"].str[1:]
    return df.sort_values("draw_no").reset_index(drop=True)


def box_type(num: str) -> str:
    c = len(set(str(num).zfill(3)))
    if c == 1:
        return "triple"
    if c == 2:
        return "double"
    return "all_diff"


def covers_straight(pick: str, win: str) -> bool:
    return pick == win


def covers_box(pick: str, win: str) -> bool:
    return Counter(pick) == Counter(win) and pick != win or pick == win
    # box wins on any permutation including exact


def covers_box_only_perm(pick: str, win: str) -> bool:
    return Counter(pick) == Counter(win)


def covers_mini(pick_last2: str, win: str) -> bool:
    return win[1:] == pick_last2


def covers_set(pick: str, win: str) -> bool:
    # set wins if straight or box (any perm of pick)
    return Counter(pick) == Counter(win)


# ---------------------------------------------------------------------------
# Budget / frequency math (null, no prediction edge)
# ---------------------------------------------------------------------------

def null_portfolio_math() -> dict:
    """What hit rates are possible with 5 units under IID uniform."""
    # Mini: each unit covers 1 distinct last-2 → +1/100 if unique
    p_one_mini = 1 / 100
    p_k_minis = [1 - (1 - p_one_mini) ** k for k in range(0, 6)]  # if disjoint last2
    # Actually for disjoint last2 on same draw: P(union)=k/100 exactly
    p_k_minis_exact = [k / 100 for k in range(0, 6)]

    # Box all-diff: covers 6 numbers / 1000
    p_one_box6 = 6 / 1000
    # Straight
    p_one_straight = 1 / 1000
    # Set all-diff: covers 6/1000 (same coverage as box+straight combined on that multiset)
    p_one_set6 = 6 / 1000

    plans = []
    # Pure 5 minis (5 distinct last2)
    plans.append(
        {
            "plan": "5x mini (distinct last2)",
            "units": {"mini": 5},
            "p_any_hit": 5 / 100,
            "expected_draws_between_hits": 100 / 5,
            "meets_every_2_3_draws": False,
            "note": "Best pure frequency under ¥1000; still only 5%/day.",
        }
    )
    # 4 mini + 1 box
    # approx if last2 of box doesn't overlap mini covers — upper bound messy; simulate later
    plans.append(
        {
            "plan": "4x mini + 1x box6",
            "units": {"mini": 4, "box": 1},
            "p_any_hit_approx": 1 - (1 - 4 / 100) * (1 - 6 / 1000),
            "expected_draws_between_hits_approx": 1
            / (1 - (1 - 4 / 100) * (1 - 6 / 1000)),
            "meets_every_2_3_draws": False,
        }
    )
    plans.append(
        {
            "plan": "3x mini + 1x box6 + 1x straight",
            "units": {"mini": 3, "box": 1, "straight": 1},
            "p_any_hit_approx": 1
            - (1 - 3 / 100) * (1 - 6 / 1000) * (1 - 1 / 1000),
            "meets_every_2_3_draws": False,
        }
    )
    plans.append(
        {
            "plan": "2x mini + 2x box6 + 1x set",
            "units": {"mini": 2, "box": 2, "set": 1},
            "p_any_hit_approx": 1
            - (1 - 2 / 100) * (1 - 6 / 1000) ** 2 * (1 - 6 / 1000),
            "meets_every_2_3_draws": False,
            "note": "Coverage overlaps possible; approx treats independent.",
        }
    )
    plans.append(
        {
            "plan": "1x mini only (reference)",
            "units": {"mini": 1},
            "p_any_hit": 1 / 100,
            "expected_draws_between_hits": 100,
            "meets_every_2_3_draws": False,
        }
    )

    # How many mini units needed for every 2 or 3 draws?
    need = {
        "for_p_1_over_2": {"target_p": 0.5, "minis_needed_disjoint": 50, "yen": 50 * 200},
        "for_p_1_over_3": {"target_p": 1 / 3, "minis_needed_disjoint": 34, "yen": 34 * 200},
        "budget_1000_max_p_with_minis": 5 / 100,
        "budget_1000_expected_gap_days": 20.0,
    }
    return {
        "stake_yen": STAKE,
        "budget_yen": BUDGET,
        "units_per_day": N_UNITS,
        "bet_type_null_p": {
            "straight": 1 / 1000,
            "box_all_diff": 6 / 1000,
            "box_double": 3 / 1000,
            "set_all_diff_coverage": 6 / 1000,
            "mini_last2": 1 / 100,
        },
        "theory_prize_yen": PRIZE,
        "plans": plans,
        "frequency_requirement": need,
        "verdict": (
            "With ¥1000/day (5 units), even an all-mini distinct-last2 book only reaches "
            "P(hit)≈5%/draw (about once per 20 draws). Hitting every 2–3 draws needs "
            "roughly ¥6800–¥10000/day in mini coverage under null odds — not ¥1000. "
            "Prediction edge is required to beat that ceiling; hypotheses must be proven."
        ),
    }


# ---------------------------------------------------------------------------
# Prediction hypotheses (walk-forward)
# ---------------------------------------------------------------------------

def _binom_pvalue(hits: int, n: int, p0: float) -> float:
    if n <= 0:
        return float("nan")
    return float(stats.binomtest(hits, n, p0, alternative="greater").pvalue)


def hyp_repeat_last2(df: pd.DataFrame, start: int) -> HypothesisResult:
    """H1: tomorrow's last2 equals today's last2 more often than 1/100."""
    hits = 0
    n = 0
    for i in range(start, len(df)):
        n += 1
        if df.loc[i, "last2"] == df.loc[i - 1, "last2"]:
            hits += 1
    rate = hits / n
    p0 = 0.01
    p = _binom_pvalue(hits, n, p0)
    ok = rate > p0 and p < 0.01
    return HypothesisResult(
        name="repeat_prev_last2",
        description="前回の下2桁が再出現する",
        metric="last2_repeat_rate",
        null_value=p0,
        observed_value=rate,
        lift=rate - p0,
        p_value=p,
        n_eval=n,
        promoted_to_axis=ok,
        reason="promote if holdout repeat rate >> 1/100 with p<0.01",
        details={"hits": hits},
    )


def hyp_hot_last2(df: pd.DataFrame, start: int, window: int = 50) -> HypothesisResult:
    """H1: picking the hottest last2 in last W beats 1/100."""
    hits = 0
    n = 0
    for i in range(max(start, window), len(df)):
        hist = df.loc[i - window : i - 1, "last2"]
        hot = Counter(hist).most_common(1)[0][0]
        n += 1
        if df.loc[i, "last2"] == hot:
            hits += 1
    rate = hits / n if n else float("nan")
    p0 = 0.01
    p = _binom_pvalue(hits, n, p0)
    ok = rate > p0 * 1.5 and p < 0.01
    return HypothesisResult(
        name=f"hot_last2_W{window}",
        description=f"直近{window}回で最多の下2桁を1口ミニ",
        metric="mini_hit_rate",
        null_value=p0,
        observed_value=rate,
        lift=rate - p0,
        p_value=p,
        n_eval=n,
        promoted_to_axis=ok,
        reason="promote if mini hit-rate >= 1.5/100 and p<0.01",
        details={"hits": hits, "window": window},
    )


def hyp_cold_last2(df: pd.DataFrame, start: int, window: int = 50) -> HypothesisResult:
    hits = 0
    n = 0
    for i in range(max(start, window), len(df)):
        hist = df.loc[i - window : i - 1, "last2"]
        cold = Counter(hist).most_common()[-1][0]
        n += 1
        if df.loc[i, "last2"] == cold:
            hits += 1
    rate = hits / n if n else float("nan")
    p0 = 0.01
    p = _binom_pvalue(hits, n, p0)
    ok = rate > p0 * 1.5 and p < 0.01
    return HypothesisResult(
        name=f"cold_last2_W{window}",
        description=f"直近{window}回で最少の下2桁を1口ミニ",
        metric="mini_hit_rate",
        null_value=p0,
        observed_value=rate,
        lift=rate - p0,
        p_value=p,
        n_eval=n,
        promoted_to_axis=ok,
        reason="promote if mini hit-rate >= 1.5/100 and p<0.01",
        details={"hits": hits},
    )


def hyp_slide_last2(df: pd.DataFrame, start: int) -> HypothesisResult:
    """H1: last2 = prev_last2 + 1 (mod on each digit) beats 1/100."""
    hits = 0
    n = 0
    for i in range(start, len(df)):
        prev = df.loc[i - 1, "last2"]
        cand = f"{(int(prev[0]) + 1) % 10}{(int(prev[1]) + 1) % 10}"
        n += 1
        if df.loc[i, "last2"] == cand:
            hits += 1
    rate = hits / n
    p0 = 0.01
    p = _binom_pvalue(hits, n, p0)
    ok = rate > p0 * 1.5 and p < 0.01
    return HypothesisResult(
        name="slide_plus1_last2",
        description="前回下2桁の各桁+1をミニ",
        metric="mini_hit_rate",
        null_value=p0,
        observed_value=rate,
        lift=rate - p0,
        p_value=p,
        n_eval=n,
        promoted_to_axis=ok,
        reason="promote if mini hit-rate >= 1.5/100 and p<0.01",
        details={"hits": hits},
    )


def hyp_hot_digits_straight(df: pd.DataFrame, start: int, window: int = 50) -> HypothesisResult:
    """H1: modal digit per position as straight beats 1/1000."""
    hits = 0
    n = 0
    for i in range(max(start, window), len(df)):
        w = df.loc[i - window : i - 1]
        h = Counter(w["d100"]).most_common(1)[0][0]
        t = Counter(w["d10"]).most_common(1)[0][0]
        o = Counter(w["d1"]).most_common(1)[0][0]
        pick = f"{h}{t}{o}"
        n += 1
        if df.loc[i, "number"] == pick:
            hits += 1
    rate = hits / n if n else float("nan")
    p0 = 0.001
    p = _binom_pvalue(hits, n, p0)
    ok = rate > p0 * 2 and p < 0.01
    return HypothesisResult(
        name=f"hot_digits_straight_W{window}",
        description=f"位置別最頻桁のストレート",
        metric="straight_hit_rate",
        null_value=p0,
        observed_value=rate,
        lift=rate - p0,
        p_value=p,
        n_eval=n,
        promoted_to_axis=ok,
        reason="promote if straight hit-rate >= 2/1000 and p<0.01",
        details={"hits": hits},
    )


def hyp_hot_digits_box(df: pd.DataFrame, start: int, window: int = 50) -> HypothesisResult:
    """H1: modal digits as box (multiset) beats box null (~6/1000 if all-diff)."""
    hits = 0
    n = 0
    null_sum = 0.0
    for i in range(max(start, window), len(df)):
        w = df.loc[i - window : i - 1]
        h = Counter(w["d100"]).most_common(1)[0][0]
        t = Counter(w["d10"]).most_common(1)[0][0]
        o = Counter(w["d1"]).most_common(1)[0][0]
        pick = f"{h}{t}{o}"
        bt = box_type(pick)
        p0 = { "all_diff": 6 / 1000, "double": 3 / 1000, "triple": 0.0 }[bt]
        null_sum += p0
        n += 1
        if Counter(pick) == Counter(df.loc[i, "number"]) and bt != "triple":
            hits += 1
    rate = hits / n if n else float("nan")
    p0 = null_sum / n if n else float("nan")
    # conservative binomial vs 6/1000
    p = _binom_pvalue(hits, n, 6 / 1000)
    ok = rate > (6 / 1000) * 1.5 and p < 0.01
    return HypothesisResult(
        name=f"hot_digits_box_W{window}",
        description="位置別最頻桁のボックス",
        metric="box_hit_rate",
        null_value=6 / 1000,
        observed_value=rate,
        lift=rate - 6 / 1000,
        p_value=p,
        n_eval=n,
        promoted_to_axis=ok,
        reason="promote if box hit-rate >= 9/1000 and p<0.01 vs 6/1000",
        details={"hits": hits, "avg_conditional_null": p0},
    )


def hyp_markov_digit(df: pd.DataFrame, start: int, window: int = 300) -> HypothesisResult:
    """H1: next hundreds digit = argmax P(h_t | h_{t-1}) from last W beats 1/10."""
    hits = 0
    n = 0
    for i in range(max(start, window), len(df) - 0):
        if i + 0 >= len(df):
            break
        # predict df[i].d100 from transitions in [i-W, i)
        prev_digit = df.loc[i - 1, "d100"]
        hist_prev = df.loc[i - window : i - 2, "d100"].values
        hist_next = df.loc[i - window + 1 : i - 1, "d100"].values
        mask = hist_prev == prev_digit
        if mask.sum() < 5:
            pred = Counter(hist_next).most_common(1)[0][0]
        else:
            pred = Counter(hist_next[mask]).most_common(1)[0][0]
        n += 1
        if df.loc[i, "d100"] == pred:
            hits += 1
    rate = hits / n if n else float("nan")
    p0 = 0.1
    p = _binom_pvalue(hits, n, p0)
    ok = rate > 0.12 and p < 0.01
    return HypothesisResult(
        name=f"markov_d100_W{window}",
        description="百の位の1次マルコフ最頻遷移",
        metric="digit_hit_rate",
        null_value=p0,
        observed_value=rate,
        lift=rate - p0,
        p_value=p,
        n_eval=n,
        promoted_to_axis=ok,
        reason="promote if digit accuracy >= 12% with p<0.01",
        details={"hits": hits},
    )


def hyp_weekday_last2_mode(df: pd.DataFrame, start: int) -> HypothesisResult:
    """H1: historical mode last2 for this weekday beats 1/100."""
    df = df.copy()
    df["weekday"] = df["date"].dt.weekday
    hits = 0
    n = 0
    for i in range(start, len(df)):
        wd = df.loc[i, "weekday"]
        hist = df.loc[: i - 1]
        hist = hist[hist["weekday"] == wd]
        if len(hist) < 30:
            continue
        mode = Counter(hist["last2"]).most_common(1)[0][0]
        n += 1
        if df.loc[i, "last2"] == mode:
            hits += 1
    rate = hits / n if n else float("nan")
    p0 = 0.01
    p = _binom_pvalue(hits, n, p0)
    ok = rate > p0 * 1.5 and p < 0.01
    return HypothesisResult(
        name="weekday_mode_last2",
        description="同曜日の過去最頻下2桁をミニ",
        metric="mini_hit_rate",
        null_value=p0,
        observed_value=rate,
        lift=rate - p0,
        p_value=p,
        n_eval=n,
        promoted_to_axis=ok,
        reason="promote if mini hit-rate >= 1.5/100 and p<0.01",
        details={"hits": hits},
    )


def run_hypotheses(df: pd.DataFrame) -> list[HypothesisResult]:
    start = int(len(df) * 0.6)  # holdout last 40%
    results = [
        hyp_repeat_last2(df, start),
        hyp_hot_last2(df, start, 30),
        hyp_hot_last2(df, start, 50),
        hyp_hot_last2(df, start, 100),
        hyp_cold_last2(df, start, 50),
        hyp_slide_last2(df, start),
        hyp_hot_digits_straight(df, start, 50),
        hyp_hot_digits_box(df, start, 50),
        hyp_markov_digit(df, start, 300),
        hyp_weekday_last2_mode(df, start),
    ]
    return results


# ---------------------------------------------------------------------------
# Portfolio simulation on holdout (prediction-guided vs null coverage)
# ---------------------------------------------------------------------------

def simulate_portfolios(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Walk-forward daily books under ¥1000, score any-hit and yen."""
    start = int(len(df) * 0.6)
    window = 50
    rows = []

    for i in range(max(start, window), len(df)):
        win = df.loc[i, "number"]
        win_l2 = df.loc[i, "last2"]
        hist = df.loc[i - window : i - 1]
        # candidate generators
        last2_counts = Counter(hist["last2"])
        hot_l2 = [x for x, _ in last2_counts.most_common(10)]
        cold_l2 = [x for x, _ in last2_counts.most_common()][-10:]
        # ensure 100 length pool of all last2
        all_l2 = [f"{a}{b}" for a in range(10) for b in range(10)]
        # unseen in window first
        unseen = [x for x in all_l2 if last2_counts[x] == 0]
        rng = np.random.default_rng(df.loc[i, "draw_no"])

        def pick_minis(pool: list[str], k: int) -> list[str]:
            out = []
            for x in pool:
                if x not in out:
                    out.append(x)
                if len(out) >= k:
                    break
            while len(out) < k:
                cand = all_l2[int(rng.integers(0, 100))]
                if cand not in out:
                    out.append(cand)
            return out[:k]

        prev = df.loc[i - 1, "number"]
        prev_l2 = df.loc[i - 1, "last2"]
        slide_l2 = f"{(int(prev_l2[0])+1)%10}{(int(prev_l2[1])+1)%10}"
        hot_digits = (
            f"{Counter(hist['d100']).most_common(1)[0][0]}"
            f"{Counter(hist['d10']).most_common(1)[0][0]}"
            f"{Counter(hist['d1']).most_common(1)[0][0]}"
        )
        if box_type(hot_digits) == "triple":
            hot_digits = prev if box_type(prev) != "triple" else f"{prev[0]}{(int(prev[1])+1)%10}{prev[2]}"
            if box_type(hot_digits) == "triple":
                hot_digits = f"{hot_digits[0]}{hot_digits[1]}{(int(hot_digits[2])+1)%10}"

        books = {
            "A_5mini_hot": {
                "mini": pick_minis(hot_l2, 5),
                "box": [],
                "straight": [],
                "set": [],
            },
            "B_5mini_unseen": {
                "mini": pick_minis(unseen + cold_l2 + all_l2, 5),
                "box": [],
                "straight": [],
                "set": [],
            },
            "C_4mini_1box_hot": {
                "mini": pick_minis(hot_l2, 4),
                "box": [hot_digits],
                "straight": [],
                "set": [],
            },
            "D_3mini_1box_1straight": {
                "mini": pick_minis(hot_l2, 3),
                "box": [hot_digits],
                "straight": [hot_digits],
                "set": [],
            },
            "E_3mini_1set_1straight_prev": {
                "mini": pick_minis([prev_l2, slide_l2] + hot_l2, 3),
                "box": [],
                "straight": [prev],
                "set": [hot_digits],
            },
            "F_5mini_random": {
                "mini": pick_minis(list(rng.permutation(all_l2)), 5),
                "box": [],
                "straight": [],
                "set": [],
            },
        }

        for name, book in books.items():
            units = (
                len(book["mini"])
                + len(book["box"])
                + len(book["straight"])
                + len(book["set"])
            )
            assert units == N_UNITS, (name, units, book)
            hit_types = []
            won = 0.0
            for m in book["mini"]:
                if covers_mini(m, win):
                    hit_types.append("mini")
                    won += PRIZE["mini"]
            for b in book["box"]:
                if covers_box_only_perm(b, win) and box_type(b) != "triple":
                    hit_types.append("box")
                    won += PRIZE["box_3" if box_type(b) == "double" else "box_6"]
            for s in book["straight"]:
                if covers_straight(s, win):
                    hit_types.append("straight")
                    won += PRIZE["straight"]
            for s in book["set"]:
                if covers_set(s, win):
                    if s == win:
                        hit_types.append("set_straight")
                        won += PRIZE["set_straight"]
                    else:
                        hit_types.append("set_box")
                        won += PRIZE["set_box_6"] if box_type(s) == "all_diff" else 15_000

            rows.append(
                {
                    "draw_no": int(df.loc[i, "draw_no"]),
                    "date": str(df.loc[i, "date"].date()),
                    "plan": name,
                    "any_hit": int(len(hit_types) > 0),
                    "hit_types": ",".join(hit_types) if hit_types else "",
                    "spent": BUDGET,
                    "won_theory": won,
                    "roi_theory": won / BUDGET - 1,
                }
            )

    detail = pd.DataFrame(rows)
    summary = (
        detail.groupby("plan", as_index=False)
        .agg(
            draws=("draw_no", "count"),
            hits=("any_hit", "sum"),
            hit_rate=("any_hit", "mean"),
            avg_gap=("any_hit", lambda s: (1 / s.mean()) if s.mean() > 0 else float("inf")),
            total_spent=("spent", "sum"),
            total_won_theory=("won_theory", "sum"),
        )
    )
    summary["roi_theory"] = summary["total_won_theory"] / summary["total_spent"] - 1
    summary["target_hit_rate_every_2"] = 0.5
    summary["target_hit_rate_every_3"] = 1 / 3
    summary["meets_every_2"] = summary["hit_rate"] >= 0.5
    summary["meets_every_3"] = summary["hit_rate"] >= 1 / 3
    # null reference for 5 distinct minis
    summary["null_5mini_hit_rate"] = 0.05
    return detail, summary.sort_values("hit_rate", ascending=False)


def next_day_suggestions(df: pd.DataFrame) -> dict:
    """Emit tomorrow's ¥1000 book from best frequency plan + axis status."""
    window = 50
    hist = df.tail(window)
    last2_counts = Counter(hist["last2"])
    hot_l2 = [x for x, _ in last2_counts.most_common(20)]
    all_l2 = [f"{a}{b}" for a in range(10) for b in range(10)]
    unseen = [x for x in all_l2 if last2_counts[x] == 0]
    prev = df.iloc[-1]
    hot_digits = (
        f"{Counter(hist['d100']).most_common(1)[0][0]}"
        f"{Counter(hist['d10']).most_common(1)[0][0]}"
        f"{Counter(hist['d1']).most_common(1)[0][0]}"
    )
    return {
        "as_of_draw": int(prev["draw_no"]),
        "as_of_date": str(prev["date"].date()),
        "prev_number": prev["number"],
        "recommended_plan": "B_5mini_unseen_or_A_5mini_hot",
        "budget_yen": BUDGET,
        "books": {
            "frequency_max_5mini_hot": {
                "mini_last2": hot_l2[:5],
                "expected_null_p_hit": 0.05,
                "comment": "頻度最大化の基本形。予想軸が無いときの上限付近。",
            },
            "frequency_max_5mini_unseen": {
                "mini_last2": (unseen + hot_l2)[:5],
                "expected_null_p_hit": 0.05,
                "comment": "窓内未出現の下2桁優先（コールド寄り）。",
            },
            "hybrid_3mini_1box_1straight": {
                "mini_last2": hot_l2[:3],
                "box": hot_digits,
                "straight": hot_digits,
                "expected_null_p_hit_approx": 1
                - (1 - 0.03) * (1 - 6 / 1000) * (1 - 1 / 1000),
                "comment": "頻度を少し犠牲にしてボックス/ストレートの上振れを残す。",
            },
        },
    }


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    df = load_n3()
    budget_math = null_portfolio_math()
    hyps = run_hypotheses(df)
    detail, summary = simulate_portfolios(df)
    sugg = next_day_suggestions(df)

    hyp_df = pd.DataFrame([asdict(h) for h in hyps])
    # details dict -> json string for csv
    hyp_df["details"] = hyp_df["details"].apply(lambda d: json.dumps(d, ensure_ascii=False))
    hyp_df.to_csv(REPORTS / "n3_prediction_hypotheses.csv", index=False)
    detail.to_csv(REPORTS / "n3_budget1000_portfolio_detail.csv", index=False)
    summary.to_csv(REPORTS / "n3_budget1000_portfolio_summary.csv", index=False)

    axes = [h for h in hyps if h.promoted_to_axis]
    out = {
        "goal": {
            "pursue_hits": True,
            "desired_frequency": "one hit every 2–3 draws among straight/box/set/mini",
            "budget_yen_per_day": BUDGET,
            "units": N_UNITS,
        },
        "budget_math": budget_math,
        "hypotheses": [asdict(h) for h in hyps],
        "axes_promoted": [asdict(h) for h in axes],
        "portfolio_summary": summary.to_dict(orient="records"),
        "next_suggestions": sugg,
        "conclusion": {
            "frequency_target_with_1000_yen": False,
            "best_null_hit_rate_approx": 0.05,
            "best_holdout_plan": summary.iloc[0].to_dict() if len(summary) else None,
            "prediction_axes_found": len(axes),
            "message": (
                "予想の正解は『的中を追い求めること』で一致。"
                "ただし¥1000ではタイプ組合せだけでは2–3回に1回に届かない。"
                "届かせるには予想エッジ（軸）が必要だが、先読み検証で軸昇格した仮説はゼロ。"
                "運用は当面『頻度上限の5ミニ』か『頻度+上振れのハイブリッド』で、"
                "仮説レジストリを更新し続ける。"
            ),
        },
    }
    (REPORTS / "prediction_axis_summary.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = []
    lines.append("# ナンバーズ3 予想仮説と¥1000/日ポートフォリオ")
    lines.append("")
    lines.append("## 目的")
    lines.append(
        "毎回当たる方向を追う。提案1〜3どおり、法則は予想仮説として登録し、"
        "先読み検証で残ったものだけを軸にする。"
        f"予算は毎日 {BUDGET} 円（{N_UNITS} 口×{STAKE} 円）。"
        "ストレート／ボックス／セット／ミニのいずれかが、できれば2〜3回に1回当たると嬉しい。"
    )
    lines.append("")
    lines.append("## 先に数字で折り合いをつける（予想なしの上限）")
    lines.append(
        f"- ミニ: 下2桁一致、**1/100**、理論 {PRIZE['mini']} 円"
    )
    lines.append(
        f"- ストレート: **1/1000**、理論 {PRIZE['straight']} 円／"
        f"ボックス(バラケ): **6/1000**、理論 {PRIZE['box_6']} 円"
    )
    lines.append(
        f"- ¥1000=5口のとき、下2桁を重ねず5ミニに全振りしても "
        f"**P(的中)≈5%/回（約20回に1回）**"
    )
    lines.append(
        "- **2回に1回**には下2桁を約50通りカバー ≈ **¥10,000/日**、"
        "**3回に1回**でも約34口 ≈ **¥6,800/日** が必要（帰無のまま）"
    )
    lines.append("")
    lines.append(
        f"**結論:** 予算¥1000のまま『2〜3回に1回』は、"
        f"**予想精度（エッジ）無しでは届かない**。"
        f"だから軸の先読み検証が本体になる。"
    )
    lines.append("")
    lines.append("## 予想仮説の先読み結果（ホールドアウト直近40%）")
    lines.append("| hypothesis | observed | null | lift | p | axis? |")
    lines.append("|---|---:|---:|---:|---:|:---:|")
    for h in hyps:
        pv = f"{h.p_value:.4g}" if h.p_value is not None and h.p_value == h.p_value else ""
        lines.append(
            f"| {h.name} | {h.observed_value:.5f} | {h.null_value:.5f} | "
            f"{h.lift:+.5f} | {pv} | {'YES' if h.promoted_to_axis else 'no'} |"
        )
    lines.append("")
    if axes:
        lines.append("### 昇格した軸")
        for h in axes:
            lines.append(f"- **{h.name}**: {h.description}")
    else:
        lines.append("### 昇格した軸")
        lines.append("- **なし**（登録仮説はすべて棄却）。精度要件を満たす法則は未発見。")
    lines.append("")
    lines.append("## ¥1000 ポートフォリオ（ホールドアウト）")
    lines.append(
        "的中＝その日の購入のうちどれか1つでも当たり。"
        "金額は理論値換算。"
    )
    lines.append("| plan | hit_rate | avg_gap_draws | ROI_theory | every_3? |")
    lines.append("|---|---:|---:|---:|:---:|")
    for _, r in summary.iterrows():
        lines.append(
            f"| {r['plan']} | {r['hit_rate']:.4f} | {r['avg_gap']:.1f} | "
            f"{r['roi_theory']:.3f} | {'Y' if r['meets_every_3'] else 'N'} |"
        )
    lines.append("")
    lines.append("## いまの推奨（軸が無い前提）")
    lines.append(
        "1. **頻度優先:** 5口すべてミニ、下2桁を重複させない "
        f"（期待的中率≈5%、ギャップ≈20回）"
    )
    lines.append(
        "2. **頻度+夢:** ミニ3 + ボックス1 + ストレート1 "
        "（的中率は少し下がり、当たったときの上振れを残す）"
    )
    lines.append(
        "3. 仮説レジストリを更新し、**p<0.01かつリフト条件**を満たしたら軸に昇格させて"
        "ミニ／ボックスの選び方を置き換える"
    )
    lines.append("")
    lines.append("### 直近データからの例")
    for name, book in sugg["books"].items():
        lines.append(f"- **{name}**: `{json.dumps(book, ensure_ascii=False)}`")
    lines.append("")
    lines.append("## 保存ファイル")
    lines.append("- `reports/n3_prediction_hypotheses.csv`")
    lines.append("- `reports/n3_budget1000_portfolio_summary.csv`")
    lines.append("- `reports/n3_budget1000_portfolio_detail.csv`")
    lines.append("- `reports/prediction_axis_summary.json`")
    lines.append("- `reports/PREDICTION_AXIS_REPORT.md`")
    lines.append("")
    (REPORTS / "PREDICTION_AXIS_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # pointer on main report
    main_report = REPORTS / "REPORT.md"
    if main_report.exists():
        text = main_report.read_text(encoding="utf-8")
        marker = "\n## 追記: 予想仮説と¥1000運用\n"
        addition = (
            marker
            + "的中追及に戻した続報。詳細は `PREDICTION_AXIS_REPORT.md`。\n"
            + f"- 昇格軸数: {len(axes)}\n"
            + "- ¥1000の帰無上限: 約5%/回（5ミニ）→ 2–3回に1回は予算不足\n"
            + "- ポートフォリオ要約: `n3_budget1000_portfolio_summary.csv`\n"
        )
        if marker in text:
            text = text.split(marker)[0].rstrip() + "\n" + addition
        else:
            text = text.rstrip() + "\n" + addition
        main_report.write_text(text + "\n", encoding="utf-8")

    print("axes", len(axes))
    print(summary.to_string(index=False))
    print(hyp_df[["name", "observed_value", "null_value", "p_value", "promoted_to_axis"]].to_string(index=False))


if __name__ == "__main__":
    main()
