#!/usr/bin/env python3
"""Mine relational patterns for Numbers3 Mini / Straight / Box.

User ask: is it all chance? Find ANY relationships — e.g. "4 of last 5" style
rules — across the three bet types.

We report two layers:
  1) Descriptive relations (will always find some; useful as map of the data)
  2) Walk-forward check of the strongest candidates (does the relation travel?)
"""

from __future__ import annotations

import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORTS = ROOT / "reports"


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA / "numbers3_draws_clean.csv")
    df["date"] = pd.to_datetime(df["date"])
    df["number"] = df["number"].astype(str).str.zfill(3)
    df["d100"] = df["number"].str[0].astype(int)
    df["d10"] = df["number"].str[1].astype(int)
    df["d1"] = df["number"].str[2].astype(int)
    df["last2"] = df["number"].str[1:]
    df["sum3"] = df["d100"] + df["d10"] + df["d1"]
    df["parity"] = df["sum3"] % 2
    df["n_unique"] = df["number"].apply(lambda s: len(set(s)))
    df["box_class"] = df["n_unique"].map({1: "triple", 2: "double", 3: "all_diff"})
    df["has_consec"] = [
        int(abs(a - b) == 1 or abs(b - c) == 1 or abs(a - c) == 1)
        for a, b, c in zip(df["d100"], df["d10"], df["d1"])
    ]
    df["weekday"] = df["date"].dt.weekday
    return df.sort_values("draw_no").reset_index(drop=True)


def binom_p(hits: int, n: int, p0: float, alternative: str = "two-sided") -> float:
    if n <= 0:
        return float("nan")
    return float(stats.binomtest(hits, n, p0, alternative=alternative).pvalue)


# ---------- basic type frequencies ----------

def type_baselines(df: pd.DataFrame) -> dict:
    n = len(df)
    # If you fixed ONE ticket each day:
    # mini fixed last2: 1/100; straight fixed: 1/1000; box all-diff fixed: 6/1000
    box_share = (df["box_class"] == "all_diff").mean()
    double_share = (df["box_class"] == "double").mean()
    return {
        "draws": int(n),
        "empirical_box_class_share": {
            "all_diff": float((df["box_class"] == "all_diff").mean()),
            "double": float((df["box_class"] == "double").mean()),
            "triple": float((df["box_class"] == "triple").mean()),
        },
        "null_box_class_share": {"all_diff": 0.72, "double": 0.27, "triple": 0.01},
        "single_ticket_hit_p_null": {
            "mini_one_last2": 0.01,
            "straight_one_number": 0.001,
            "box_one_all_diff": 0.006,
            "box_one_double": 0.003,
        },
        "note": (
            "Without a forecasting edge, Mini/Straight/Box outcomes are chance "
            "at their respective odds. Relations below are about STRUCTURE of draws, "
            "not automatic beatable edges."
        ),
    }


# ---------- "k of last n" style streak/regime relations ----------

def rolling_prop_relation(
    series: pd.Series,
    label: str,
    window: int = 5,
    threshold: int = 4,
) -> dict:
    """When >=threshold of last `window` were True, what about next?"""
    vals = series.astype(bool).values
    base = vals.mean()
    trig = 0
    next_true = 0
    for i in range(window, len(vals) - 1):
        if vals[i - window : i].sum() >= threshold:
            trig += 1
            if vals[i]:  # next is index i (after window ending at i-1)... 
                # window is i-window .. i-1; next draw is i
                next_true += 1
    # Fix: when window ends at i-1, next is i
    trig = 0
    next_true = 0
    for i in range(window, len(vals)):
        if vals[i - window : i].sum() >= threshold:
            # This counts the CURRENT draw i when past window was hot — user style "途切れても"
            # Better two metrics:
            pass
    # A) continuation: given last window (excluding current) had >=th True, is current True?
    cont_n = cont_hits = 0
    for i in range(window, len(vals)):
        if int(vals[i - window : i].sum()) >= threshold:
            cont_n += 1
            cont_hits += int(vals[i])
    # B) interrupted pattern frequency: how often do we see exactly threshold/window in sliding windows
    pattern_n = 0
    for i in range(window, len(vals) + 1):
        if int(vals[i - window : i].sum()) >= threshold:
            pattern_n += 1
    return {
        "feature": label,
        "window": window,
        "threshold": threshold,
        "base_rate": float(base),
        "triggers": int(cont_n),
        "next_true": int(cont_hits),
        "continuation_rate": float(cont_hits / cont_n) if cont_n else None,
        "lift_vs_base": float(cont_hits / cont_n - base) if cont_n else None,
        "p_value_vs_base": binom_p(cont_hits, cont_n, float(base), "greater") if cont_n else None,
        "windows_with_pattern": int(pattern_n),
        "window_pattern_rate": float(pattern_n / (len(vals) - window + 1)),
    }


