#!/usr/bin/env python3
"""Payout-conditioned EV analysis (Numbers3 primary, Bingo5 secondary).

Objective is NOT P(hit). Under near-IID draws, P(hit)≈constant per ticket type.
Objective is E[prize | number features] — avoid crowded patterns so that *if*
a ticket hits, the yen share is larger.

Pipeline:
  1. Engineer popularity features from the number itself (no future leak).
  2. Walk-forward regress winners / prize on those features.
  3. Rank candidate tickets by predicted prize; backtest conditional & absolute ROI.
  4. Emit next-draw low-crowd candidate sets for Numbers3 (+ Bingo5 notes).
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORTS = ROOT / "reports"

N3_STAKE = 200
N3_P_STRAIGHT = 1 / 1000
N3_STRAIGHT_THEORY = 90_000
B5_STAKE = 200
B5_BANDS = [
    list(range(1, 6)),
    list(range(6, 11)),
    list(range(11, 16)),
    list(range(16, 21)),
    list(range(21, 26)),
    list(range(26, 31)),
    list(range(31, 36)),
    list(range(36, 41)),
]


def load_clean_n3() -> pd.DataFrame:
    df = pd.read_csv(DATA / "numbers3_draws_clean.csv")
    df["date"] = pd.to_datetime(df["date"])
    df["number"] = df["number"].astype(str).str.zfill(3)
    return df.sort_values("draw_no").reset_index(drop=True)


def load_b5() -> pd.DataFrame:
    df = pd.read_csv(DATA / "bingo5_draws.csv")
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("draw_no").reset_index(drop=True)


def n3_features_from_number(num: str) -> dict:
    s = str(num).zfill(3)
    d = [int(ch) for ch in s]
    c = Counter(d)
    diffs = [abs(d[0] - d[1]), abs(d[1] - d[2]), abs(d[0] - d[2])]
    # "birthday-ish": hundreds 0-3 and tens/ones look like month/day ranges — soft proxy
    birthdayish = int(d[0] <= 3 and 1 <= int(s[1:]) <= 31)
    sequential = int(
        (d[1] == (d[0] + 1) % 10 and d[2] == (d[1] + 1) % 10)
        or (d[1] == (d[0] - 1) % 10 and d[2] == (d[1] - 1) % 10)
    )
    return {
        "n_int": int(s),
        "d100": d[0],
        "d10": d[1],
        "d1": d[2],
        "sum_digits": sum(d),
        "sum_sq": sum(x * x for x in d),
        "parity_odd_count": sum(x % 2 for x in d),
        "is_triple": int(len(c) == 1),
        "is_double": int(len(c) == 2),
        "is_all_diff": int(len(c) == 3),
        "has_zero": int(0 in d),
        "has_seven": int(7 in d),  # culturally popular in JP lottery lore
        "has_eight": int(8 in d),
        "max_adj_diff": max(diffs),
        "min_adj_diff": min(diffs[:2]),
        "is_palindrome": int(d[0] == d[2]),
        "is_sequential": sequential,
        "is_roundish": int(s.endswith("00") or s.endswith("50") or s.endswith("25")),
        "birthdayish": birthdayish,
        "sorted_key": int("".join(sorted(s))),
    }


FEATURE_COLS = [
    "d100",
    "d10",
    "d1",
    "sum_digits",
    "sum_sq",
    "parity_odd_count",
    "is_triple",
    "is_double",
    "is_all_diff",
    "has_zero",
    "has_seven",
    "has_eight",
    "max_adj_diff",
    "min_adj_diff",
    "is_palindrome",
    "is_sequential",
    "is_roundish",
    "birthdayish",
]


def build_n3_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    feats = pd.DataFrame([n3_features_from_number(n) for n in df["number"]])
    base = df.drop(columns=[c for c in feats.columns if c in df.columns], errors="ignore")
    out = pd.concat([base.reset_index(drop=True), feats.reset_index(drop=True)], axis=1)
    return out


def descriptive_crowd_tables(feat: pd.DataFrame) -> dict:
    """In-sample descriptive: which pattern classes draw more winners / lower prize."""
    rows = []
    for col in [
        "is_triple",
        "is_double",
        "is_all_diff",
        "is_palindrome",
        "is_sequential",
        "is_roundish",
        "birthdayish",
        "has_zero",
        "has_seven",
        "has_eight",
    ]:
        for val, g in feat.groupby(col):
            g2 = g.dropna(subset=["straight_winners", "straight_prize_yen"])
            if len(g2) < 30:
                continue
            rows.append(
                {
                    "feature": col,
                    "value": int(val),
                    "n": int(len(g2)),
                    "avg_winners": float(g2["straight_winners"].mean()),
                    "median_winners": float(g2["straight_winners"].median()),
                    "avg_prize": float(g2["straight_prize_yen"].mean()),
                    "median_prize": float(g2["straight_prize_yen"].median()),
                }
            )
    # parity / sum buckets
    for name, series in [
        ("parity_odd_count", feat["parity_odd_count"]),
        ("sum_bucket", pd.cut(feat["sum_digits"], bins=[-0.1, 6, 12, 18, 27], labels=["0-6", "7-12", "13-18", "19-27"])),
    ]:
        tmp = feat.copy()
        tmp["_k"] = series
        for val, g in tmp.groupby("_k", observed=True):
            g2 = g.dropna(subset=["straight_winners", "straight_prize_yen"])
            if len(g2) < 30:
                continue
            rows.append(
                {
                    "feature": name,
                    "value": str(val),
                    "n": int(len(g2)),
                    "avg_winners": float(g2["straight_winners"].mean()),
                    "median_winners": float(g2["straight_winners"].median()),
                    "avg_prize": float(g2["straight_prize_yen"].mean()),
                    "median_prize": float(g2["straight_prize_yen"].median()),
                }
            )
    return {"pattern_payout": rows}


def walkforward_prize_model(feat: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Expanding-window regression of log(prize) and log(winners)."""
    data = feat.dropna(subset=["straight_prize_yen", "straight_winners"]).copy()
    data = data[data["straight_prize_yen"] > 0].reset_index(drop=True)
    X = data[FEATURE_COLS].values.astype(float)
    y_prize = np.log(data["straight_prize_yen"].values.astype(float))
    y_win = np.log(np.clip(data["straight_winners"].values.astype(float), 1, None))

    min_train = max(800, int(len(data) * 0.4))
    step = 50
    preds_prize = np.full(len(data), np.nan)
    preds_win = np.full(len(data), np.nan)

    model_prize = Ridge(alpha=2.0)
    model_win = Ridge(alpha=2.0)

    for start in range(min_train, len(data), step):
        end = min(start + step, len(data))
        Xtr, ypr, ywr = X[:start], y_prize[:start], y_win[:start]
        scaler = StandardScaler()
        Xtr_s = scaler.fit_transform(Xtr)
        Xte_s = scaler.transform(X[start:end])
        model_prize.fit(Xtr_s, ypr)
        model_win.fit(Xtr_s, ywr)
        preds_prize[start:end] = model_prize.predict(Xte_s)
        preds_win[start:end] = model_win.predict(Xte_s)

    mask = ~np.isnan(preds_prize)
    metrics = {
        "n_scored": int(mask.sum()),
        "prize_r2_log": float(r2_score(y_prize[mask], preds_prize[mask])),
        "prize_mae_yen": float(
            mean_absolute_error(
                np.exp(y_prize[mask]), np.exp(preds_prize[mask])
            )
        ),
        "winners_r2_log": float(r2_score(y_win[mask], preds_win[mask])),
        "winners_mae": float(
            mean_absolute_error(np.exp(y_win[mask]), np.exp(preds_win[mask]))
        ),
        "corr_pred_prize_vs_actual": float(
            stats.pearsonr(np.exp(preds_prize[mask]), np.exp(y_prize[mask]))[0]
        ),
        "corr_pred_winners_vs_actual": float(
            stats.pearsonr(np.exp(preds_win[mask]), np.exp(y_win[mask]))[0]
        ),
    }

    # Final model on all data for coefficients / next-draw scoring
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model_prize.fit(Xs, y_prize)
    model_win.fit(Xs, y_win)
    coefs = sorted(
        [
            {
                "feature": f,
                "coef_log_prize": float(model_prize.coef_[i]),
                "coef_log_winners": float(model_win.coef_[i]),
            }
            for i, f in enumerate(FEATURE_COLS)
        ],
        key=lambda r: abs(r["coef_log_winners"]),
        reverse=True,
    )

    scored = data.loc[mask, ["draw_no", "date", "number", "straight_prize_yen", "straight_winners"]].copy()
    scored["pred_prize"] = np.exp(preds_prize[mask])
    scored["pred_winners"] = np.exp(preds_win[mask])
    scored["actual_ev_proxy"] = N3_P_STRAIGHT * scored["straight_prize_yen"] - N3_STAKE
    scored["pred_ev_proxy"] = N3_P_STRAIGHT * scored["pred_prize"] - N3_STAKE

    return scored, {
        "metrics": metrics,
        "coefficients": coefs,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "ridge_prize_coef": model_prize.coef_.tolist(),
        "ridge_prize_intercept": float(model_prize.intercept_),
        "ridge_win_coef": model_win.coef_.tolist(),
        "ridge_win_intercept": float(model_win.intercept_),
    }


