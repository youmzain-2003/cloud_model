# ナンバーズ3／ビンゴ5 予測分析レポート

## 目的
運の言い換えではなく、**予測問題**として定式化する。各指標は帰無仮説「IID一様乱数」に対する検定・時系列ウォークフォワード評価・金額ROIで検証する。

## データ
- Numbers3 raw: 7049回 / clean: 7006回 (1994-10-07〜2026-08-14)
- Bingo5: 483回 (2017-04-05〜2026-08-12)
- みずほ公式は当環境から取得不可。RENBANミラーを使用し、同一数字の連続3回以上ストリーク、および同一数字かつ同一口数・当せん金の隣接行を汚染として除去。
- 長ストリーク例: 361x3(2019-10-07〜2019-10-09), 808x4(2019-10-16〜2019-10-21), 178x3(2020-05-22〜2020-05-26), 458x10(2020-10-19〜2020-10-30)

## ナンバーズ3：乱数性・関連性（clean）
- **N3 chi2 uniform hundreds**: chi2=12.44, p=0.1897 — Reject H0 if p<<0.05 (digit not uniform).
- **N3 chi2 uniform tens**: chi2=7.16, p=0.6204 — Reject H0 if p<<0.05 (digit not uniform).
- **N3 chi2 uniform ones**: chi2=6.86, p=0.6517 — Reject H0 if p<<0.05 (digit not uniform).
- **N3 runs-test sum parity**: z=-0.1661, p=0.8681 — Serial dependence in odd/even of digit-sum.
- **N3 empirical number entropy (bits)**: entropy=9.858 — Max entropy for observed support size 999 ≈ 9.964; full 1000-space max=9.966.

### 前回との関係（clean vs raw）
- exact_repeat: clean=0.0013 (null=0.0010, lift=+0.0003) / raw=0.0047 (lift=+0.0037)
- same_digit_same_pos_avg: clean=0.1010 (null=0.1000, lift=+0.0010) / raw=0.1043 (lift=+0.0043)
- any_shared_digit_multiset: clean=0.6107 (null=0.6100, lift=+0.0007) / raw=0.6127 (lift=+0.0027)
- any_pos_slide_pm1: clean=0.4507 (null=0.4476, lift=+0.0030) / raw=0.4493 (lift=+0.0017)

### マルコフ性（桁の相互情報・次桁予測）
- d100: MI=0.0085 bit, WF acc=0.0984 (baseline 0.10, lift=-0.0016)
- d10: MI=0.0090 bit, WF acc=0.0995 (baseline 0.10, lift=-0.0005)
- d1: MI=0.0078 bit, WF acc=0.1016 (baseline 0.10, lift=+0.0016)

### MLウォークフォワード（次の百の位）
- logreg: acc=0.0937±0.0039, logloss=2.3615 (uniform acc=0.10, logloss=2.3026)
- rf: acc=0.1003±0.0066, logloss=2.3104 (uniform acc=0.10, logloss=2.3026)

### ストレート1口戦略 ROI（clean）
| strategy | hits | hit_rate | ROI |
|---|---:|---:|---:|
| repeat_prev | 5 | 0.00178 | -0.143 |
| random | 5 | 0.00178 | -0.235 |
| hot_digits_W50 | 5 | 0.00178 | -0.303 |
| cold_digits_W50 | 4 | 0.00143 | -0.311 |
| slide_plus1 | 3 | 0.00107 | -0.592 |
| unseen_in_last500 | 2 | 0.00071 | -0.687 |

参考: rawデータでは `repeat_prev` が偽の高ROIになる。これは汚染ストリークの産物で、予測エッジではない。
- raw repeat_prev: hits=29, hit_rate=0.01028, ROI=3.611

### 金額・ボックス型・人気偏重
- all_diff: share=0.718, avg_straight_prize=91255, avg_winners=121.8
- double: share=0.274, avg_straight_prize=101269, avg_winners=124.5
- triple: share=0.008, avg_straight_prize=73487, avg_winners=573.5
- 理論ストレート期待還元の目安: 0.450 （= 90000/1000 / 200）
- 口数と当せん金の相関（clean）: r=-0.542 （口数多いほど単価下がる＝金額最適化の余地はここ）

## ビンゴ5（帯構造を明示）
- 構造: one number from each of 8 bands of 5 (bingo card columns/rows)
- band 1-5: chi2=3.573, p=0.4668
- band 6-10: chi2=3.222, p=0.5215
- band 11-15: chi2=2.207, p=0.6977
- band 16-20: chi2=2.124, p=0.7129
- band 21-25: chi2=3.656, p=0.4545
- band 26-30: chi2=2.663, p=0.6158
- band 31-35: chi2=11.793, p=0.01896
- band 36-40: chi2=7.093, p=0.131
- 前回重複 mean=1.705 (band-null=1.604)
- 連番ペア mean=0.306 (band-null=0.281)
- hot30重複=1.596 / random=1.631
- 1等実額: mean=7914112, median=6252400, min=0, max=26436700
- 注記: Bingo5 1st prize is pari-mutuel: more winners => lower yen. Avoiding popular cards can raise conditional payout, not hit probability.

## クロス（同日 N3×Bingo5）
{
  "paired_same_date_rows": 473,
  "pearson_sum_r": -0.001461437562185277,
  "pearson_sum_p": 0.9747112266835897,
  "n3_ones_in_bingo_mod10_rate": 0.5750528541226215,
  "null_rate_sim": 0.5692
}

## 予測としての結論
クリーン後のデータでは、**当選番号そのものを当てる予測エッジは見つからない**。見える法則の大半は帰無水準か、ミラー汚染のアーティファクト。一方で金額面では、口数増加に応じた単価低下が明確で、『的中確率』ではなく『的中時の取り分』を目的関数にする設計が妥当。

予測パイプラインの次の打ち手:
1. 新規指標は clean データ＋ウォークフォワードROI/loglossで棄却判定
2. 人気数字回避など **ペイアウト条件付きEV** を別モデル化
3. Numbers3を日次ラベル、Bingo5を週次の分散検証に使う
4. 公式データが取れる環境ではミラー異常区間を再照合

詳細JSON: `reports/analysis_summary.json`

## 追記: ペイアウト条件付きEV
番号予測から転換した続報。詳細は `PAYOUT_EV_REPORT.md` / `payout_ev_summary.json`。
- 予測単価モデル corr(pred,actual prize)=0.479
- 000–999 の予測EV幅: -146.1〜-72.5円/口
- 候補リスト: `n3_candidates_low_crowd_filters.csv`

## 追記: 予想仮説と¥1000運用
的中追及に戻した続報。詳細は `PREDICTION_AXIS_REPORT.md`。
- 昇格軸数: 0
- ¥1000の帰無上限: 約5%/回（5ミニ）→ 2–3回に1回は予算不足
- ポートフォリオ要約: `n3_budget1000_portfolio_summary.csv`

