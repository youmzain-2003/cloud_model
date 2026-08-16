# ペイアウト条件付きEV分析レポート

## 目的関数の転換
当選番号の予測ではなく、**E[当せん金 | 買い目特徴] × P(的中) − 掛金** を最大化する。ストレートでは P(的中)≈1/1000 なので、実質は **予測当せん単価** の最大化。

## Numbers3：パターン別の人気・単価（記述）
- is_triple: value0 prize=93459/win=122.5 vs value1 prize=74254/win=573.5
- is_palindrome: value0 prize=92604/win=122.5 vs value1 prize=99992/win=158.0
- is_sequential: value0 prize=93455/win=125.7 vs value1 prize=87341/win=134.8
- birthdayish: value0 prize=94503/win=121.7 vs value1 prize=84424/win=157.2
- has_seven: value0 prize=92878/win=128.2 vs value1 prize=94482/win=119.7

## ウォークフォワード回帰（log prize / log winners）
- scored=3710, prize R²(log)=0.1997, MAE=14220円, corr(pred,actual)=0.479
- winners R²(log)=-0.1038, MAE=50.6, corr=0.366

### 混雑（口数）に効く係数（絶対値上位）
- is_triple: coef_log_winners=+0.1445, coef_log_prize=-0.0314
- has_zero: coef_log_winners=-0.1044, coef_log_prize=+0.1112
- d10: coef_log_winners=-0.0943, coef_log_prize=+0.0680
- sum_sq: coef_log_winners=-0.0602, coef_log_prize=-0.0004
- max_adj_diff: coef_log_winners=+0.0532, coef_log_prize=-0.0478
- d1: coef_log_winners=+0.0416, coef_log_prize=-0.0054
- birthdayish: coef_log_winners=+0.0336, coef_log_prize=-0.0183
- is_all_diff: coef_log_winners=-0.0254, coef_log_prize=-0.0082

## 5口選別バックテスト（予測単価の質）
的中回数は稀なので、主指標は **選んだ5口の平均予測単価／平均予測口数**。ROIは参考（分散極大）。
| strategy | mean_pred_prize | mean_pred_winners | hits | ROI |
|---|---:|---:|---:|---:|
| max_pred_prize_top5 | 127556 | 77.2 | 6 | -0.103 |
| avoid_crowd_top5 | 122338 | 70.9 | 6 | -0.013 |
| random_5 | 93508 | 114.0 | 2 | -0.691 |
| no_triple_random5 | 93315 | 109.4 | 6 | -0.053 |
| chase_crowd_top5 | 62040 | 673.4 | 3 | -0.665 |

理論EV目安（単価90000円仮定）: -110.0円/口。モデル上の000–999の予測EV幅: -146.1 〜 -72.5円。

## 次回向け候補（低混雑フィルタ例）
条件: バラケ型・非連番・非birthdayish・7なし、予測単価上位。
| number | pred_prize | pred_winners | pred_ev |
|---|---:|---:|---:|
| 690 | 116718 | 71.6 | -83.3 |
| 590 | 112486 | 74.6 | -87.5 |
| 490 | 112379 | 73.3 | -87.6 |
| 980 | 112167 | 74.9 | -87.8 |
| 560 | 112098 | 80.0 | -87.9 |
| 460 | 111991 | 78.6 | -88.0 |
| 096 | 111736 | 75.4 | -88.3 |
| 680 | 111190 | 75.1 | -88.8 |
| 960 | 110515 | 80.4 | -89.5 |
| 094 | 109158 | 75.8 | -90.8 |

## Bingo5：混雑五分位と1等実額
口数と1等金額の相関 r=-0.732。Bingo5 1st prize is shared; lower predicted crowd quintiles historically associate with higher average 1st-prize yen when that board appeared.
| crowd_q | n | avg_winners | avg_prize | median_prize |
|---|---:|---:|---:|---:|
| Q1_low | 46 | 4.02 | 8052313 | 6318100 |
| Q2 | 46 | 3.43 | 7615907 | 5980950 |
| Q3 | 46 | 4.28 | 7450596 | 6170950 |
| Q4 | 46 | 3.65 | 7823096 | 5839950 |
| Q5_high | 46 | 3.30 | 8953215 | 6441300 |

## 保存ファイル
- `reports/n3_pattern_payout_table.csv`
- `reports/n3_payout_walkforward_scores.csv`
- `reports/n3_payout_selection_summary.csv`
- `reports/n3_payout_selection_detail.csv`
- `reports/n3_universe_pred_payout.csv`
- `reports/n3_candidates_top_pred_prize.csv`
- `reports/n3_candidates_all_diff_top.csv`
- `reports/n3_candidates_low_crowd_filters.csv`
- `reports/b5_crowd_quintile_payout.csv`
- `reports/PAYOUT_EV_REPORT.md`
- `reports/payout_ev_summary.json`

## 位置づけ
この方向は『当たりやすくする』のではなく、『当たったときに取り分が痩せにくい買い目』を選ぶ最適化。ハウスエッジ自体は消えず、期待値をプラスにする保証はない。ただし予測パイプラインとしては検証可能で、前回までの番号予測よりデータが支持する。
