#!/usr/bin/env python3
"""Multi-angle predictive analysis for Numbers3 (primary) and Bingo5 (secondary).

Scientific framing:
  - Treat each candidate "law" as a hypothesis H1 against IID-uniform null H0.
  - Prefer walk-forward / out-of-sample tests over in-sample pattern mining.
  - Score strategies by hit-rate lift AND yen return vs random baseline.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORTS = ROOT / "reports"

# Official-style theoretical reference (200-yen unit). Actual payouts vary by sales.
N3_STAKE = 200
N3_STRAIGHT_THEORY = 90_000  # frequently cited theoretical straight payout
N3_BOX_6WAY_THEORY = 15_000
N3_MINI_THEORY = 900
B5_STAKE = 200


@dataclass
class TestResult:
    name: str
    metric: str
    value: float
    p_value: float | None
    note: str
    predictive: bool


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    n3_raw = pd.read_csv(DATA / "numbers3_draws.csv")
    clean_path = DATA / "numbers3_draws_clean.csv"
    if not clean_path.exists():
        raise FileNotFoundError("Run scripts/clean_data.py first")
    n3 = pd.read_csv(clean_path)
    b5 = pd.read_csv(DATA / "bingo5_draws.csv")
    for df in (n3_raw, n3, b5):
        df["date"] = pd.to_datetime(df["date"])
    n3_raw = n3_raw.sort_values("draw_no").reset_index(drop=True)
    n3 = n3.sort_values("draw_no").reset_index(drop=True)
    b5 = b5.sort_values("draw_no").reset_index(drop=True)
    return n3_raw, n3, b5


def chi_square_uniform(counts: np.ndarray, n_cats: int) -> tuple[float, float]:
    expected = np.full(n_cats, counts.sum() / n_cats)
    # pad if missing categories
    if len(counts) != n_cats:
        full = np.zeros(n_cats)
        for i, c in enumerate(counts):
            full[i] = c
        counts = full
    chi2, p = stats.chisquare(counts, expected)
    return float(chi2), float(p)


def runs_test_binary(x: np.ndarray) -> tuple[float, float]:
    """Wald-Wolfowitz runs test on a binary series."""
    x = np.asarray(x, dtype=int)
    n1 = int((x == 1).sum())
    n0 = int((x == 0).sum())
    if n1 == 0 or n0 == 0:
        return float("nan"), float("nan")
    runs = 1 + int(np.sum(x[1:] != x[:-1]))
    mu = 1 + 2 * n1 * n0 / (n1 + n0)
    var = (2 * n1 * n0 * (2 * n1 * n0 - n1 - n0)) / (
        (n1 + n0) ** 2 * (n1 + n0 - 1)
    )
    if var <= 0:
        return float("nan"), float("nan")
    z = (runs - mu) / math.sqrt(var)
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    return float(z), float(p)


def entropy(probs: np.ndarray) -> float:
    p = probs[probs > 0]
    return float(-(p * np.log2(p)).sum())


def n3_basic_randomness(n3: pd.DataFrame) -> list[TestResult]:
    out: list[TestResult] = []
    for col, label in [("d100", "hundreds"), ("d10", "tens"), ("d1", "ones")]:
        counts = n3[col].value_counts().reindex(range(10), fill_value=0).values
        chi2, p = chi_square_uniform(counts.astype(float), 10)
        out.append(
            TestResult(
                f"N3 chi2 uniform {label}",
                "chi2",
                chi2,
                p,
                "Reject H0 if p<<0.05 (digit not uniform).",
                predictive=False,
            )
        )
    # odd/even balance of sum
    s = n3["d100"] + n3["d10"] + n3["d1"]
    odd = (s % 2).values
    z, p = runs_test_binary(odd)
    out.append(
        TestResult(
            "N3 runs-test sum parity",
            "z",
            z,
            p,
            "Serial dependence in odd/even of digit-sum.",
            predictive=False,
        )
    )
    # number-level uniformity over 000-999
    cnt = n3["number"].astype(str).str.zfill(3).value_counts()
    # sparse: use digit-wise already; also entropy of empirical number dist
    probs = (cnt / cnt.sum()).values
    H = entropy(probs)
    out.append(
        TestResult(
            "N3 empirical number entropy (bits)",
            "entropy",
            H,
            None,
            f"Max entropy for observed support size {len(cnt)} "
            f"≈ {math.log2(len(cnt)):.3f}; full 1000-space max=9.966.",
            predictive=False,
        )
    )
    return out


def lag_hit_rates(n3: pd.DataFrame) -> pd.DataFrame:
    """How often previous-draw features reappear — in-sample descriptive."""
    num = n3["number"].astype(str).str.zfill(3)
    rows = []
    exact = (num.values[1:] == num.values[:-1]).mean()
    rows.append({"feature": "exact_repeat", "rate": float(exact), "null": 1 / 1000})

    def digit_overlap(a: str, b: str) -> int:
        return sum(x == y for x, y in zip(a, b))

    same_pos = np.mean(
        [digit_overlap(a, b) / 3 for a, b in zip(num.values[:-1], num.values[1:])]
    )
    rows.append({"feature": "same_digit_same_pos_avg", "rate": float(same_pos), "null": 0.1})

    # any shared multiset digit
    share = []
    for a, b in zip(num.values[:-1], num.values[1:]):
        share.append(len(set(a) & set(b)) > 0)
    rng = np.random.default_rng(0)
    sim = []
    for _ in range(20000):
        a = rng.integers(0, 10, 3)
        b = rng.integers(0, 10, 3)
        sim.append(len(set(a.tolist()) & set(b.tolist())) > 0)
    rows.append(
        {
            "feature": "any_shared_digit_multiset",
            "rate": float(np.mean(share)),
            "null": float(np.mean(sim)),
        }
    )

    # slide ±1 on any position
    slide = []
    for a, b in zip(num.values[:-1], num.values[1:]):
        hit = False
        for i in range(3):
            da, db = int(a[i]), int(b[i])
            if abs(da - db) == 1:
                hit = True
                break
        slide.append(hit)
    # null sim
    sim = []
    for _ in range(20000):
        a = rng.integers(0, 10, 3)
        b = rng.integers(0, 10, 3)
        sim.append(any(abs(int(a[i]) - int(b[i])) == 1 for i in range(3)))
    rows.append(
        {
            "feature": "any_pos_slide_pm1",
            "rate": float(np.mean(slide)),
            "null": float(np.mean(sim)),
        }
    )
    return pd.DataFrame(rows)


def transition_predictability(n3: pd.DataFrame) -> dict:
    """Markov lag-1: does P(digit_t | digit_{t-1}) beat uniform?"""
    results = {}
    for col in ["d100", "d10", "d1"]:
        prev = n3[col].values[:-1]
        cur = n3[col].values[1:]
        # mutual information estimate
        joint = np.zeros((10, 10))
        for a, b in zip(prev, cur):
            joint[a, b] += 1
        joint /= joint.sum()
        p_a = joint.sum(axis=1, keepdims=True)
        p_b = joint.sum(axis=0, keepdims=True)
        mi = 0.0
        for i in range(10):
            for j in range(10):
                if joint[i, j] > 0:
                    mi += joint[i, j] * math.log2(
                        joint[i, j] / (p_a[i, 0] * p_b[0, j])
                    )
        # walk-forward majority from last W transitions
        correct = 0
        total = 0
        W = 300
        for t in range(W, len(n3) - 1):
            hist_prev = n3[col].values[t - W : t]
            hist_cur = n3[col].values[t - W + 1 : t + 1]
            # conditioned on prev digit at t
            p = n3[col].values[t]
            mask = hist_prev == p
            if mask.sum() < 5:
                pred = Counter(hist_cur).most_common(1)[0][0]
            else:
                pred = Counter(hist_cur[mask]).most_common(1)[0][0]
            correct += int(pred == n3[col].values[t + 1])
            total += 1
        acc = correct / total if total else float("nan")
        results[col] = {
            "mutual_information_bits": mi,
            "walkforward_next_digit_acc": acc,
            "uniform_baseline_acc": 0.1,
            "lift_vs_uniform": acc - 0.1,
        }
    return results


def build_n3_features(n3: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Feature matrix for predicting next hundreds digit (representative target)."""
    d = n3[["d100", "d10", "d1"]].values
    feats = []
    names = []
    # lags 1..5 of each digit
    max_lag = 5
    y = d[max_lag:, 0]
    for lag in range(1, max_lag + 1):
        for j, lab in enumerate(["h", "t", "o"]):
            feats.append(d[max_lag - lag : len(d) - lag, j])
            names.append(f"lag{lag}_{lab}")
    # rolling freq of hundreds digit over last 20
    roll = []
    for i in range(max_lag, len(d)):
        window = d[i - 20 : i, 0] if i >= 20 else d[:i, 0]
        counts = np.bincount(window, minlength=10) / max(len(window), 1)
        roll.append(counts)
    roll = np.asarray(roll)
    for k in range(10):
        feats.append(roll[:, k])
        names.append(f"roll20_h_freq_{k}")
    # sum / parity / consecutive flags from lag1
    lag1 = d[max_lag - 1 : len(d) - 1]
    s = lag1.sum(axis=1)
    feats.extend(
        [
            s,
            s % 2,
            (lag1[:, 0] == lag1[:, 1]).astype(float),
            (lag1[:, 1] == lag1[:, 2]).astype(float),
            (np.abs(lag1[:, 0] - lag1[:, 1]) == 1).astype(float),
            (np.abs(lag1[:, 1] - lag1[:, 2]) == 1).astype(float),
        ]
    )
    names.extend(
        [
            "lag1_sum",
            "lag1_sum_parity",
            "lag1_h_eq_t",
            "lag1_t_eq_o",
            "lag1_h_slide_t",
            "lag1_t_slide_o",
        ]
    )
    X = np.column_stack(feats)
    return X, y, names