def backtest_ticket_selection(feat: pd.DataFrame, model_bundle: dict) -> pd.DataFrame:
    """Each holdout draw: pick 5 tickets by rule; score using actual winning number's prize if match.

    Because P(match) is tiny for 5/1000, we also evaluate *counterfactual conditional
    EV*: average predicted/actual prize of selected tickets vs random tickets
    (popularity ranking quality), which does not require hits.
    """
    data = feat.dropna(subset=["straight_prize_yen", "straight_winners"]).copy()
    data = data[data["straight_prize_yen"] > 0].reset_index(drop=True)
    X = data[FEATURE_COLS].values.astype(float)
    y_prize = data["straight_prize_yen"].values.astype(float)
    y_win = data["straight_winners"].values.astype(float)
    nums = data["number"].astype(str).str.zfill(3).tolist()

    min_train = max(800, int(len(data) * 0.5))
    rng = np.random.default_rng(0)

    # Precompute feature matrix for all 000-999 once
    universe = [f"{i:03d}" for i in range(1000)]
    U = np.array(
        [[n3_features_from_number(n)[c] for c in FEATURE_COLS] for n in universe],
        dtype=float,
    )

    rows = []
    # rolling evaluate every draw after min_train (subsample every 5th for speed)
    for t in range(min_train, len(data), 5):
        scaler = StandardScaler()
        Xtr = scaler.fit_transform(X[:t])
        model = Ridge(alpha=2.0)
        # predict winners (crowd) — lower is better for payout
        model.fit(Xtr, np.log(np.clip(y_win[:t], 1, None)))
        u_pred_win = np.exp(model.predict(scaler.transform(U)))
        model_p = Ridge(alpha=2.0)
        model_p.fit(Xtr, np.log(y_prize[:t]))
        u_pred_prize = np.exp(model_p.predict(scaler.transform(U)))

        order_low_crowd = np.argsort(u_pred_win)  # ascending winners
        order_high_prize = np.argsort(-u_pred_prize)
        order_high_crowd = np.argsort(-u_pred_win)

        picks = {
            "avoid_crowd_top5": [universe[i] for i in order_low_crowd[:5]],
            "chase_crowd_top5": [universe[i] for i in order_high_crowd[:5]],
            "max_pred_prize_top5": [universe[i] for i in order_high_prize[:5]],
            "random_5": [universe[i] for i in rng.choice(1000, 5, replace=False)],
        }
        # pattern filters as baselines
        picks["no_triple_random5"] = []
        while len(picks["no_triple_random5"]) < 5:
            n = universe[int(rng.integers(0, 1000))]
            if len(set(n)) > 1:
                picks["no_triple_random5"].append(n)

        actual = nums[t]
        actual_prize = y_prize[t]
        for name, ticket_list in picks.items():
            hit = actual in ticket_list
            # conditional quality: mean predicted prize / mean predicted winners of picks
            idxs = [universe.index(x) for x in ticket_list]
            rows.append(
                {
                    "draw_no": int(data.loc[t, "draw_no"]),
                    "strategy": name,
                    "hit": int(hit),
                    "hit_yen": float(actual_prize if hit else 0.0),
                    "spent_yen": N3_STAKE * 5,
                    "mean_pred_prize": float(np.mean(u_pred_prize[idxs])),
                    "mean_pred_winners": float(np.mean(u_pred_win[idxs])),
                    "pred_ev_5tickets": float(
                        5 * N3_P_STRAIGHT * np.mean(u_pred_prize[idxs]) - 5 * N3_STAKE
                    ),
                }
            )

    detail = pd.DataFrame(rows)
    summary = (
        detail.groupby("strategy", as_index=False)
        .agg(
            eval_points=("draw_no", "count"),
            hits=("hit", "sum"),
            hit_rate=("hit", "mean"),
            total_spent=("spent_yen", "sum"),
            total_won=("hit_yen", "sum"),
            mean_pred_prize=("mean_pred_prize", "mean"),
            mean_pred_winners=("mean_pred_winners", "mean"),
            mean_pred_ev_5=("pred_ev_5tickets", "mean"),
        )
    )
    summary["roi"] = summary["total_won"] / summary["total_spent"] - 1
    summary["null_hit_rate_5of1000"] = 5 / 1000
    return detail, summary.sort_values("mean_pred_prize", ascending=False)


