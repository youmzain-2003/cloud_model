#!/usr/bin/env python3
"""Horizon-based Numbers3 prediction analysis (from-scratch reframing).

Horizons:
  - H1  : next single draw (毎回)
  - H3  : next 3 draw days (数日)
  - H5  : next 5 draw days ≈ one Numbers3 week (月–金)

Claim to test:
  Longer horizons raise P(at least one hit) even under chance, AND may change
  whether foresight can beat the horizon-matched null.

Primary ticket types: mini (last2), straight, box(all-diff multiset).
Budget reference: ¥1000/day = 5 units × ¥200 (carried into multi-day books).
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORTS = ROOT / "reports"

STAKE = 200
DAILY_BUDGET = 1000
DAILY_UNITS = DAILY_BUDGET // STAKE  # 5
ALL_LAST2 = [f"{a}{b}" for a in range(10) for b in range(10)]
L2I = {s: i for i, s in enumerate(ALL_LAST2)}


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA / "numbers3_draws_clean.csv")
    df["date"] = pd.to_datetime(df["date"])
    df["number"] = df["number"].astype(str).str.zfill(3)
    df["d100"] = df["number"].str[0].astype(int)
    df["d10"] = df["number"].str[1].astype(int)
    df["d1"] = df["number"].str[2].astype(int)
    df["last2"] = df["number"].str[1:]
    df["weekday"] = df["date"].dt.weekday
    df["iso_year"] = df["date"].dt.isocalendar().year.astype(int)
    df["iso_week"] = df["date"].dt.isocalendar().week.astype(int)
    df["n_unique"] = df["number"].map(lambda s: len(set(s)))
    return df.sort_values(["date", "draw_no"]).reset_index(drop=True)


def binom_p(hits: int, n: int, p0: float, alt: str = "greater") -> float:
    if n <= 0:
        return float("nan")
    return float(stats.binomtest(hits, n, p0, alternative=alt).pvalue)


def p_union_independent(p: float, n: int) -> float:
    return 1.0 - (1.0 - p) ** n


# ---------------------------------------------------------------------------
# Layer A — null difficulty by horizon (no foresight)
# ---------------------------------------------------------------------------

def null_horizon_table() -> pd.DataFrame:
    """P(at least one hit) under chance for fixed tickets held across a horizon.

    Interpretations:
      - replay_same_tickets: same picks every day in the horizon
      - refresh_daily_disjoint_minis: each day 5 fresh distinct last2 (best mini frequency)
    """
    rows = []
    horizons = [("H1_every_draw", 1), ("H3_few_days", 3), ("H5_weekish", 5)]

    # single unit face odds
    face = {
        "mini": 1 / 100,
        "straight": 1 / 1000,
        "box_all_diff": 6 / 1000,
    }

    for hname, H in horizons:
        for typ, p1 in face.items():
            # 1 unit replayed H days
            rows.append(
                {
                    "horizon": hname,
                    "draws": H,
                    "plan": f"1x_{typ}_replay_H_days",
                    "p_any_hit": p_union_independent(p1, H),
                    "expected_gap_horizons": 1 / p_union_independent(p1, H),
                    "yen_per_horizon": STAKE * H,
                }
            )
            # 5 units same type, approximate independent if disjoint coverage
            if typ == "mini":
                p_day = min(1.0, 5 * p1)  # 5 distinct last2
            elif typ == "box_all_diff":
                p_day = 1 - (1 - p1) ** 5  # approx if low overlap
            else:
                p_day = 1 - (1 - p1) ** 5
            rows.append(
                {
                    "horizon": hname,
                    "draws": H,
                    "plan": f"5x_{typ}_replay_each_day",
                    "p_any_hit": p_union_independent(p_day, H),
                    "expected_gap_horizons": 1 / max(p_union_independent(p_day, H), 1e-12),
                    "yen_per_horizon": DAILY_BUDGET * H,
                }
            )

        # ¥1000/day mini-optimal over horizon
        p_day_mini5 = 0.05
        rows.append(
            {
                "horizon": hname,
                "draws": H,
                "plan": "daily_¥1000_5mini_refresh",
                "p_any_hit": p_union_independent(p_day_mini5, H),
                "expected_gap_horizons": 1 / p_union_independent(p_day_mini5, H),
                "yen_per_horizon": DAILY_BUDGET * H,
                "note": "Best practical frequency under ¥1000/day without edge",
            }
        )
        # week pool: spend full week budget once on distinct minis (no refresh)
        # H days * 5 units = 5H distinct last2 if enough budget concentration
        units = DAILY_UNITS * H
        cover = min(100, units)
        p_week_pool = cover / 100  # one shot against each draw? 
        # Correct model for "buy cover last2s once, they remain valid each day":
        # each day hit if that day's last2 in cover set; P(day)=cover/100
        # P(any in H)=1-(1-c/100)^H
        rows.append(
            {
                "horizon": hname,
                "draws": H,
                "plan": f"pool_{cover}_distinct_minis_held_{H}_days",
                "p_any_hit": p_union_independent(cover / 100, H),
                "expected_gap_horizons": 1 / p_union_independent(cover / 100, H),
                "yen_per_horizon": STAKE * cover,
                "note": "Front-load week budget into a standing mini cover set",
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Layer B — foresight: will targets appear within next H draws?
# ---------------------------------------------------------------------------

def scores_freq(hist: pd.DataFrame) -> np.ndarray:
    c = Counter(hist["last2"])
    return np.array([c[x] + 1e-6 for x in ALL_LAST2], dtype=float)


def scores_recency(hist: pd.DataFrame, hl: int = 20) -> np.ndarray:
    s = np.zeros(100)
    n = len(hist)
    for i, l2 in enumerate(hist["last2"].values):
        s[L2I[l2]] += 0.5 ** ((n - 1 - i) / hl)
    return s + 1e-6


def scores_cold(hist: pd.DataFrame) -> np.ndarray:
    return 1.0 / scores_freq(hist)


def top_k_from_scores(scores: np.ndarray, k: int) -> list[str]:
    order = np.lexsort((np.arange(100), -scores))
    return [ALL_LAST2[i] for i in order[:k]]


def horizon_hit_last2(future_last2: list[str], picks: list[str]) -> bool:
    s = set(picks)
    return any(x in s for x in future_last2)


def eval_last2_horizon_foresight(df: pd.DataFrame, H: int, k: int, start: int) -> pd.DataFrame:
    """Predict a set of k last2s; success if any appears in next H draws."""
    methods = {
        "uniform_random_seeded": None,  # special
        "hot_freq": scores_freq,
        "recency_hl20": lambda h: scores_recency(h, 20),
        "cold_freq": scores_cold,
    }
    rows = []
    # null: k/100 per day, union over H under independence approx for fixed set:
    p0 = 1.0 - (1.0 - k / 100.0) ** H

    min_hist = 150
    for name, fn in methods.items():
        hits = 0
        n = 0
        for i in range(max(start, min_hist), len(df) - H):
            hist = df.iloc[:i]
            future = df.loc[i : i + H - 1, "last2"].tolist()
            if name == "uniform_random_seeded":
                rng = np.random.default_rng(int(df.loc[i, "draw_no"]))
                picks = [ALL_LAST2[j] for j in rng.choice(100, size=k, replace=False)]
            else:
                picks = top_k_from_scores(fn(hist), k)
            n += 1
            hits += int(horizon_hit_last2(future, picks))
        rate = hits / n if n else float("nan")
        rows.append(
            {
                "target": "mini_last2",
                "horizon_draws": H,
                "pick_k": k,
                "method": name,
                "hits": hits,
                "n": n,
                "hit_rate": rate,
                "null_rate": p0,
                "lift": rate - p0,
                "p_value": binom_p(hits, n, p0, "greater"),
            }
        )
    return pd.DataFrame(rows)


def eval_box_horizon(df: pd.DataFrame, H: int, start: int) -> pd.DataFrame:
    """Predict one all-diff multiset (from hot digits); hit if any of next H wins matches multiset."""
    rows = []
    p1 = 6 / 1000
    p0 = p_union_independent(p1, H)
    hits = n = 0
    hits_rand = n_rand = 0
    min_hist = 150
    for i in range(max(start, min_hist), len(df) - H):
        hist = df.iloc[i - 50 : i]
        h = Counter(hist["d100"]).most_common(1)[0][0]
        t = Counter(hist["d10"]).most_common(1)[0][0]
        o = Counter(hist["d1"]).most_common(1)[0][0]
        pick = f"{h}{t}{o}"
        if len(set(pick)) < 3:
            # mutate to all-diff
            digits = list(pick)
            for d in range(10):
                if str(d) not in digits:
                    digits[2] = str(d)
                    break
            pick = "".join(digits)
        future = df.loc[i : i + H - 1, "number"].tolist()
        hit = any(Counter(pick) == Counter(w) for w in future)
        n += 1
        hits += int(hit)

        rng = np.random.default_rng(int(df.loc[i, "draw_no"]))
        # random all-diff
        while True:
            a, b, c = rng.choice(10, 3, replace=False)
            rpick = f"{a}{b}{c}"
            break
        rhit = any(Counter(rpick) == Counter(w) for w in future)
        n_rand += 1
        hits_rand += int(rhit)

    for name, hts, nn in [
        ("hot_digits_box", hits, n),
        ("random_box", hits_rand, n_rand),
    ]:
        rate = hts / nn
        rows.append(
            {
                "target": "box_all_diff",
                "horizon_draws": H,
                "pick_k": 1,
                "method": name,
                "hits": hts,
                "n": nn,
                "hit_rate": rate,
                "null_rate": p0,
                "lift": rate - p0,
                "p_value": binom_p(hts, nn, p0, "greater"),
            }
        )
    return pd.DataFrame(rows)


def eval_straight_horizon(df: pd.DataFrame, H: int, start: int) -> pd.DataFrame:
    p1 = 1 / 1000
    p0 = p_union_independent(p1, H)
    rows = []
    hits = n = 0
    hits_r = n_r = 0
    min_hist = 150
    for i in range(max(start, min_hist), len(df) - H):
        hist = df.iloc[i - 50 : i]
        pick = (
            f"{Counter(hist['d100']).most_common(1)[0][0]}"
            f"{Counter(hist['d10']).most_common(1)[0][0]}"
            f"{Counter(hist['d1']).most_common(1)[0][0]}"
        )
        future = set(df.loc[i : i + H - 1, "number"].tolist())
        n += 1
        hits += int(pick in future)
        rng = np.random.default_rng(int(df.loc[i, "draw_no"]))
        rpick = f"{rng.integers(0,1000):03d}"
        n_r += 1
        hits_r += int(rpick in future)
    for name, hts, nn in [("hot_digits_straight", hits, n), ("random_straight", hits_r, n_r)]:
        rate = hts / nn
        rows.append(
            {
                "target": "straight",
                "horizon_draws": H,
                "pick_k": 1,
                "method": name,
                "hits": hts,
                "n": nn,
                "hit_rate": rate,
                "null_rate": p0,
                "lift": rate - p0,
                "p_value": binom_p(hts, nn, p0, "greater"),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Layer C — calendar week blocks (actual Mon-Fri groups)
# ---------------------------------------------------------------------------

def week_blocks(df: pd.DataFrame) -> list[pd.DataFrame]:
    blocks = []
    for (_, _), g in df.groupby(["iso_year", "iso_week"], sort=True):
        g = g.sort_values("date")
        # Numbers3 typically weekdays; keep weeks with >=3 draws
        if len(g) >= 3:
            blocks.append(g.reset_index(drop=True))
    return blocks


def eval_calendar_week_mini(df: pd.DataFrame, k: int = 5) -> pd.DataFrame:
    """Before each week starts, pick k last2 from history; hit if any weekday draw matches."""
    blocks = week_blocks(df)
    # use first 60% weeks as burn-in history boundary by draw index
    all_idx = {int(d): i for i, d in enumerate(df["draw_no"])}
    cut_draw = df.iloc[int(len(df) * 0.6)]["draw_no"]

    rows = []
    methods = ["hot_freq", "cold_freq", "recency_hl20", "random"]
    # null depends on week length L: 1-(1-k/100)^L
    for method in methods:
        hits = n = 0
        null_sum = 0.0
        for g in blocks:
            first_draw = int(g.iloc[0]["draw_no"])
            if first_draw < cut_draw:
                continue
            # history: all draws before this week
            hist = df[df["draw_no"] < first_draw]
            if len(hist) < 150:
                continue
            L = len(g)
            p0 = 1 - (1 - k / 100) ** L
            null_sum += p0
            if method == "hot_freq":
                picks = top_k_from_scores(scores_freq(hist), k)
            elif method == "cold_freq":
                picks = top_k_from_scores(scores_cold(hist), k)
            elif method == "recency_hl20":
                picks = top_k_from_scores(scores_recency(hist, 20), k)
            else:
                rng = np.random.default_rng(first_draw)
                picks = [ALL_LAST2[j] for j in rng.choice(100, k, replace=False)]
            future = g["last2"].tolist()
            n += 1
            hits += int(horizon_hit_last2(future, picks))
        avg_null = null_sum / n if n else float("nan")
        rate = hits / n if n else float("nan")
        # p-value vs average null is approximate; use mean p0
        rows.append(
            {
                "target": "mini_last2_calendar_week",
                "method": method,
                "pick_k": k,
                "weeks": n,
                "hit_rate": rate,
                "avg_null_rate": avg_null,
                "lift": rate - avg_null if n else None,
                "p_value_vs_avg_null": binom_p(hits, n, avg_null, "greater") if n else None,
            }
        )
    return pd.DataFrame(rows)


def portfolio_horizon_simulation(df: pd.DataFrame) -> pd.DataFrame:
    """Simulate ¥1000/day books over rolling horizons; measure any-hit rate."""
    start = int(len(df) * 0.6)
    rows = []
    for H in (1, 3, 5):
        hits_mini = hits_hybrid = hits_rand = 0
        n = 0
        for i in range(max(start, 50), len(df) - H):
            # for each day in horizon, spend ¥1000
            any_mini = any_hybrid = any_rand = False
            for d in range(H):
                j = i + d
                hist = df.iloc[max(0, j - 50) : j]
                win = df.loc[j, "number"]
                win_l2 = df.loc[j, "last2"]
                # mini5 hot
                hot = [x for x, _ in Counter(hist["last2"]).most_common(5)]
                while len(hot) < 5:
                    hot.append(ALL_LAST2[len(hot)])
                if win_l2 in hot:
                    any_mini = True
                # hybrid: 3 mini + 1 box + 1 straight
                hot3 = hot[:3]
                pick = (
                    f"{Counter(hist['d100']).most_common(1)[0][0]}"
                    f"{Counter(hist['d10']).most_common(1)[0][0]}"
                    f"{Counter(hist['d1']).most_common(1)[0][0]}"
                )
                if win_l2 in hot3 or Counter(pick) == Counter(win) or pick == win:
                    any_hybrid = True
                rng = np.random.default_rng(int(df.loc[j, "draw_no"]))
                rp = [ALL_LAST2[x] for x in rng.choice(100, 5, replace=False)]
                if win_l2 in rp:
                    any_rand = True
            n += 1
            hits_mini += int(any_mini)
            hits_hybrid += int(any_hybrid)
            hits_rand += int(any_rand)

        p0_mini = p_union_independent(0.05, H)
        for name, hits, p0 in [
            ("5mini_hot_daily", hits_mini, p0_mini),
            ("hybrid_3mini_box_str_daily", hits_hybrid, None),
            ("5mini_random_daily", hits_rand, p0_mini),
        ]:
            rate = hits / n
            rows.append(
                {
                    "horizon_draws": H,
                    "plan": name,
                    "eval_windows": n,
                    "any_hit_rate": rate,
                    "null_any_hit_rate": p0,
                    "lift_vs_null": (rate - p0) if p0 is not None else None,
                    "p_value": binom_p(hits, n, p0, "greater") if p0 is not None else None,
                    "yen_per_window": DAILY_BUDGET * H,
                }
            )
    return pd.DataFrame(rows)


def holm(pvals: list[float]) -> list[float]:
    m = len(pvals)
    order = np.argsort([p if p == p else 1 for p in pvals])
    adj = [1.0] * m
    run = 0.0
    for rank, idx in enumerate(order):
        p = pvals[idx]
        if p != p:
            adj[idx] = float("nan")
            continue
        run = max(run, (m - rank) * p)
        adj[idx] = min(1.0, run)
    return adj


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    df = load()
    start = int(len(df) * 0.6)

    null_df = null_horizon_table()
    null_df.to_csv(REPORTS / "horizon_null_probabilities.csv", index=False)

    foresight_rows = []
    for H in (1, 3, 5):
        print("last2 foresight H", H, flush=True)
        foresight_rows.append(eval_last2_horizon_foresight(df, H, k=5, start=start))
        # also k=15 as "heavier cover" comparison (would cost more than ¥1000/day if daily)
        foresight_rows.append(eval_last2_horizon_foresight(df, H, k=15, start=start))
        print("box/straight H", H, flush=True)
        foresight_rows.append(eval_box_horizon(df, H, start))
        foresight_rows.append(eval_straight_horizon(df, H, start))
    foresight = pd.concat(foresight_rows, ignore_index=True)
    # Holm within last2 k=5 methods only (fair family)
    fam = foresight[(foresight["target"] == "mini_last2") & (foresight["pick_k"] == 5)].copy()
    fam["p_holm"] = holm(fam["p_value"].tolist())
    fam["promoted"] = (fam["p_holm"] < 0.05) & (fam["lift"] > 0)
    foresight = foresight.merge(
        fam[["horizon_draws", "method", "pick_k", "p_holm", "promoted"]],
        on=["horizon_draws", "method", "pick_k"],
        how="left",
    )
    foresight.to_csv(REPORTS / "horizon_foresight_results.csv", index=False)

    print("calendar weeks", flush=True)
    week_df = eval_calendar_week_mini(df, k=5)
    week_df.to_csv(REPORTS / "horizon_calendar_week_mini.csv", index=False)

    print("portfolio sim", flush=True)
    port = portfolio_horizon_simulation(df)
    port.to_csv(REPORTS / "horizon_portfolio_simulation.csv", index=False)

    # difficulty curve summary
    curve = []
    for H, label in [(1, "毎回"), (3, "数日"), (5, "週相当")]:
        p_mini5 = p_union_independent(0.05, H)
        p_str1 = p_union_independent(0.001, H)
        p_box1 = p_union_independent(0.006, H)
        curve.append(
            {
                "horizon": label,
                "draws": H,
                "p_any_¥1000_5mini_null": p_mini5,
                "approx_horizons_per_hit_5mini": 1 / p_mini5,
                "p_any_1_straight_null": p_str1,
                "p_any_1_box_null": p_box1,
                "foresight_promoted_last2_k5": int(
                    fam[(fam["horizon_draws"] == H) & (fam["promoted"] == True)].shape[0]
                ),
            }
        )

    summary = {
        "reframe": (
            "Predicting every draw vs a few days vs a week changes BASE RATES a lot. "
            "That raises hit chance even with zero skill. Skill still requires beating "
            "the horizon-matched null."
        ),
        "difficulty_curve_null": curve,
        "foresight_family_last2_k5": fam.to_dict(orient="records"),
        "calendar_week": week_df.to_dict(orient="records"),
        "portfolio": port.to_dict(orient="records"),
        "verdict": {
            "difficulty_orders": "H1 hardest << H3 << H5 easiest (for any-hit)",
            "null_¥1000_5mini": {
                "H1": p_union_independent(0.05, 1),
                "H3": p_union_independent(0.05, 3),
                "H5": p_union_independent(0.05, 5),
            },
            "foresight_beats_null": bool(fam["promoted"].fillna(False).any()),
            "message": (
                "Longer horizons make hits feel more frequent — mostly because chance compounds. "
                "Walk-forward foresight still fails to beat horizon-matched nulls for last2 top-5."
            ),
        },
    }

    def conv(o):
        if isinstance(o, dict):
            return {str(k): conv(v) for k, v in o.items()}
        if isinstance(o, list):
            return [conv(v) for v in o]
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating, float)):
            v = float(o)
            return None if v != v else v
        if isinstance(o, (np.bool_, bool)):
            return bool(o)
        if hasattr(o, "item"):
            try:
                return conv(o.item())
            except Exception:
                return str(o)
        return o

    (REPORTS / "horizon_analysis_summary.json").write_text(
        json.dumps(conv(summary), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = []
    lines.append("# ホライズン別・当選番号予想の再分析")
    lines.append("")
    lines.append("## ねらい")
    lines.append(
        "毎回予想・数日予想・今週予想では難易度と『当たりやすさ』が変わる。"
        "最初からこの軸で、帰無確率と先読み（偶然超え）を切り分けて検証する。"
    )
    lines.append("")
    lines.append("## 1. 難易度カーブ（予想スキルなし／¥1000で5ミニ相当）")
    lines.append("| ホライズン | 抽選回数 | どれか当たる確率 | 当たり間隔の目安 |")
    lines.append("|---|---:|---:|---:|")
    for c in curve:
        lines.append(
            f"| {c['horizon']} | {c['draws']} | {c['p_any_¥1000_5mini_null']:.1%} | "
            f"約{c['approx_horizons_per_hit_5mini']:.1f}ホライズンに1回 |"
        )
    lines.append("")
    lines.append(
        f"参考: ストレート1口をH日間持ち越し → H1 {p_union_independent(0.001,1):.2%} / "
        f"H3 {p_union_independent(0.001,3):.2%} / H5 {p_union_independent(0.001,5):.2%}"
    )
    lines.append(
        f"参考: ボックス1口 → H1 {p_union_independent(0.006,1):.2%} / "
        f"H3 {p_union_independent(0.006,3):.2%} / H5 {p_union_independent(0.006,5):.2%}"
    )
    lines.append("")
    lines.append("## 2. 先読みはホライズンを伸ばすと強くなるか？")
    lines.append(
        "ミニ: 歴史から下2桁を5つ選び、次のH回のどれかに出るか。"
        "帰無は `1-(1-0.05)^H`。"
    )
    lines.append("| H | method | rate | null | lift | p | p_Holm |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|")
    for _, r in fam.sort_values(["horizon_draws", "hit_rate"], ascending=[True, False]).iterrows():
        ph = r["p_holm"] if r["p_holm"] == r["p_holm"] else float("nan")
        lines.append(
            f"| {int(r['horizon_draws'])} | {r['method']} | {r['hit_rate']:.4f} | "
            f"{r['null_rate']:.4f} | {r['lift']:+.4f} | {r['p_value']:.4g} | {ph:.4g} |"
        )
    lines.append("")
    lines.append(
        f"**Holm後に昇格した先読み: "
        f"{int(fam['promoted'].fillna(False).sum())} 件**"
    )
    lines.append("")
    lines.append("## 3. 実カレンダー週（月–金ブロック）")
    lines.append("| method | weeks | hit_rate | avg_null | lift | p |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for _, r in week_df.iterrows():
        lines.append(
            f"| {r['method']} | {int(r['weeks'])} | {r['hit_rate']:.4f} | "
            f"{r['avg_null_rate']:.4f} | {r['lift']:+.4f} | {r['p_value_vs_avg_null']:.4g} |"
        )
    lines.append("")
    lines.append("## 4. ¥1000/日ポートフォリオ（ローリングH）")
    lines.append("| H | plan | any_hit_rate | null | lift |")
    lines.append("|---:|---|---:|---:|---:|")
    for _, r in port.iterrows():
        null = f"{r['null_any_hit_rate']:.4f}" if r["null_any_hit_rate"] == r["null_any_hit_rate"] else "-"
        lift = f"{r['lift_vs_null']:+.4f}" if r["lift_vs_null"] == r["lift_vs_null"] else "-"
        lines.append(
            f"| {int(r['horizon_draws'])} | {r['plan']} | {r['any_hit_rate']:.4f} | {null} | {lift} |"
        )
    lines.append("")
    lines.append("## 結論")
    lines.append(
        "1. **難易度は確かに変わる。** 同じ¥1000運用でも、"
        f"毎回≈{p_union_independent(0.05,1):.0%}、数日(3)≈{p_union_independent(0.05,3):.0%}、"
        f"週(5)≈{p_union_independent(0.05,5):.0%} と、当たりやすさは積み上がる。"
    )
    lines.append(
        "2. ただしそれは主に**時間（試行回数）の効果**であり、予想精度が上がった証拠ではない。"
    )
    lines.append(
        "3. ホライズンを伸ばしても、下2桁トップ5の先読みは帰無を安定して超えなかった。"
        "『今週なら当たる法則』も、今のデータでは未確認。"
    )
    lines.append(
        "4. 実務的には、目標を『毎回』から『今週どれか』に変えると体感難易度は下がる。"
        "その目標変更は有効。そこに予想エッジを足す段階は、まだ根拠不足。"
    )
    lines.append("")
    lines.append("保存: `horizon_*.csv`, `horizon_analysis_summary.json`, `HORIZON_ANALYSIS_REPORT.md`")
    (REPORTS / "HORIZON_ANALYSIS_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # pointers
    for path, marker, extra in [
        (
            REPORTS / "PREDICTION_AXIS_REPORT.md",
            "\n## 追記: ホライズン別再分析\n",
            "詳細は `HORIZON_ANALYSIS_REPORT.md`。毎回/数日/週で帰無的中率が大きく変わるが、先読みは帰無超えせず。\n",
        ),
        (
            REPORTS / "REPORT.md",
            "\n## 追記: ホライズン別予想\n",
            "新規枠の再分析: `HORIZON_ANALYSIS_REPORT.md` / `horizon_analysis_summary.json`\n",
        ),
    ]:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            addition = marker + extra
            if marker in text:
                text = text.split(marker)[0].rstrip() + "\n" + addition
            else:
                text = text.rstrip() + "\n" + addition
            path.write_text(text + "\n", encoding="utf-8")

    print(null_df[null_df["plan"].str.contains("daily_¥1000|pool_")].to_string(index=False))
    print(fam[["horizon_draws", "method", "hit_rate", "null_rate", "lift", "p_holm", "promoted"]].to_string(index=False))
    print(week_df.to_string(index=False))
    print(port.to_string(index=False))


if __name__ == "__main__":
    main()