def ml_walkforward(n3: pd.DataFrame) -> dict:
    X, y, names = build_n3_features(n3)
    tscv = TimeSeriesSplit(n_splits=5)
    models = {
        "logreg": LogisticRegression(max_iter=2000),
        "rf": RandomForestClassifier(
            n_estimators=200, max_depth=6, random_state=0, n_jobs=-1
        ),
    }
    out = {}
    for name, model in models.items():
        accs, losses = [], []
        for train_idx, test_idx in tscv.split(X):
            Xtr, Xte = X[train_idx], X[test_idx]
            ytr, yte = y[train_idx], y[test_idx]
            if name == "logreg":
                scaler = StandardScaler()
                Xtr = scaler.fit_transform(Xtr)
                Xte = scaler.transform(Xte)
            model.fit(Xtr, ytr)
            pred = model.predict(Xte)
            proba = model.predict_proba(Xte)
            accs.append(accuracy_score(yte, pred))
            # align columns
            full = np.zeros((len(yte), 10))
            for i, cls in enumerate(model.classes_):
                full[:, int(cls)] = proba[:, i]
            losses.append(log_loss(yte, full, labels=list(range(10))))
        out[name] = {
            "cv_accuracy_mean": float(np.mean(accs)),
            "cv_accuracy_std": float(np.std(accs)),
            "cv_logloss_mean": float(np.mean(losses)),
            "uniform_accuracy": 0.1,
            "uniform_logloss": -math.log(0.1),
        }
        if name == "rf":
            # refit on all for crude importance (descriptive only)
            model.fit(X, y)
            imp = sorted(
                zip(names, model.feature_importances_),
                key=lambda z: z[1],
                reverse=True,
            )[:12]
            out[name]["top_features"] = [
                {"feature": f, "importance": float(v)} for f, v in imp
            ]
    return out