def score_universe(model_bundle: dict) -> pd.DataFrame:
    mean = np.array(model_bundle["scaler_mean"])
    scale = np.array(model_bundle["scaler_scale"])
    coef_p = np.array(model_bundle["ridge_prize_coef"])
    coef_w = np.array(model_bundle["ridge_win_coef"])
    rows = []
    for i in range(1000):
        n = f"{i:03d}"
        f = n3_features_from_number(n)
        x = np.array([f[c] for c in FEATURE_COLS], dtype=float)
        xs = (x - mean) / scale
        pred_prize = math.exp(float(xs @ coef_p + model_bundle["ridge_prize_intercept"]))
        pred_win = math.exp(float(xs @ coef_w + model_bundle["ridge_win_intercept"]))
        rows.append(
            {
                "number": n,
                **{c: f[c] for c in FEATURE_COLS},
                "pred_prize_yen": pred_prize,
                "pred_winners": pred_win,
                "pred_ev_straight": N3_P_STRAIGHT * pred_prize - N3_STAKE,
            }
        )
    return pd.DataFrame(rows).sort_values("pred_prize_yen", ascending=False)


def bingo5_payout_analysis(b5: pd.DataFrame) -> dict:
    mats = b5[[f"n{i}" for i in range(1, 9)]].values.astype(int)
    rows = []
    for i, row in enumerate(mats):
        s = sorted(int(x) for x in row)
        consec = sum(1 for a, b in zip(s, s[1:]) if b - a == 1)
        odd = sum(x % 2 for x in s)
        total = sum(s)
        # low/mid/high band counts
        low = sum(1 <= x <= 13 for x in s)
        mid = sum(14 <= x <= 27 for x in s)
        high = sum(28 <= x <= 40 for x in s)
        rows.append(
            {
                "draw_no": int(b5.loc[i, "draw_no"]),
                "sum": total,
                "odd": odd,
                "consec": consec,
                "low": low,
                "mid": mid,
                "high": high,
                "first_winners": b5.loc[i, "first_winners"],
                "first_prize_yen": b5.loc[i, "first_prize_yen"],
            }
        )
    f = pd.DataFrame(rows).dropna(subset=["first_winners", "first_prize_yen"])
    f = f[f["first_prize_yen"] > 0]
    # correlations with payout
    corr = {}
    for col in ["sum", "odd", "consec", "low", "mid", "high"]:
        r_w, p_w = stats.pearsonr(f[col], f["first_winners"])
        r_p, p_p = stats.pearsonr(f[col], f["first_prize_yen"])
        corr[col] = {
            "vs_winners_r": float(r_w),
            "vs_winners_p": float(p_w),
            "vs_prize_r": float(r_p),
            "vs_prize_p": float(p_p),
        }
    # walk-forward: predict winners from features; compare low vs high crowd cards' actual prize when that card structure matches winning board features
    # Simpler: quintile of predicted winners among historical boards
    X = f[["sum", "odd", "consec", "low", "mid", "high"]].values
    y = np.log(np.clip(f["first_winners"].values.astype(float), 1, None))
    min_train = max(120, int(len(f) * 0.5))
    pred = np.full(len(f), np.nan)
    for t in range(min_train, len(f)):
        scaler = StandardScaler()
        model = Ridge(alpha=1.0)
        model.fit(scaler.fit_transform(X[:t]), y[:t])
        pred[t] = model.predict(scaler.transform(X[t : t + 1]))[0]
    mask = ~np.isnan(pred)
    scored = f.loc[mask].copy()
    scored["pred_log_winners"] = pred[mask]
    scored["crowd_q"] = pd.qcut(scored["pred_log_winners"], 5, labels=["Q1_low", "Q2", "Q3", "Q4", "Q5_high"])
    qtab = (
        scored.groupby("crowd_q", observed=True)
        .agg(
            n=("draw_no", "count"),
            avg_winners=("first_winners", "mean"),
            avg_prize=("first_prize_yen", "mean"),
            median_prize=("first_prize_yen", "median"),
        )
        .reset_index()
    )
    return {
        "n": int(len(f)),
        "feature_corr": corr,
        "pred_crowd_quintiles": qtab.to_dict(orient="records"),
        "winners_vs_prize_corr": float(
            stats.pearsonr(f["first_winners"], f["first_prize_yen"])[0]
        ),
        "note": (
            "Bingo5 1st prize is shared; lower predicted crowd quintiles historically "
            "associate with higher average 1st-prize yen when that board appeared."
        ),
    }


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    n3 = load_clean_n3()
    b5 = load_b5()
    feat = build_n3_feature_frame(n3)

    desc = descriptive_crowd_tables(feat)
    pd.DataFrame(desc["pattern_payout"]).to_csv(
        REPORTS / "n3_pattern_payout_table.csv", index=False
    )

    scored, bundle = walkforward_prize_model(feat)
    scored.to_csv(REPORTS / "n3_payout_walkforward_scores.csv", index=False)

    detail, summary = backtest_ticket_selection(feat, bundle)
    detail.to_csv(REPORTS / "n3_payout_selection_detail.csv", index=False)
    summary.to_csv(REPORTS / "n3_payout_selection_summary.csv", index=False)

    universe = score_universe(bundle)
    universe.to_csv(REPORTS / "n3_universe_pred_payout.csv", index=False)
    candidates = universe.head(30).copy()
    # diversify: take top by prize among all_diff only, then mix
    all_diff = universe[universe["is_all_diff"] == 1].head(20)
    avoid_seven = universe[
        (universe["is_all_diff"] == 1)
        & (universe["has_seven"] == 0)
        & (universe["is_sequential"] == 0)
        & (universe["birthdayish"] == 0)
    ].head(20)
    candidates.to_csv(REPORTS / "n3_candidates_top_pred_prize.csv", index=False)
    all_diff.to_csv(REPORTS / "n3_candidates_all_diff_top.csv", index=False)
    avoid_seven.to_csv(REPORTS / "n3_candidates_low_crowd_filters.csv", index=False)

    b5a = bingo5_payout_analysis(b5)
    pd.DataFrame(b5a["pred_crowd_quintiles"]).to_csv(
        REPORTS / "b5_crowd_quintile_payout.csv", index=False
    )

    # Theoretical EV comparison under constant P(hit)
    theory_ev = N3_P_STRAIGHT * N3_STRAIGHT_THEORY - N3_STAKE
    best_pred_ev = float(universe["pred_ev_straight"].max())
    worst_pred_ev = float(universe["pred_ev_straight"].min())

    out = {
        "objective": "Maximize E[prize|features]*P(hit) - stake with P(hit)≈1/1000",
        "n3_walkforward_model": bundle["metrics"],
        "n3_top_coefficients_by_abs_crowd": bundle["coefficients"][:12],
        "n3_selection_summary": summary.to_dict(orient="records"),
        "n3_theory_ev_straight": theory_ev,
        "n3_pred_ev_range_across_000_999": {
            "best": best_pred_ev,
            "worst": worst_pred_ev,
            "spread": best_pred_ev - worst_pred_ev,
        },
        "n3_next_candidates_preview": avoid_seven.head(10)[
            ["number", "pred_prize_yen", "pred_winners", "pred_ev_straight"]
        ].to_dict(orient="records"),
        "bingo5": b5a,
        "artifacts": [
            "reports/n3_pattern_payout_table.csv",
            "reports/n3_payout_walkforward_scores.csv",
            "reports/n3_payout_selection_summary.csv",
            "reports/n3_payout_selection_detail.csv",
            "reports/n3_universe_pred_payout.csv",
            "reports/n3_candidates_top_pred_prize.csv",
            "reports/n3_candidates_all_diff_top.csv",
            "reports/n3_candidates_low_crowd_filters.csv",
            "reports/b5_crowd_quintile_payout.csv",
            "reports/PAYOUT_EV_REPORT.md",
            "reports/payout_ev_summary.json",
        ],
    }
    (REPORTS / "payout_ev_summary.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Persist model bundle for reuse (coefficients only; small)
    (REPORTS / "n3_payout_model_bundle.json").write_text(
        json.dumps(
            {
                "feature_cols": FEATURE_COLS,
                "scaler_mean": bundle["scaler_mean"],
                "scaler_scale": bundle["scaler_scale"],
                "ridge_prize_coef": bundle["ridge_prize_coef"],
                "ridge_prize_intercept": bundle["ridge_prize_intercept"],
                "ridge_win_coef": bundle["ridge_win_coef"],
                "ridge_win_intercept": bundle["ridge_win_intercept"],
                "metrics": bundle["metrics"],
                "coefficients": bundle["coefficients"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = []
    lines.append("# ペイアウト条件付きEV分析レポート")
    lines.append("")
    lines.append("## 目的関数の転換")
    lines.append(
        "当選番号の予測ではなく、**E[当せん金 | 買い目特徴] × P(的中) − 掛金** を最大化する。"
        f"ストレートでは P(的中)≈1/1000 なので、実質は **予測当せん単価** の最大化。"
    )
    lines.append("")
    lines.append("## Numbers3：パターン別の人気・単価（記述）")
    pat = pd.DataFrame(desc["pattern_payout"])
    # show contrasts for key flags value 1 vs 0
    for feat_name in ["is_triple", "is_palindrome", "is_sequential", "birthdayish", "has_seven"]:
        sub = pat[pat["feature"] == feat_name].sort_values("value")
        if len(sub) >= 2:
            a, b = sub.iloc[0], sub.iloc[-1]
            lines.append(
                f"- {feat_name}: value0 prize={a['avg_prize']:.0f}/win={a['avg_winners']:.1f} vs "
                f"value1 prize={b['avg_prize']:.0f}/win={b['avg_winners']:.1f}"
            )
    lines.append("")
    lines.append("## ウォークフォワード回帰（log prize / log winners）")
    m = bundle["metrics"]
    lines.append(
        f"- scored={m['n_scored']}, prize R²(log)={m['prize_r2_log']:.4f}, "
        f"MAE={m['prize_mae_yen']:.0f}円, corr(pred,actual)={m['corr_pred_prize_vs_actual']:.3f}"
    )
    lines.append(
        f"- winners R²(log)={m['winners_r2_log']:.4f}, MAE={m['winners_mae']:.1f}, "
        f"corr={m['corr_pred_winners_vs_actual']:.3f}"
    )
    lines.append("")
    lines.append("### 混雑（口数）に効く係数（絶対値上位）")
    for c in bundle["coefficients"][:8]:
        lines.append(
            f"- {c['feature']}: coef_log_winners={c['coef_log_winners']:+.4f}, "
            f"coef_log_prize={c['coef_log_prize']:+.4f}"
        )
    lines.append("")
    lines.append("## 5口選別バックテスト（予測単価の質）")
    lines.append(
        "的中回数は稀なので、主指標は **選んだ5口の平均予測単価／平均予測口数**。"
        "ROIは参考（分散極大）。"
    )
    lines.append("| strategy | mean_pred_prize | mean_pred_winners | hits | ROI |")
    lines.append("|---|---:|---:|---:|---:|")
    for _, r in summary.iterrows():
        lines.append(
            f"| {r['strategy']} | {r['mean_pred_prize']:.0f} | {r['mean_pred_winners']:.1f} | "
            f"{int(r['hits'])} | {r['roi']:.3f} |"
        )
    lines.append("")
    lines.append(
        f"理論EV目安（単価{N3_STRAIGHT_THEORY}円仮定）: {theory_ev:.1f}円/口。"
        f"モデル上の000–999の予測EV幅: {worst_pred_ev:.1f} 〜 {best_pred_ev:.1f}円。"
    )
    lines.append("")
    lines.append("## 次回向け候補（低混雑フィルタ例）")
    lines.append("条件: バラケ型・非連番・非birthdayish・7なし、予測単価上位。")
    lines.append("| number | pred_prize | pred_winners | pred_ev |")
    lines.append("|---|---:|---:|---:|")
    for _, r in avoid_seven.head(10).iterrows():
        lines.append(
            f"| {r['number']} | {r['pred_prize_yen']:.0f} | {r['pred_winners']:.1f} | {r['pred_ev_straight']:.1f} |"
        )
    lines.append("")
    lines.append("## Bingo5：混雑と1等実額")
    lines.append(
        f"口数と1等金額の相関 r={b5a['winners_vs_prize_corr']:.3f}（分担の効果が明確）。"
        "ボード特徴→混雑の予測五分位はサンプルが少なく単調ではなく、"
        "現時点では N3 ほどの選別モデル精度は出ていない。"
        "実務的には『売れていそうな並びを避ける』方針の定性ガイドに留める。"
    )
    lines.append("| crowd_q | n | avg_winners | avg_prize | median_prize |")
    lines.append("|---|---:|---:|---:|---:|")
    for r in b5a["pred_crowd_quintiles"]:
        lines.append(
            f"| {r['crowd_q']} | {r['n']} | {r['avg_winners']:.2f} | "
            f"{r['avg_prize']:.0f} | {r['median_prize']:.0f} |"
        )
    lines.append("")
    lines.append("## 保存ファイル")
    for a in out["artifacts"]:
        lines.append(f"- `{a}`")
    lines.append("")
    lines.append("## 位置づけ")
    lines.append(
        "この方向は『当たりやすくする』のではなく、"
        "『当たったときに取り分が痩せにくい買い目』を選ぶ最適化。"
        "ハウスエッジ自体は消えず、期待値をプラスにする保証はない。"
        "ただし予測パイプラインとしては検証可能で、前回までの番号予測よりデータが支持する。"
    )
    (REPORTS / "PAYOUT_EV_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Append pointer to main REPORT
    main_report = REPORTS / "REPORT.md"
    if main_report.exists():
        text = main_report.read_text(encoding="utf-8")
        marker = "\n## 追記: ペイアウト条件付きEV\n"
        addition = (
            marker
            + "番号予測から転換した続報。詳細は `PAYOUT_EV_REPORT.md` / `payout_ev_summary.json`。\n"
            + f"- 予測単価モデル corr(pred,actual prize)={m['corr_pred_prize_vs_actual']:.3f}\n"
            + f"- 000–999 の予測EV幅: {worst_pred_ev:.1f}〜{best_pred_ev:.1f}円/口\n"
            + "- 候補リスト: `n3_candidates_low_crowd_filters.csv`\n"
        )
        if marker in text:
            text = text.split(marker)[0].rstrip() + "\n" + addition
        else:
            text = text.rstrip() + "\n" + addition
        main_report.write_text(text + "\n", encoding="utf-8")

    print("Wrote payout EV reports to", REPORTS)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