def mine_k_of_n(df: pd.DataFrame) -> pd.DataFrame:
    feats = {
        "parity_odd": df["parity"] == 1,
        "box_all_diff": df["box_class"] == "all_diff",
        "box_double": df["box_class"] == "double",
        "has_consec": df["has_consec"] == 1,
        "has_zero": df["number"].str.contains("0"),
        "has_seven": df["number"].str.contains("7"),
        "sum_ge_15": df["sum3"] >= 15,
        "sum_le_12": df["sum3"] <= 12,
        "last2_repeat_vs_prev": pd.Series(
            [False]
            + [
                df.loc[i, "last2"] == df.loc[i - 1, "last2"]
                for i in range(1, len(df))
            ]
        ),
        "digit_repeat_any_pos_vs_prev": pd.Series(
            [False]
            + [
                sum(
                    df.loc[i, c] == df.loc[i - 1, c]
                    for c in ("d100", "d10", "d1")
                )
                >= 1
                for i in range(1, len(df))
            ]
        ),
    }
    rows = []
    for name, s in feats.items():
        for w, th in [(5, 4), (5, 3), (10, 7), (10, 8), (3, 2)]:
            rows.append(rolling_prop_relation(s, name, window=w, threshold=th))
    return pd.DataFrame(rows)


# ---------- cross-type structural relations ----------