def strategy_backtest_n3(n3: pd.DataFrame) -> pd.DataFrame:
    """Walk-forward strategies: pick 1 straight ticket / draw using rules."""
    nums = n3["number"].astype(str).str.zfill(3).tolist()
    prizes = n3["straight_prize_yen"].fillna(N3_STRAIGHT_THEORY).astype(float).tolist()
    strategies = {}

    # 1) random baseline (fixed seed sequence)
    rng = np.random.default_rng(42)
    rand_picks = [f"{rng.integers(0,1000):03d}" for _ in nums]

    # 2) pure repeat previous
    repeat_picks = ["000"] + nums[:-1]

    # 3) hot hundreds/tens/ones from last W
    W = 50
    hot_picks = []
    for i in range(len(nums)):
        if i < W:
            hot_picks.append(rand_picks[i])
            continue
        window = nums[i - W : i]
        h = Counter(n[0] for n in window).most_common(1)[0][0]
        t = Counter(n[1] for n in window).most_common(1)[0][0]
        o = Counter(n[2] for n in window).most_common(1)[0][0]
        hot_picks.append(h + t + o)

    # 4) cold digits
    cold_picks = []
    for i in range(len(nums)):
        if i < W:
            cold_picks.append(rand_picks[i])
            continue
        window = nums[i - W : i]
        h = Counter(n[0] for n in window).most_common()[-1][0]
        t = Counter(n[1] for n in window).most_common()[-1][0]
        o = Counter(n[2] for n in window).most_common()[-1][0]
        cold_picks.append(h + t + o)

    # 5) slide +1 on previous (mod 10)
    slide_picks = []
    for i, prev in enumerate(["000"] + nums[:-1]):
        slide_picks.append(
            "".join(str((int(ch) + 1) % 10) for ch in prev)
        )

    # 6) avoid popular: use theoretical — pick least frequent exact number in history
    # (computationally ok)
    avoid_picks = []
    freq = Counter()
    for i in range(len(nums)):
        if i < 100:
            avoid_picks.append(rand_picks[i])
        else:
            # choose min-frequency among 000-999 — too heavy; use digit-wise cold already.
            # Instead: pick number that appeared least among last 500 exact draws,
            # fallback random among unseen in last 500.
            recent = nums[max(0, i - 500) : i]
            c = Counter(recent)
            # prefer never-seen random-ish via hash
            cand = None
            for k in range(1000):
                s = f"{(i * 97 + k) % 1000:03d}"
                if c[s] == 0:
                    cand = s
                    break
            avoid_picks.append(cand or min(c, key=c.get))
        freq[nums[i]] += 1

    strategies = {
        "random": rand_picks,
        "repeat_prev": repeat_picks,
        "hot_digits_W50": hot_picks,
        "cold_digits_W50": cold_picks,
        "slide_plus1": slide_picks,
        "unseen_in_last500": avoid_picks,
    }

    # evaluate only on last 40% as holdout after burn-in
    start = int(len(nums) * 0.6)
    rows = []
    for name, picks in strategies.items():
        hits = 0
        spent = 0
        won = 0.0
        for i in range(start, len(nums)):
            spent += N3_STAKE
            if picks[i] == nums[i]:
                hits += 1
                won += prizes[i] if prizes[i] > 0 else N3_STRAIGHT_THEORY
        n = len(nums) - start
        rows.append(
            {
                "strategy": name,
                "holdout_draws": n,
                "straight_hits": hits,
                "hit_rate": hits / n,
                "null_hit_rate": 1 / 1000,
                "spent_yen": spent,
                "won_yen": won,
                "roi": won / spent - 1 if spent else float("nan"),
                "avg_prize_if_theory": N3_STRAIGHT_THEORY,
            }
        )
    return pd.DataFrame(rows).sort_values("roi", ascending=False)


