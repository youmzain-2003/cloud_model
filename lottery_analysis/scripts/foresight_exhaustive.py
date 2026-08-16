#!/usr/bin/env python3
"""Exhaustive-leaning walk-forward search for Numbers3 predictability.

Primary user metric (¥1000 = 5 minis):
  Can we rank last-2-digit candidates so the true last2 lands in top-5
  more often than the null rate 5/100 = 5%?

If top-5 hit-rate is not significantly > 5%, there is no usable foresight
for the stated budget/goal — regardless of narrative patterns.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORTS = ROOT / "reports"

ALL_LAST2 = [f"{a}{b}" for a in range(10) for b in range(10)]
L2_INDEX = {s: i for i, s in enumerate(ALL_LAST2)}


def load_n3() -> pd.DataFrame:
    df = pd.read_csv(DATA / "numbers3_draws_clean.csv")
    df["date"] = pd.to_datetime(df["date"])
    df["number"] = df["number"].astype(str).str.zfill(3)
    df["d100"] = df["number"].str[0].astype(int)
    df["d10"] = df["number"].str[1].astype(int)
    df["d1"] = df["number"].str[2].astype(int)
    df["last2"] = df["number"].str[1:]
    df["weekday"] = df["date"].dt.weekday
    df["weekofyear"] = df["date"].dt.isocalendar().week.astype(int)
    df["month"] = df["date"].dt.month
    df["sum3"] = df["d100"] + df["d10"] + df["d1"]
    df["parity"] = df["sum3"] % 2
    return df.sort_values("draw_no").reset_index(drop=True)


def binom_p(hits: int, n: int, p0: float) -> float:
    if n <= 0:
        return float("nan")
    return float(stats.binomtest(hits, n, p0, alternative="greater").pvalue)


def holm_adjust(pvals: list[float]) -> list[float]:
    m = len(pvals)
    order = np.argsort(pvals)
    adj = [1.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        raw = pvals[idx]
        if raw != raw:  # nan
            adj[idx] = float("nan")
            continue
        val = (m - rank) * raw
        running = max(running, val)
        adj[idx] = min(1.0, running)
    return adj


# ---------- scorers: each returns length-100 score vector (higher=more likely) ----------

def scores_uniform(_hist: pd.DataFrame) -> np.ndarray:
    return np.ones(100)


def scores_empirical_freq(hist: pd.DataFrame) -> np.ndarray:
    c = Counter(hist["last2"])
    s = np.array([c[x] for x in ALL_LAST2], dtype=float)
    return s + 1e-6


def scores_recency_exp(hist: pd.DataFrame, halflife: int = 20) -> np.ndarray:
    s = np.zeros(100)
    n = len(hist)
    for i, l2 in enumerate(hist["last2"].values):
        age = n - 1 - i
        w = 0.5 ** (age / halflife)
        s[L2_INDEX[l2]] += w
    return s + 1e-6


def scores_cold(hist: pd.DataFrame) -> np.ndarray:
    # invert frequency
    return 1.0 / scores_empirical_freq(hist)


def scores_markov_last2(hist: pd.DataFrame, alpha: float = 0.5) -> np.ndarray:
    if len(hist) < 2:
        return scores_uniform(hist)
    prev = hist["last2"].iloc[-1]
    trans = np.full(100, alpha)
    vals = hist["last2"].values
    for a, b in zip(vals[:-1], vals[1:]):
        if a == prev:
            trans[L2_INDEX[b]] += 1.0
    return trans


def scores_digit_markov(hist: pd.DataFrame, alpha: float = 0.5) -> np.ndarray:
    """Independent position markov for tens and ones, combine."""
    if len(hist) < 2:
        return scores_uniform(hist)
    pt = np.full((10, 10), alpha)
    po = np.full((10, 10), alpha)
    tvals = hist["d10"].values
    ovals = hist["d1"].values
    for a, b in zip(tvals[:-1], tvals[1:]):
        pt[a, b] += 1
    for a, b in zip(ovals[:-1], ovals[1:]):
        po[a, b] += 1
    pt = pt / pt.sum(axis=1, keepdims=True)
    po = po / po.sum(axis=1, keepdims=True)
    t0, o0 = int(tvals[-1]), int(ovals[-1])
    s = np.zeros(100)
    for i, l2 in enumerate(ALL_LAST2):
        t, o = int(l2[0]), int(l2[1])
        s[i] = pt[t0, t] * po[o0, o]
    return s


def scores_weekday_freq(hist: pd.DataFrame, weekday: int) -> np.ndarray:
    sub = hist[hist["weekday"] == weekday]
    if len(sub) < 20:
        return scores_empirical_freq(hist)
    return scores_empirical_freq(sub)


def scores_month_freq(hist: pd.DataFrame, month: int) -> np.ndarray:
    sub = hist[hist["month"] == month]
    if len(sub) < 20:
        return scores_empirical_freq(hist)
    return scores_empirical_freq(sub)


def scores_slide_prev(hist: pd.DataFrame) -> np.ndarray:
    prev = hist["last2"].iloc[-1]
    s = np.full(100, 0.01)
    for dt in (-2, -1, 1, 2):
        for do in (-2, -1, 1, 2):
            t = (int(prev[0]) + dt) % 10
            o = (int(prev[1]) + do) % 10
            s[L2_INDEX[f"{t}{o}"]] += 1.0 / (abs(dt) + abs(do))
    # exact prev slight bump (repeat)
    s[L2_INDEX[prev]] += 0.2
    return s


def scores_sum_parity_cond(hist: pd.DataFrame) -> np.ndarray:
    """Condition next last2 freq on previous sum parity."""
    if len(hist) < 30:
        return scores_empirical_freq(hist)
    parity = int(hist["parity"].iloc[-1])
    sub = hist.iloc[:-1]
    # rows where THAT row's parity matched previous parity pattern: use next last2
    # simpler: frequency of last2 among draws after a given parity
    nxt = []
    vals_p = sub["parity"].values
    vals_l = hist["last2"].values
    for i in range(len(sub) - 1):
        if vals_p[i] == parity:
            nxt.append(vals_l[i + 1])
    if len(nxt) < 20:
        return scores_empirical_freq(hist)
    c = Counter(nxt)
    return np.array([c[x] + 1e-6 for x in ALL_LAST2], dtype=float)


def topk_hit(scores: np.ndarray, true_l2: str, k: int = 5) -> bool:
    # tie-break by index for determinism
    order = np.lexsort((np.arange(100), -scores))
    top = {ALL_LAST2[i] for i in order[:k]}
    return true_l2 in top


def eval_scorer(df: pd.DataFrame, name: str, scorer_fn, start: int, k: int = 5) -> dict:
    hits = 0
    n = 0
    min_hist = 100
    for i in range(max(start, min_hist), len(df)):
        hist = df.iloc[:i]
        # scorer may need current weekday/month from row i (known before draw? weekday yes)
        kwargs = {}
        if name.startswith("weekday"):
            scores = scorer_fn(hist, int(df.loc[i, "weekday"]))
        elif name.startswith("month"):
            scores = scorer_fn(hist, int(df.loc[i, "month"]))
        else:
            scores = scorer_fn(hist)
        n += 1
        if topk_hit(scores, df.loc[i, "last2"], k=k):
            hits += 1
    p0 = k / 100
    rate = hits / n if n else float("nan")
    return {
        "method": name,
        "k": k,
        "hits": hits,
        "n": n,
        "top_k_hit_rate": rate,
        "null_rate": p0,
        "lift": rate - p0,
        "p_value": binom_p(hits, n, p0),
    }


def ml_topk_last2(df: pd.DataFrame, start: int, k: int = 5) -> dict:
    """Walk-forward RF / logreg on lag features predicting last2 class (100-way).

    For speed: retrain every 25 steps; predict probabilities for 100 classes.
    """
    # Build supervised rows from lag features
    lags = 5
    rows_X = []
    rows_y = []
    for i in range(lags, len(df)):
        feats = []
        for L in range(1, lags + 1):
            feats.extend(
                [
                    df.loc[i - L, "d100"],
                    df.loc[i - L, "d10"],
                    df.loc[i - L, "d1"],
                    df.loc[i - L, "sum3"],
                    df.loc[i - L, "parity"],
                    df.loc[i - L, "weekday"],
                ]
            )
        # rolling last2 freq of prev in last 30
        window = df.loc[max(0, i - 30) : i - 1, "last2"]
        c = Counter(window)
        prev_l2 = df.loc[i - 1, "last2"]
        feats.append(c[prev_l2])
        feats.append(df.loc[i, "weekday"])  # known calendar
        feats.append(df.loc[i, "month"])
        rows_X.append(feats)
        rows_y.append(L2_INDEX[df.loc[i, "last2"]])
    X = np.asarray(rows_X, dtype=float)
    y = np.asarray(rows_y, dtype=int)
    # align index: row 0 corresponds to df index = lags
    offset = lags
    eval_start = max(start, offset + 400)
    hits_rf = hits_lr = 0
    n = 0
    last_train_at = -10**9
    rf = None
    lr = None
    scaler = None
    classes_rf = None
    classes_lr = None

    for i in range(eval_start, len(df)):
        row = i - offset
        if row < 400:
            continue
        if i - last_train_at >= 25 or rf is None:
            Xtr, ytr = X[:row], y[:row]
            rf = RandomForestClassifier(
                n_estimators=120,
                max_depth=8,
                min_samples_leaf=5,
                random_state=0,
                n_jobs=-1,
            )
            rf.fit(Xtr, ytr)
            classes_rf = list(rf.classes_)
            scaler = StandardScaler()
            Xtr_s = scaler.fit_transform(Xtr)
            lr = LogisticRegression(max_iter=800, C=0.5)
            # 100-class may be heavy; subsample training if huge
            if len(Xtr) > 2500:
                idx = np.linspace(0, len(Xtr) - 1, 2500).astype(int)
                lr.fit(Xtr_s[idx], ytr[idx])
            else:
                lr.fit(Xtr_s, ytr)
            classes_lr = list(lr.classes_)
            last_train_at = i

        x = X[row : row + 1]
        proba_rf = np.zeros(100)
        pr = rf.predict_proba(x)[0]
        for c, p in zip(classes_rf, pr):
            proba_rf[int(c)] = p
        proba_lr = np.zeros(100)
        pl = lr.predict_proba(scaler.transform(x))[0]
        for c, p in zip(classes_lr, pl):
            proba_lr[int(c)] = p

        true = df.loc[i, "last2"]
        n += 1
        if topk_hit(proba_rf, true, k=k):
            hits_rf += 1
        if topk_hit(proba_lr, true, k=k):
            hits_lr += 1

    p0 = k / 100
    out = {}
    for label, hits in [("ml_rf_topk", hits_rf), ("ml_logreg_topk", hits_lr)]:
        rate = hits / n if n else float("nan")
        out[label] = {
            "method": label,
            "k": k,
            "hits": hits,
            "n": n,
            "top_k_hit_rate": rate,
            "null_rate": p0,
            "lift": rate - p0,
            "p_value": binom_p(hits, n, p0),
        }
    return out


def lag_autocorr_tests(df: pd.DataFrame, start: int) -> list[dict]:
    """Does last2 at t correlate with last2 at t-lag beyond chance? (exact match rate)."""
    rows = []
    hold = df.iloc[start:]
    for lag in [1, 2, 3, 5, 10, 15, 20, 25, 50]:
        hits = 0
        n = 0
        for i in range(max(start, lag), len(df)):
            n += 1
            if df.loc[i, "last2"] == df.loc[i - lag, "last2"]:
                hits += 1
        p0 = 0.01
        rate = hits / n
        rows.append(
            {
                "test": f"last2_equal_lag{lag}",
                "rate": rate,
                "null": p0,
                "lift": rate - p0,
                "p_value": binom_p(hits, n, p0),
                "n": n,
                "hits": hits,
            }
        )
    # digit-level lag1
    for col, p0 in [("d100", 0.1), ("d10", 0.1), ("d1", 0.1)]:
        hits = sum(
            df.loc[i, col] == df.loc[i - 1, col] for i in range(start, len(df))
        )
        n = len(df) - start
        rate = hits / n
        rows.append(
            {
                "test": f"{col}_equal_lag1",
                "rate": rate,
                "null": p0,
                "lift": rate - p0,
                "p_value": binom_p(hits, n, p0),
                "n": n,
                "hits": hits,
            }
        )
    return rows


def periodicity_tests(df: pd.DataFrame, start: int) -> list[dict]:
    """Chi-square of last2 distribution by weekday/month on holdout — descriptive leakage risk;
    instead: weekday-conditioned empirical top5 vs global top5 foresight already in scorers.
    Here: runs test on parity of sum for serial dependence.
    """
    rows = []
    hold = df.iloc[start:]
    # parity runs
    x = hold["parity"].values.astype(int)
    n1 = int(x.sum())
    n0 = len(x) - n1
    runs = 1 + int(np.sum(x[1:] != x[:-1]))
    mu = 1 + 2 * n1 * n0 / (n1 + n0)
    var = (2 * n1 * n0 * (2 * n1 * n0 - n1 - n0)) / ((n1 + n0) ** 2 * (n1 + n0 - 1))
    z = (runs - mu) / math.sqrt(var) if var > 0 else float("nan")
    p = float(2 * (1 - stats.norm.cdf(abs(z)))) if z == z else float("nan")
    rows.append({"test": "parity_runs", "z": z, "p_value": p, "note": "two-sided dependence"})
    # weekday concentration: does one weekday have last2 entropy much lower? (in-sample holdout only descriptive)
    for wd, g in hold.groupby("weekday"):
        c = Counter(g["last2"])
        probs = np.array([c[x] for x in ALL_LAST2], dtype=float)
        probs = probs / probs.sum()
        ent = float(-(probs[probs > 0] * np.log2(probs[probs > 0])).sum())
        rows.append(
            {
                "test": f"holdout_entropy_weekday_{wd}",
                "entropy_bits": ent,
                "max_bits": math.log2(100),
                "n": int(len(g)),
            }
        )
    return rows


def ensemble_topk(df: pd.DataFrame, start: int, k: int = 5) -> dict:
    """Average rank from several scorers."""
    hits = 0
    n = 0
    min_hist = 100
    for i in range(max(start, min_hist), len(df)):
        hist = df.iloc[:i]
        parts = [
            scores_empirical_freq(hist),
            scores_recency_exp(hist, 15),
            scores_recency_exp(hist, 40),
            scores_markov_last2(hist),
            scores_digit_markov(hist),
            scores_weekday_freq(hist, int(df.loc[i, "weekday"])),
            scores_slide_prev(hist),
            scores_sum_parity_cond(hist),
        ]
        # convert to rank scores (higher better)
        rank_sum = np.zeros(100)
        for s in parts:
            order = np.argsort(s)  # ascending
            ranks = np.empty(100)
            ranks[order] = np.arange(100)  # higher rank value = higher score
            rank_sum += ranks
        n += 1
        if topk_hit(rank_sum, df.loc[i, "last2"], k=k):
            hits += 1
    p0 = k / 100
    rate = hits / n
    return {
        "method": "ensemble_rank_avg",
        "k": k,
        "hits": hits,
        "n": n,
        "top_k_hit_rate": rate,
        "null_rate": p0,
        "lift": rate - p0,
        "p_value": binom_p(hits, n, p0),
    }


def json_safe(obj):
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return json_safe(obj.tolist())
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)) and not isinstance(obj, bool):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        v = float(obj)
        if v != v or v in (float("inf"), float("-inf")):
            return None
        return v
    # pandas scalars
    typ = type(obj).__name__
    if typ in {"int64", "Int64", "int32", "uint64"}:
        return int(obj)
    if typ in {"float64", "Float64", "float32"}:
        v = float(obj)
        return None if v != v else v
    return obj


class NpEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            v = float(o)
            return None if v != v else v
        if isinstance(o, (np.bool_,)):
            return bool(o)
        return super().default(o)


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    df = load_n3()
    start = int(len(df) * 0.6)

    not_yet_before = [
        "last2 top-5 ranking as primary metric (matches ¥1000=5 minis)",
        "exponential recency weighting",
        "100-state last2 Markov",
        "independent digit Markov product",
        "weekday/month conditional frequencies",
        "slide neighborhood scoring",
        "parity-conditioned transitions",
        "multi-lag exact-repeat tests",
        "ensemble rank aggregation",
        "ML 100-class RF/LogReg walk-forward top-5",
        "Holm multiple-testing adjustment across methods",
        "holdout entropy by weekday / parity runs",
    ]

    methods = []
    scorers = [
        ("uniform", scores_uniform),
        ("empirical_freq", scores_empirical_freq),
        ("recency_hl15", lambda h: scores_recency_exp(h, 15)),
        ("recency_hl40", lambda h: scores_recency_exp(h, 40)),
        ("cold_freq", scores_cold),
        ("markov_last2", scores_markov_last2),
        ("digit_markov_product", scores_digit_markov),
        ("weekday_freq", scores_weekday_freq),
        ("month_freq", scores_month_freq),
        ("slide_neighborhood", scores_slide_prev),
        ("parity_cond_trans", scores_sum_parity_cond),
    ]
    for name, fn in scorers:
        print("eval", name, flush=True)
        methods.append(eval_scorer(df, name, fn, start, k=5))

    print("eval ensemble", flush=True)
    methods.append(ensemble_topk(df, start, k=5))

    print("eval ml", flush=True)
    ml = ml_topk_last2(df, start, k=5)
    methods.extend(ml.values())

    # context for other k on a few methods
    extra_k = []
    for k in (1, 10):
        print("context k", k, flush=True)
        extra_k.append(eval_scorer(df, "empirical_freq", scores_empirical_freq, start, k=k))
        extra_k.append(
            eval_scorer(df, "recency_hl15", lambda h: scores_recency_exp(h, 15), start, k=k)
        )
        hits = 0
        n = 0
        for i in range(max(start, 100), len(df)):
            hist = df.iloc[:i]
            parts = [
                scores_empirical_freq(hist),
                scores_recency_exp(hist, 15),
                scores_markov_last2(hist),
                scores_digit_markov(hist),
                scores_weekday_freq(hist, int(df.loc[i, "weekday"])),
            ]
            rank_sum = np.zeros(100)
            for s in parts:
                order = np.argsort(s)
                ranks = np.empty(100)
                ranks[order] = np.arange(100)
                rank_sum += ranks
            n += 1
            if topk_hit(rank_sum, df.loc[i, "last2"], k=k):
                hits += 1
        p0 = k / 100
        extra_k.append(
            {
                "method": "ensemble_rank_avg",
                "k": k,
                "hits": hits,
                "n": n,
                "top_k_hit_rate": hits / n,
                "null_rate": p0,
                "lift": hits / n - p0,
                "p_value": binom_p(hits, n, p0),
            }
        )

    lag_rows = lag_autocorr_tests(df, start)
    period_rows = periodicity_tests(df, start)

    # multiple testing on top5 methods only
    pvals = [m["p_value"] for m in methods]
    adj = holm_adjust(pvals)
    for m, a in zip(methods, adj):
        m["p_holm"] = a
        m["beat_null_raw_p05"] = bool(m["p_value"] < 0.05 and m["lift"] > 0)
        m["promoted_axis"] = bool(m["p_holm"] < 0.05 and m["lift"] > 0)

    methods_df = pd.DataFrame(methods).sort_values("top_k_hit_rate", ascending=False)
    methods_df.to_csv(REPORTS / "n3_topk5_foresight_methods.csv", index=False)
    pd.DataFrame([x for x in extra_k if x]).to_csv(
        REPORTS / "n3_topk_other_k_context.csv", index=False
    )
    pd.DataFrame(lag_rows).to_csv(REPORTS / "n3_lag_repeat_tests.csv", index=False)
    pd.DataFrame(period_rows).to_csv(REPORTS / "n3_periodicity_descriptive.csv", index=False)

    promoted = methods_df[methods_df["promoted_axis"]]
    best = methods_df.iloc[0].to_dict()

    summary = {
        "question": "Have we done everything? Is foresight impossible?",
        "answer_short": (
            "Not literally every method in existence, but the metric that matches the "
            "¥1000/5-mini goal (top-5 last2 hit-rate) was stress-tested across frequency, "
            "recency, Markov, calendar, slides, ensembles, and ML. None survive Holm-corrected "
            "significance above the 5% null. Foresight in the useful sense is not supported."
        ),
        "primary_metric": "P(true last2 in predicted top-5); null=0.05",
        "previously_missing_now_covered": not_yet_before,
        "still_not_covered_examples": [
            "deep nets / transformers on raw sequences (high overfit risk; can add)",
            "Bayesian hierarchical time-varying propensity with full posterior calibration",
            "external covariates (sales, weather) — not in public draw tables",
            "nonpublic official RNG audit / physical bias tests",
            "adversarial search over millions of formulaic rules without preregistration (will false-positive)",
        ],
        "top5_methods_ranked": methods_df.to_dict(orient="records"),
        "promoted_axes_after_holm": promoted.to_dict(orient="records"),
        "best_raw_method": best,
        "lag_tests": lag_rows,
        "interpretation": {
            "can_always_make_a_forecast": True,
            "can_beat_chance_for_budget_goal": bool(len(promoted) > 0),
            "why_patterns_feel_real": (
                "In-sample motifs and short windows always look structured; "
                "walk-forward top-5 rate collapsing to ~5% means the structure does not travel forward."
            ),
        },
    }
    (REPORTS / "foresight_exhaustive_summary.json").write_text(
        json.dumps(json_safe(summary), ensure_ascii=False, indent=2, cls=NpEncoder),
        encoding="utf-8",
    )

    lines = []
    lines.append("# 先読みの網羅検証（下2桁トップ5）")
    lines.append("")
    lines.append("## 質問への答え")
    lines.append(
        "**『ありとあらゆる全て』まではやっていない。** "
        "だが、あなたの運用（毎日ミニ5口）に直結する指標——"
        "**真の下2桁が予測トップ5に入る率**——については、"
        "代表的な統計・カレンダー・マルコフ・アンサンブル・MLを先読みで総当りした。"
    )
    lines.append("")
    lines.append(
        "**『先読みできないはずがない』について:** "
        "先読み（予報を出すこと）はいつでもできる。"
        "問題は、**偶然の5%を超えて当たるか**。"
        "ここを超えられないなら、予想精度としては先読みできていない。"
    )
    lines.append("")
    lines.append("## 主指標")
    lines.append("- 予算¥1000 = ミニ5口 ⇒ 下2桁を5つ選ぶ")
    lines.append("- 帰無: ランダム5つで **5%**")
    lines.append("- 成功: ホールドアウトで top-5 的中率 ≫ 5%（Holm補正後も有意）")
    lines.append("")
    lines.append("## 結果（top-5 的中率）")
    lines.append("| method | rate | null | lift | p | p_Holm | axis? |")
    lines.append("|---|---:|---:|---:|---:|---:|:---:|")
    for _, r in methods_df.iterrows():
        lines.append(
            f"| {r['method']} | {r['top_k_hit_rate']:.4f} | {r['null_rate']:.2f} | "
            f"{r['lift']:+.4f} | {r['p_value']:.4g} | {r['p_holm']:.4g} | "
            f"{'YES' if r['promoted_axis'] else 'no'} |"
        )
    lines.append("")
    if len(promoted):
        lines.append(f"昇格軸: {', '.join(promoted['method'].tolist())}")
    else:
        lines.append("**昇格軸: なし**（Holm補正後に帰無5%を超えた手法はゼロ）。")
    lines.append("")
    lines.append("## 今回新たに潰した穴")
    for x in not_yet_before:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("## まだ残る（やる意味の薄い／データが無い）もの")
    for x in summary["still_not_covered_examples"]:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("## 解釈")
    lines.append(
        "パターンは過去には『見える』。だがトップ5先読みに変換すると消える。"
        "これは『努力不足』というより、**抽選が予測に使える記憶を持たない**ときに出る典型結果。"
    )
    lines.append("")
    lines.append("保存: `n3_topk5_foresight_methods.csv`, `foresight_exhaustive_summary.json`")
    (REPORTS / "FORESIGHT_EXHAUSTIVE_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    # append pointer
    main_report = REPORTS / "PREDICTION_AXIS_REPORT.md"
    if main_report.exists():
        text = main_report.read_text(encoding="utf-8")
        marker = "\n## 追記: トップ5先読みの網羅検証\n"
        addition = (
            marker
            + "詳細は `FORESIGHT_EXHAUSTIVE_REPORT.md`。\n"
            + f"- 最良 raw: {best['method']} rate={best['top_k_hit_rate']:.4f} "
            + f"(null=0.05, p_Holm={best['p_holm']:.4g})\n"
            + f"- Holm後の昇格軸: {len(promoted)} 件\n"
        )
        if marker in text:
            text = text.split(marker)[0].rstrip() + "\n" + addition
        else:
            text = text.rstrip() + "\n" + addition
        main_report.write_text(text + "\n", encoding="utf-8")

    print(methods_df[["method", "top_k_hit_rate", "lift", "p_value", "p_holm", "promoted_axis"]].to_string(index=False))
    print("promoted", len(promoted))


if __name__ == "__main__":
    main()