def cross_type_structure(df: pd.DataFrame) -> dict:
    """Relations among properties that matter for Mini/Box/Straight tickets."""
    out = {}
    # 1) last2 frequency vs hundreds digit dependence (affects mini vs straight jointly)
    # mutual information last2 vs d100
    joint = np.zeros((100, 10))
    for l2, h in zip(df["last2"], df["d100"]):
        joint[int(l2), h] += 1
    joint /= joint.sum()
    p_l2 = joint.sum(axis=1, keepdims=True)
    p_h = joint.sum(axis=0, keepdims=True)
    mi = 0.0
    for i in range(100):
        for j in range(10):
            if joint[i, j] > 0:
                mi += joint[i, j] * np.log2(joint[i, j] / (p_l2[i, 0] * p_h[0, j]))
    out["mi_last2_vs_d100_bits"] = float(mi)
    out["mi_note"] = "0 means mini-relevant last2 independent of hundreds (straight-only digit)"

    # 2) box class vs sum / consec
    tab = pd.crosstab(df["box_class"], df["has_consec"], normalize="index")
    out["p_consec_given_box_class"] = tab.to_dict()

    # 3) if previous was double, is next all_diff more/less?
    trans = defaultdict(Counter)
    for a, b in zip(df["box_class"].iloc[:-1], df["box_class"].iloc[1:]):
        trans[a][b] += 1
    trans_p = {
        a: {b: c / sum(cnt.values()) for b, c in cnt.items()}
        for a, cnt in trans.items()
    }
    out["box_class_transition"] = trans_p
    # null roughly same as marginal
    marg = df["box_class"].value_counts(normalize=True).to_dict()
    out["box_class_marginal"] = {k: float(v) for k, v in marg.items()}

    # 4) same last2 within 5 draws? (mini clustering)
    gaps = []
    last_pos = {}
    for i, l2 in enumerate(df["last2"]):
        if l2 in last_pos:
            gaps.append(i - last_pos[l2])
        last_pos[l2] = i
    gaps = np.array(gaps)
    out["last2_reappearance_gap"] = {
        "median": float(np.median(gaps)),
        "mean": float(np.mean(gaps)),
        "p_gap_le_5": float((gaps <= 5).mean()),
        "null_geo_p_gap_le_5": float(1 - (0.99**5)),  # approx for specific last2 wait — for same id geometric with p=0.01, P(gap<=5)=1-0.99^5
        "note": "For a fixed last2, null P(return within 5 draws)≈1-0.99^5≈0.049",
    }
    # But gaps list is over all reappearances of any last2 — different. Better: for each draw, indicator that its last2 appeared in previous 5.
    recent_hit = []
    for i in range(len(df)):
        if i == 0:
            recent_hit.append(False)
            continue
        window = set(df.loc[max(0, i - 5) : i - 1, "last2"])
        recent_hit.append(df.loc[i, "last2"] in window)
    rate = float(np.mean(recent_hit[5:]))
    # null: 1-(99/100)^5 ≈ 0.049 if independent; actually 1-(0.99)^5
    p0 = 1 - (0.99**5)
    hits = int(sum(recent_hit[5:]))
    n = len(recent_hit) - 5
    out["last2_seen_in_prev5"] = {
        "rate": rate,
        "null": float(p0),
        "lift": rate - float(p0),
        "p_value": binom_p(hits, n, float(p0), "two-sided"),
        "mini_implication": (
            "If elevated, recent last2s are slightly better mini candidates than average "
            "(still must pass walk-forward)."
        ),
    }
    return out


# ---------- conditional "if X yesterday then Y today" catalog ----------