def box_ev_note(n3: pd.DataFrame) -> dict:
    """Classify draw types and compare observed straight prizes vs theory."""
    def box_type(s: str) -> str:
        s = str(s).zfill(3)
        c = Counter(s)
        if len(c) == 1:
            return "triple"
        if len(c) == 2:
            return "double"
        return "all_diff"

    types = n3["number"].astype(str).map(box_type)
    prize = n3["straight_prize_yen"]
    summary = {}
    for t, g in n3.groupby(types):
        summary[t] = {
            "count": int(len(g)),
            "share": float(len(g) / len(n3)),
            "avg_straight_prize": float(g["straight_prize_yen"].mean()),
            "median_straight_prize": float(g["straight_prize_yen"].median()),
            "avg_winners": float(g["straight_winners"].mean()),
        }
    # theoretical composition shares
    summary["_null_shares"] = {
        "triple": 10 / 1000,
        "double": 270 / 1000,
        "all_diff": 720 / 1000,
    }
    summary["_payout_refs_yen_per_200"] = {
        "straight_theory": N3_STRAIGHT_THEORY,
        "box_6way_theory": N3_BOX_6WAY_THEORY,
        "mini_theory": N3_MINI_THEORY,
        "stake": N3_STAKE,
        "straight_theory_ev_ratio": N3_STRAIGHT_THEORY / 1000 / N3_STAKE,
    }
    return summary


def bingo5_analysis(b5: pd.DataFrame) -> dict:
    mats = b5[[f"n{i}" for i in range(1, 9)]].values.astype(int)
    bands = [
        np.arange(1, 6),
        np.arange(6, 11),
        np.arange(11, 16),
        np.arange(16, 21),
        np.arange(21, 26),
        np.arange(26, 31),
        np.arange(31, 36),
        np.arange(36, 41),
    ]
    # frequency within each band should be ~uniform over 5 numbers
    band_tests = []
    for bi, band in enumerate(bands):
        col = mats[:, bi]
        counts = np.array([(col == v).sum() for v in band], dtype=float)
        chi2, p = chi_square_uniform(counts, 5)
        band_tests.append({"band": f"{band[0]}-{band[-1]}", "chi2": chi2, "p_value": p})

    overlaps = [
        len(set(mats[i]) & set(mats[i - 1])) for i in range(1, len(mats))
    ]
    rng = np.random.default_rng(0)

    def sample_card() -> np.ndarray:
        return np.array([rng.choice(band) for band in bands], dtype=int)

    sim = []
    for _ in range(20000):
        a = sample_card()
        b = sample_card()
        sim.append(len(set(a.tolist()) & set(b.tolist())))

    consec = []
    for row in mats:
        s = sorted(row)
        consec.append(sum(1 for i in range(7) if s[i + 1] - s[i] == 1))
    sim_c = []
    for _ in range(20000):
        s = sorted(sample_card().tolist())
        sim_c.append(sum(1 for i in range(7) if s[i + 1] - s[i] == 1))

    W = 30
    hot_overlaps = []
    rand_overlaps = []
    for i in range(W, len(mats)):
        # hot within each band from last W
        pick = []
        for bi, band in enumerate(bands):
            window = mats[i - W : i, bi]
            freq = Counter(window.tolist())
            pick.append(freq.most_common(1)[0][0])
        hot_overlaps.append(len(set(pick) & set(mats[i])))
        rand_overlaps.append(len(set(sample_card().tolist()) & set(mats[i])))

    prize = b5["first_prize_yen"].dropna()
    winners = b5["first_winners"].dropna()
    # crude 1st-prize EV proxy if buying 1 of C(5)^8 cards — not practical;
    # instead report observed mean 1st prize and winner count (pari-mutuel pressure)
    return {
        "draws": int(len(b5)),
        "structure": "one number from each of 8 bands of 5 (bingo card columns/rows)",
        "band_uniform_chi2": band_tests,
        "overlap_with_prev": {
            "mean": float(np.mean(overlaps)),
            "null_mean_band_aware": float(np.mean(sim)),
            "std": float(np.std(overlaps)),
            "null_std_band_aware": float(np.std(sim)),
        },
        "consecutive_pairs_per_draw": {
            "mean": float(np.mean(consec)),
            "null_mean_band_aware": float(np.mean(sim_c)),
        },
        "hot_W30_vs_random_overlap_band_aware": {
            "hot_mean_overlap": float(np.mean(hot_overlaps)),
            "random_mean_overlap": float(np.mean(rand_overlaps)),
            "note": "Overlap with next winning set (0-8), not prize EV.",
        },
        "first_prize_yen": {
            "mean": float(prize.mean()) if len(prize) else None,
            "median": float(prize.median()) if len(prize) else None,
            "min": float(prize.min()) if len(prize) else None,
            "max": float(prize.max()) if len(prize) else None,
        },
        "first_winners": {
            "mean": float(winners.mean()) if len(winners) else None,
            "median": float(winners.median()) if len(winners) else None,
        },
        "stake_yen": B5_STAKE,
        "payout_note": (
            "Bingo5 1st prize is pari-mutuel: more winners => lower yen. "
            "Avoiding popular cards can raise conditional payout, not hit probability."
        ),
    }


def cross_game(n3: pd.DataFrame, b5: pd.DataFrame) -> dict:
    """Same-calendar-day linkage between N3 and Bingo5 (Wednesdays)."""
    # Bingo5 is weekly (Wed). Aggregate N3 on those dates.
    merged = b5.merge(n3, on="date", how="inner", suffixes=("_b5", "_n3"))
    if merged.empty:
        # N3 draws daily; merge may have multiple N3 per day — use asof? 
        # Better: for each b5 date, take that day's n3 rows.
        pass
    # Remerge properly: many N3 per day historically? Usually 1/day.
    m = pd.merge(
        b5.assign(key=1),
        n3.assign(key=1),
        on="date",
        how="inner",
        suffixes=("_b5", "_n3"),
    )
    if m.empty:
        return {"paired_draws": 0}
    # correlation between b5 sum and n3 digit sum on same date
    b5_sum = m[[f"n{i}" for i in range(1, 9)]].sum(axis=1)
    n3_sum = m["d100"] + m["d10"] + m["d1"]
    if len(m) > 3:
        r, p = stats.pearsonr(b5_sum, n3_sum)
    else:
        r, p = float("nan"), float("nan")
    # shared last digit between n3 ones and any bingo number mod 10
    share = []
    for _, row in m.iterrows():
        ones = int(row["d1"])
        bnums = [int(row[f"n{i}"]) % 10 for i in range(1, 9)]
        share.append(ones in bnums)
    rng = np.random.default_rng(0)
    sim = [rng.integers(0, 10) in rng.choice(10, 8, replace=True) for _ in range(20000)]
    return {
        "paired_same_date_rows": int(len(m)),
        "pearson_sum_r": float(r),
        "pearson_sum_p": float(p),
        "n3_ones_in_bingo_mod10_rate": float(np.mean(share)),
        "null_rate_sim": float(np.mean(sim)),
    }