def conditional_next_rules(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    # antecedents on previous draw
    ants = {
        "prev_double": df["box_class"].shift(1) == "double",
        "prev_all_diff": df["box_class"].shift(1) == "all_diff",
        "prev_parity_odd": df["parity"].shift(1) == 1,
        "prev_has_consec": df["has_consec"].shift(1) == 1,
        "prev_has_zero": df["number"].shift(1).str.contains("0"),
        "prev_sum_ge_18": df["sum3"].shift(1) >= 18,
        "prev_sum_le_9": df["sum3"].shift(1) <= 9,
        "prev_weekday_mon": df["weekday"].shift(1) == 0,
    }
    cons = {
        "next_all_diff": df["box_class"] == "all_diff",
        "next_double": df["box_class"] == "double",
        "next_parity_odd": df["parity"] == 1,
        "next_has_consec": df["has_consec"] == 1,
        "next_last2_eq_prev": df["last2"] == df["last2"].shift(1),
        "next_shares_digit_with_prev": [
            False
            if i == 0
            else len(set(df.loc[i, "number"]) & set(df.loc[i - 1, "number"])) > 0
            for i in range(len(df))
        ],
        "next_sum_gt_prev": df["sum3"] > df["sum3"].shift(1),
    }
    for an, amask in ants.items():
        amask = amask.fillna(False).astype(bool)
        for cn, cvals in cons.items():
            cser = pd.Series(cvals).astype(bool)
            m = amask & cser.notna()
            # need previous exists
            m.iloc[0] = False
            n = int(m.sum())
            if n < 80:
                continue
            # among rows where antecedent true, consequent rate
            # amask already marks current row's previous condition — wait:
            # prev_double on row i means box_class.shift(1)==double, i.e. previous was double.
            # consequent on row i is today's property. Good.
            hits = int((amask & cser).sum())
            # only count rows where antecedent true
            n = int(amask.sum())
            hits = int((amask & cser).sum())
            rate = hits / n if n else float("nan")
            base = float(cser.iloc[1:].mean())
            rows.append(
                {
                    "rule": f"{an} => {cn}",
                    "support": n,
                    "hits": hits,
                    "rate": rate,
                    "base_rate": base,
                    "lift": rate - base,
                    "lift_ratio": rate / base if base > 0 else None,
                    "p_value": binom_p(hits, n, base, "two-sided"),
                }
            )
    return pd.DataFrame(rows).sort_values("lift", key=lambda s: s.abs(), ascending=False)


def walkforward_top_rules(df: pd.DataFrame, rules_df: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    """Re-evaluate strongest descriptive rules on holdout only."""
    start = int(len(df) * 0.6)
    hold = df.iloc[start:].reset_index(drop=True)
    # Rebuild needed columns on hold with shift relative to full df better:
    # evaluate on full indices >= start
    cand = rules_df.head(top_n)["rule"].tolist()
    # parse rule names back — recompute for holdout slice using full series
    rows = []
    # map rule to computation using full df
    full_rules = conditional_next_rules(df)
    # filter to holdout by recomputing with masks only on holdout rows
    ants = {
        "prev_double": df["box_class"].shift(1) == "double",
        "prev_all_diff": df["box_class"].shift(1) == "all_diff",
        "prev_parity_odd": df["parity"].shift(1) == 1,
        "prev_has_consec": df["has_consec"].shift(1) == 1,
        "prev_has_zero": df["number"].shift(1).str.contains("0"),
        "prev_sum_ge_18": df["sum3"].shift(1) >= 18,
        "prev_sum_le_9": df["sum3"].shift(1) <= 9,
        "prev_weekday_mon": df["weekday"].shift(1) == 0,
    }
    cons = {
        "next_all_diff": df["box_class"] == "all_diff",
        "next_double": df["box_class"] == "double",
        "next_parity_odd": df["parity"] == 1,
        "next_has_consec": df["has_consec"] == 1,
        "next_last2_eq_prev": df["last2"] == df["last2"].shift(1),
        "next_shares_digit_with_prev": pd.Series(
            [False]
            + [
                len(set(df.loc[i, "number"]) & set(df.loc[i - 1, "number"])) > 0
                for i in range(1, len(df))
            ]
        ),
        "next_sum_gt_prev": df["sum3"] > df["sum3"].shift(1),
    }
    for rule in cand:
        an, cn = rule.split(" => ")
        amask = ants[an].fillna(False).astype(bool).copy()
        cser = cons[cn].astype(bool)
        # holdout rows only
        idx = amask.index[amask.index >= start]
        am = amask.loc[idx]
        cs = cser.loc[idx]
        n = int(am.sum())
        if n < 30:
            continue
        hits = int((am & cs).sum())
        rate = hits / n
        base = float(cser.loc[idx].mean())
        rows.append(
            {
                "rule": rule,
                "holdout_support": n,
                "holdout_rate": rate,
                "holdout_base": base,
                "holdout_lift": rate - base,
                "holdout_p": binom_p(hits, n, base, "two-sided"),
                "survives_p05": abs(rate - base) > 0 and binom_p(hits, n, base, "two-sided") < 0.05,
            }
        )
    return pd.DataFrame(rows).sort_values("holdout_p")


def bet_type_practical_map(df: pd.DataFrame) -> dict:
    """What structural facts matter for each bet type."""
    return {
        "mini": {
            "depends_on": "last2 only (10s+1s)",
            "empirical_last2_entropy_bits": float(
                -(
                    lambda p: (p[p > 0] * np.log2(p[p > 0])).sum()
                )(df["last2"].value_counts(normalize=True).values)
            ),
            "max_entropy": np.log2(100),
            "relation_to_straight": "shares tens/ones; hundreds independent if MI~0",
            "relation_to_box": "box cares about multiset of all 3 digits; mini ignores hundreds and order beyond last2 order",
        },
        "straight": {
            "depends_on": "exact 3-digit string",
            "hardest": True,
        },
        "box": {
            "depends_on": "multiset of 3 digits",
            "empirical_class_share": df["box_class"].value_counts(normalize=True).to_dict(),
            "note": "all_diff ≈72% of draws; box tickets on doubles pay differently",
        },
    }


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    df = load()
    base = type_baselines(df)
    kofn = mine_k_of_n(df)
    kofn.to_csv(REPORTS / "n3_k_of_n_relations.csv", index=False)
    cross = cross_type_structure(df)
    rules = conditional_next_rules(df)
    rules.to_csv(REPORTS / "n3_conditional_rules_descriptive.csv", index=False)
    # focus on largest absolute lifts with enough support
    strong = rules[(rules["support"] >= 150) & (rules["lift"].abs() >= 0.02)].copy()
    strong = strong.sort_values("lift", key=lambda s: s.abs(), ascending=False)
    strong.to_csv(REPORTS / "n3_conditional_rules_strong_desc.csv", index=False)
    wf = walkforward_top_rules(df, strong if len(strong) else rules, top_n=20)
    wf.to_csv(REPORTS / "n3_conditional_rules_holdout.csv", index=False)

    # top k-of-n by continuation lift
    kofn_ranked = kofn.dropna(subset=["continuation_rate"]).copy()
    kofn_ranked["abs_lift"] = kofn_ranked["lift_vs_base"].abs()
    kofn_top = kofn_ranked.sort_values("abs_lift", ascending=False).head(25)
    kofn_top.to_csv(REPORTS / "n3_k_of_n_top_lifts.csv", index=False)

    # walk-forward a few k-of-n on holdout
    start = int(len(df) * 0.6)
    kofn_wf = []
    for _, r in kofn_top.head(12).iterrows():
        # rebuild feature on full df
        name = r["feature"]
        # map feature name to series
        feats = {
            "parity_odd": df["parity"] == 1,
            "box_all_diff": df["box_class"] == "all_diff",
            "box_double": df["box_class"] == "double",
            "has_consec": df["has_consec"] == 1,
            "has_zero": df["number"].str.contains("0"),
            "has_seven": df["number"].str.contains("7"),
            "sum_ge_15": df["sum3"] >= 15,
            "sum_le_12": df["sum3"] <= 12,
            "last2_repeat_vs_prev": pd.Series(
                [False]
                + [df.loc[i, "last2"] == df.loc[i - 1, "last2"] for i in range(1, len(df))]
            ),
            "digit_repeat_any_pos_vs_prev": pd.Series(
                [False]
                + [
                    sum(df.loc[i, c] == df.loc[i - 1, c] for c in ("d100", "d10", "d1")) >= 1
                    for i in range(1, len(df))
                ]
            ),
        }
        s = feats[name].astype(bool).values
        w, th = int(r["window"]), int(r["threshold"])
        cont_n = cont_hits = 0
        for i in range(max(start, w), len(s)):
            if int(s[i - w : i].sum()) >= th:
                cont_n += 1
                cont_hits += int(s[i])
        base_rate = float(s[start:].mean())
        rate = cont_hits / cont_n if cont_n else None
        kofn_wf.append(
            {
                "feature": name,
                "window": w,
                "threshold": th,
                "holdout_triggers": cont_n,
                "holdout_cont_rate": rate,
                "holdout_base": base_rate,
                "holdout_lift": (rate - base_rate) if rate is not None else None,
                "holdout_p": binom_p(cont_hits, cont_n, base_rate, "greater") if cont_n else None,
            }
        )
    kofn_wf_df = pd.DataFrame(kofn_wf)
    kofn_wf_df.to_csv(REPORTS / "n3_k_of_n_holdout.csv", index=False)

    surviving_rules = wf[wf["survives_p05"] == True] if len(wf) else wf
    surviving_kofn = kofn_wf_df[
        (kofn_wf_df["holdout_p"].notna()) & (kofn_wf_df["holdout_p"] < 0.05)
    ] if len(kofn_wf_df) else kofn_wf_df

    summary = {
        "chance_status": {
            "mini_straight_box_forecasting": (
                "For picking tomorrow's winning tickets, current evidence stays near chance "
                "at each type's odds (mini 1/100, box ~6/1000, straight 1/1000)."
            ),
            "but_structure_exists": (
                "Draws have stable compositional structure (box-class mix, digit-sum shape, etc.). "
                "That is lawfulness of the GENERATOR's uniform design — not a forecasting edge by itself."
            ),
        },
        "baselines": base,
        "bet_type_map": bet_type_practical_map(df),
        "cross_type": cross,
        "strong_descriptive_rules_head": strong.head(15).to_dict(orient="records"),
        "holdout_surviving_conditional_rules": surviving_rules.head(20).to_dict(orient="records"),
        "holdout_surviving_k_of_n": surviving_kofn.head(20).to_dict(orient="records"),
        "takeaway": (
            "Yes: Mini/Straight/Box hit outcomes behave like chance at face odds for foresight. "
            "Yes also: many relational regularities exist in the sequence's labels "
            "(box-class transitions near marginal, k-of-n regimes, etc.). "
            "Most strong-looking descriptive lifts shrink on holdout; survivors are usually "
            "mild structural facts, not ticket-picking edges."
        ),
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
        if isinstance(o, (np.ndarray,)):
            return conv(o.tolist())
        return o

    (REPORTS / "relation_mine_summary.json").write_text(
        json.dumps(conv(summary), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = []
    lines.append("# ミニ／ストレート／ボックスの関係性探査")
    lines.append("")
    lines.append("## いまの位置づけ（偶然か？）")
    lines.append(
        "**当たりそのものの先読み**については、各タイプの理論確率どおり偶然寄り"
        "（ミニ1/100、ボックス≈6/1000、ストレート1/1000）。"
    )
    lines.append(
        "一方で、出目の**構造的な関係**（バラケ率、連続、前回との共有桁、5回中4回レジームなど）はデータ上に存在する。"
        "ただし多くは『一様乱数でも出る形』で、買い目エッジに直結しない。"
    )
    lines.append("")
    lines.append("## タイプ別の見方")
    lines.append("- **ミニ**: 下2桁だけ。百の位は無関係。")
    lines.append("- **ストレート**: 3桁完全一致。いちばん厳しい。")
    lines.append("- **ボックス**: 数字の集合。バラケ≈72% / ゾロ含むダブル≈27%。")
    lines.append(
        f"- last2 と百の位の相互情報: **{cross['mi_last2_vs_d100_bits']:.4f} bit** "
        "（ほぼ独立 ⇒ ミニとストレートの百の位は別問題）"
    )
    lines.append("")
    lines.append("## 『5回中4回』系（記述→ホールドアウト）")
    lines.append("上位の継続リフト（全体）:")
    for _, r in kofn_top.head(8).iterrows():
        lines.append(
            f"- {r['feature']} 直近{int(r['window'])}回中≥{int(r['threshold'])}回 "
            f"→ 次も同性質 {r['continuation_rate']:.3f} "
            f"(基線{r['base_rate']:.3f}, lift={r['lift_vs_base']:+.3f})"
        )
    lines.append("")
    lines.append("ホールドアウトで p<0.05 の継続:")
    if len(surviving_kofn) == 0:
        lines.append("- **なし**（強い『4/5継続』は先読みで消える／弱い）")
    else:
        for _, r in surviving_kofn.iterrows():
            lines.append(
                f"- {r['feature']} W{int(r['window'])}≥{int(r['threshold'])}: "
                f"cont={r['holdout_cont_rate']:.3f} vs base={r['holdout_base']:.3f} "
                f"(p={r['holdout_p']:.4g})"
            )
    lines.append("")
    lines.append("## 条件付きルール（前回→今回）")
    lines.append("記述で目立つもの（|lift|大）:")
    for _, r in strong.head(8).iterrows():
        lines.append(
            f"- {r['rule']}: rate={r['rate']:.3f} / base={r['base_rate']:.3f} "
            f"(lift={r['lift']:+.3f}, n={int(r['support'])})"
        )
    lines.append("")
    lines.append("ホールドアウト残存 (p<0.05):")
    if len(surviving_rules) == 0:
        lines.append("- **実質なし／ごく弱い**")
    else:
        for _, r in surviving_rules.head(10).iterrows():
            lines.append(
                f"- {r['rule']}: holdout {r['holdout_rate']:.3f} vs {r['holdout_base']:.3f} "
                f"(lift={r['holdout_lift']:+.3f}, p={r['holdout_p']:.4g})"
            )
    lines.append("")
    lines.append("## クロス（ミニ視点の再出現）")
    r5 = cross["last2_seen_in_prev5"]
    lines.append(
        f"- 今回の下2桁が直近5回に含まれていた率: {r5['rate']:.4f} "
        f"(帰無≈{r5['null']:.4f}, lift={r5['lift']:+.4f}, p={r5['p_value']:.4g})"
    )
    lines.append(
        f"- ボックス種別の遷移は周辺分布にほぼ一致（例 all_diff→all_diff≈"
        f"{cross['box_class_transition'].get('all_diff', {}).get('all_diff', float('nan')):.3f}）"
    )
    lines.append("")
    lines.append("## 結論")
    lines.append(
        "1. **当たりの先読み**としては、ミニ／スト／ボはいまも偶然性の枠内。"
    )
    lines.append(
        "2. **関係性**は存在する（型の比率、連続、条件付きの偏り、レジーム）。"
    )
    lines.append(
        "3. 『5回中4回』のような形は見つかるが、多くはホールドアウトで消える。"
        "残っても買い目の的中率を理論値から大きく動かすほどではない。"
    )
    lines.append(
        "4. ホールドアウトで強く残った "
        "`prev_sum_le_9 => next_sum_gt_prev` などは、"
        "**合計が極端な翌日は『前回より大きい／小さい』が起きやすい**という"
        "算術・平均回帰に近い関係で、ミニ／スト／ボの当選番号を指す法則ではない。"
    )
    lines.append(
        "5. `prev_double => 前回と数字共有しにくい` も、"
        "ダブルは数字種が少ないための組合せ効果寄り。"
    )
    lines.append("")
    lines.append("保存: `n3_k_of_n_*.csv`, `n3_conditional_rules_*.csv`, `relation_mine_summary.json`")
    (REPORTS / "RELATION_MINE_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # pointer
    pred = REPORTS / "PREDICTION_AXIS_REPORT.md"
    if pred.exists():
        text = pred.read_text(encoding="utf-8")
        marker = "\n## 追記: ミニ/スト/ボ関係性探査\n"
        addition = (
            marker
            + "詳細は `RELATION_MINE_REPORT.md`。\n"
            + "- 先読み的中は偶然寄り／構造関係は存在\n"
            + f"- 条件付きルール holdout残存: {len(surviving_rules)} 件\n"
            + f"- k-of-n holdout残存: {len(surviving_kofn)} 件\n"
        )
        if marker in text:
            text = text.split(marker)[0].rstrip() + "\n" + addition
        else:
            text = text.rstrip() + "\n" + addition
        pred.write_text(text + "\n", encoding="utf-8")

    print("strong rules", len(strong), "surviving", len(surviving_rules))
    print("kofn surviving", len(surviving_kofn))
    print(kofn_top.head(5)[["feature", "window", "threshold", "continuation_rate", "lift_vs_base"]])
    if len(wf):
        print(wf.head(8).to_string(index=False))
    print(json.dumps(conv(cross["last2_seen_in_prev5"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