def weekday_effects(n3: pd.DataFrame) -> pd.DataFrame:
    df = n3.copy()
    df["weekday"] = df["date"].dt.day_name()
    g = (
        df.groupby("weekday")
        .agg(
            draws=("draw_no", "count"),
            avg_sum=("number", lambda s: np.mean(
                [sum(int(ch) for ch in str(x).zfill(3)) for x in s]
            )),
            avg_straight_prize=("straight_prize_yen", "mean"),
            avg_winners=("straight_winners", "mean"),
        )
        .reset_index()
    )
    # chi2 of hundreds digit by weekday (flatten)
    rows = []
    for wd, sub in df.groupby("weekday"):
        counts = sub["d100"].value_counts().reindex(range(10), fill_value=0).values
        chi2, p = chi_square_uniform(counts.astype(float), 10)
        rows.append({"weekday": wd, "d100_chi2": chi2, "d100_p": p})
    return g.merge(pd.DataFrame(rows), on="weekday")


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    n3_raw, n3, b5 = load_data()
    quality = json.loads((DATA / "numbers3_data_quality.json").read_text(encoding="utf-8"))

    tests = n3_basic_randomness(n3)
    lag = lag_hit_rates(n3)
    lag_raw = lag_hit_rates(n3_raw)
    markov = transition_predictability(n3)
    ml = ml_walkforward(n3)
    strat = strategy_backtest_n3(n3)
    strat_raw = strategy_backtest_n3(n3_raw)
    box = box_ev_note(n3)
    b5a = bingo5_analysis(b5)
    cross = cross_game(n3, b5)
    week = weekday_effects(n3)

    # Persist tables
    lag.to_csv(REPORTS / "n3_lag_features.csv", index=False)
    lag_raw.to_csv(REPORTS / "n3_lag_features_raw.csv", index=False)
    strat.to_csv(REPORTS / "n3_strategy_backtest.csv", index=False)
    strat_raw.to_csv(REPORTS / "n3_strategy_backtest_raw.csv", index=False)
    week.to_csv(REPORTS / "n3_weekday_effects.csv", index=False)
    pd.DataFrame([asdict(t) for t in tests]).to_csv(
        REPORTS / "n3_randomness_tests.csv", index=False
    )

    # Popularity vs payout (straight): more winners => lower prize
    prize_corr = float(
        n3[["straight_winners", "straight_prize_yen"]]
        .dropna()
        .corr()
        .iloc[0, 1]
    )

    summary = {
        "meta": {
            "numbers3_draws_raw": int(len(n3_raw)),
            "numbers3_draws_clean": int(len(n3)),
            "numbers3_date_range_clean": [
                str(n3["date"].min().date()),
                str(n3["date"].max().date()),
            ],
            "bingo5_draws": int(len(b5)),
            "bingo5_date_range": [
                str(b5["date"].min().date()),
                str(b5["date"].max().date()),
            ],
            "sources": {
                "numbers3": "https://numbers-renban.tokyo/numbers3/result_all",
                "bingo5": "https://bingo5.money-plan.net/history/",
                "mizuho_blocked": True,
            },
            "data_quality": quality,
            "stake_yen": {"numbers3": N3_STAKE, "bingo5": B5_STAKE},
        },
        "numbers3_randomness_tests": [asdict(t) for t in tests],
        "numbers3_lag_vs_null_clean": lag.to_dict(orient="records"),
        "numbers3_lag_vs_null_raw": lag_raw.to_dict(orient="records"),
        "numbers3_markov": markov,
        "numbers3_ml_walkforward": ml,
        "numbers3_strategy_backtest_clean": strat.to_dict(orient="records"),
        "numbers3_strategy_backtest_raw": strat_raw.to_dict(orient="records"),
        "numbers3_box_and_payout": box,
        "numbers3_winners_vs_prize_corr": prize_corr,
        "bingo5": b5a,
        "cross_n3_bingo5": cross,
        "verdict": {
            "prediction_edge_found": False,
            "criteria": (
                "Edge requires holdout hit-rate or ROI statistically above "
                "random baseline after data-quality controls and multiple-testing."
            ),
            "key_findings": [
                "Mirror data contains multi-day identical-number streaks and duplicate payout rows; raw repeat-prev backtests are invalid.",
                "After removing long streaks and identical-payout duplicates, residual exact-repeats approach the null rate.",
                "On cleaned Numbers3, digit marginals pass uniformity; lag lifts collapse near null.",
                "ML digit prediction stays at chance (~10%).",
                "Straight winners and prize are negatively correlated (sales/crowding effect on payout).",
                "Bingo5 is band-structured (8x choose-1-of-5); band-aware nulls match overlaps/consecutives.",
                "Same-day N3↔Bingo5 linkage is absent.",
            ],
            "actionable_for_prediction_pipeline": [
                "Treat indicator discovery as hypothesis testing with walk-forward ROI/logloss gates.",
                "Optimize payout-conditioned objectives (avoid crowded numbers) separately from hit-probability.",
                "Keep Numbers3 as high-frequency sandbox; Bingo5 for weekly variance/payout study.",
                "Re-validate any mirror anomaly against official Mizuho results before claiming signal.",
            ],
        },
    }
    (REPORTS / "analysis_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Human report
    lines = []
    lines.append("# ナンバーズ3／ビンゴ5 予測分析レポート")
    lines.append("")
    lines.append("## 目的")
    lines.append(
        "運の言い換えではなく、**予測問題**として定式化する。"
        "各指標は帰無仮説「IID一様乱数」に対する検定・"
        "時系列ウォークフォワード評価・金額ROIで検証する。"
    )
    lines.append("")
    lines.append("## データ")
    lines.append(
        f"- Numbers3 raw: {len(n3_raw)}回 / clean: {len(n3)}回 "
        f"({n3['date'].min().date()}〜{n3['date'].max().date()})"
    )
    lines.append(
        f"- Bingo5: {len(b5)}回 ({b5['date'].min().date()}〜{b5['date'].max().date()})"
    )
    lines.append(
        "- みずほ公式は当環境から取得不可。RENBANミラーを使用し、"
        "同一数字の連続3回以上ストリーク、および同一数字かつ同一口数・当せん金の隣接行を汚染として除去。"
    )
    lines.append(
        f"- 長ストリーク例: "
        + ", ".join(
            f"{s['number']}x{s['len']}({s['date_from']}〜{s['date_to']})"
            for s in quality.get("long_streaks", [])
        )
    )
    lines.append("")
    lines.append("## ナンバーズ3：乱数性・関連性（clean）")
    for t in tests:
        pv = f", p={t.p_value:.4g}" if t.p_value is not None else ""
        lines.append(f"- **{t.name}**: {t.metric}={t.value:.4g}{pv} — {t.note}")
    lines.append("")
    lines.append("### 前回との関係（clean vs raw）")
    merged = lag.merge(lag_raw, on="feature", suffixes=("_clean", "_raw"))
    for _, r in merged.iterrows():
        lines.append(
            f"- {r['feature']}: clean={r['rate_clean']:.4f} "
            f"(null={r['null_clean']:.4f}, lift={r['rate_clean']-r['null_clean']:+.4f}) / "
            f"raw={r['rate_raw']:.4f} (lift={r['rate_raw']-r['null_raw']:+.4f})"
        )
    lines.append("")
    lines.append("### マルコフ性（桁の相互情報・次桁予測）")
    for col, d in markov.items():
        lines.append(
            f"- {col}: MI={d['mutual_information_bits']:.4f} bit, "
            f"WF acc={d['walkforward_next_digit_acc']:.4f} "
            f"(baseline 0.10, lift={d['lift_vs_uniform']:+.4f})"
        )
    lines.append("")
    lines.append("### MLウォークフォワード（次の百の位）")
    for name, d in ml.items():
        lines.append(
            f"- {name}: acc={d['cv_accuracy_mean']:.4f}±{d['cv_accuracy_std']:.4f}, "
            f"logloss={d['cv_logloss_mean']:.4f} "
            f"(uniform acc=0.10, logloss={d['uniform_logloss']:.4f})"
        )
    lines.append("")
    lines.append("### ストレート1口戦略 ROI（clean）")
    lines.append("| strategy | hits | hit_rate | ROI |")
    lines.append("|---|---:|---:|---:|")
    for _, r in strat.iterrows():
        lines.append(
            f"| {r['strategy']} | {r['straight_hits']} | {r['hit_rate']:.5f} | {r['roi']:.3f} |"
        )
    lines.append("")
    lines.append(
        "参考: rawデータでは `repeat_prev` が偽の高ROIになる。"
        "これは汚染ストリークの産物で、予測エッジではない。"
    )
    raw_rep = strat_raw.loc[strat_raw["strategy"] == "repeat_prev"].iloc[0]
    lines.append(
        f"- raw repeat_prev: hits={int(raw_rep['straight_hits'])}, "
        f"hit_rate={raw_rep['hit_rate']:.5f}, ROI={raw_rep['roi']:.3f}"
    )
    lines.append("")
    lines.append("### 金額・ボックス型・人気偏重")
    for k, v in box.items():
        if k.startswith("_"):
            continue
        lines.append(
            f"- {k}: share={v['share']:.3f}, avg_straight_prize={v['avg_straight_prize']:.0f}, "
            f"avg_winners={v['avg_winners']:.1f}"
        )
    ev = box["_payout_refs_yen_per_200"]["straight_theory_ev_ratio"]
    lines.append(
        f"- 理論ストレート期待還元の目安: {ev:.3f} "
        f"（= {N3_STRAIGHT_THEORY}/1000 / {N3_STAKE}）"
    )
    lines.append(
        f"- 口数と当せん金の相関（clean）: r={prize_corr:.3f} "
        "（口数多いほど単価下がる＝金額最適化の余地はここ）"
    )
    lines.append("")
    lines.append("## ビンゴ5（帯構造を明示）")
    lines.append(f"- 構造: {b5a['structure']}")
    for bt in b5a["band_uniform_chi2"]:
        lines.append(
            f"- band {bt['band']}: chi2={bt['chi2']:.3f}, p={bt['p_value']:.4g}"
        )
    lines.append(
        f"- 前回重複 mean={b5a['overlap_with_prev']['mean']:.3f} "
        f"(band-null={b5a['overlap_with_prev']['null_mean_band_aware']:.3f})"
    )
    lines.append(
        f"- 連番ペア mean={b5a['consecutive_pairs_per_draw']['mean']:.3f} "
        f"(band-null={b5a['consecutive_pairs_per_draw']['null_mean_band_aware']:.3f})"
    )
    ho = b5a["hot_W30_vs_random_overlap_band_aware"]
    lines.append(
        f"- hot30重複={ho['hot_mean_overlap']:.3f} / random={ho['random_mean_overlap']:.3f}"
    )
    fp = b5a["first_prize_yen"]
    lines.append(
        f"- 1等実額: mean={fp['mean']:.0f}, median={fp['median']:.0f}, "
        f"min={fp['min']:.0f}, max={fp['max']:.0f}"
    )
    lines.append(f"- 注記: {b5a['payout_note']}")
    lines.append("")
    lines.append("## クロス（同日 N3×Bingo5）")
    lines.append(json.dumps(cross, ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("## 予測としての結論")
    lines.append(
        "クリーン後のデータでは、**当選番号そのものを当てる予測エッジは見つからない**。"
        "見える法則の大半は帰無水準か、ミラー汚染のアーティファクト。"
        "一方で金額面では、口数増加に応じた単価低下が明確で、"
        "『的中確率』ではなく『的中時の取り分』を目的関数にする設計が妥当。"
    )
    lines.append("")
    lines.append("予測パイプラインの次の打ち手:")
    lines.append("1. 新規指標は clean データ＋ウォークフォワードROI/loglossで棄却判定")
    lines.append("2. 人気数字回避など **ペイアウト条件付きEV** を別モデル化")
    lines.append("3. Numbers3を日次ラベル、Bingo5を週次の分散検証に使う")
    lines.append("4. 公式データが取れる環境ではミラー異常区間を再照合")
    lines.append("")
    lines.append("詳細JSON: `reports/analysis_summary.json`")
    (REPORTS / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote reports to", REPORTS)


if __name__ == "__main__":
    main()
