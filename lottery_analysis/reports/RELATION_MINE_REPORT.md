# ミニ／ストレート／ボックスの関係性探査

## いまの位置づけ（偶然か？）
**当たりそのものの先読み**については、各タイプの理論確率どおり偶然寄り（ミニ1/100、ボックス≈6/1000、ストレート1/1000）。
一方で、出目の**構造的な関係**（バラケ率、連続、前回との共有桁、5回中4回レジームなど）はデータ上に存在する。ただし多くは『一様乱数でも出る形』で、買い目エッジに直結しない。

## タイプ別の見方
- **ミニ**: 下2桁だけ。百の位は無関係。
- **ストレート**: 3桁完全一致。いちばん厳しい。
- **ボックス**: 数字の集合。バラケ≈72% / ゾロ含むダブル≈27%。
- last2 と百の位の相互情報: **0.0989 bit** （ほぼ独立 ⇒ ミニとストレートの百の位は別問題）

## 『5回中4回』系（記述→ホールドアウト）
上位の継続リフト（全体）:
- digit_repeat_any_pos_vs_prev 直近10回中≥8回 → 次も同性質 0.000 (基線0.276, lift=-0.276)
- box_double 直近10回中≥8回 → 次も同性質 0.500 (基線0.274, lift=+0.226)
- digit_repeat_any_pos_vs_prev 直近10回中≥7回 → 次も同性質 0.113 (基線0.276, lift=-0.163)
- box_double 直近10回中≥7回 → 次も同性質 0.383 (基線0.274, lift=+0.109)
- has_seven 直近5回中≥4回 → 次も同性質 0.183 (基線0.271, lift=-0.089)
- sum_le_12 直近10回中≥8回 → 次も同性質 0.496 (基線0.421, lift=+0.076)
- has_zero 直近10回中≥7回 → 次も同性質 0.326 (基線0.272, lift=+0.053)
- has_zero 直近10回中≥8回 → 次も同性質 0.222 (基線0.272, lift=-0.050)

ホールドアウトで p<0.05 の継続:
- sum_le_12 W10≥8: cont=0.552 vs base=0.427 (p=0.03812)

## 条件付きルール（前回→今回）
記述で目立つもの（|lift|大）:
- prev_sum_le_9 => next_sum_gt_prev: rate=0.865 / base=0.472 (lift=+0.393, n=1519)
- prev_sum_ge_18 => next_sum_gt_prev: rate=0.089 / base=0.472 (lift=-0.382, n=1532)
- prev_has_zero => next_sum_gt_prev: rate=0.706 / base=0.472 (lift=+0.234, n=1909)
- prev_double => next_shares_digit_with_prev: rate=0.486 / base=0.611 (lift=-0.125, n=1923)
- prev_all_diff => next_shares_digit_with_prev: rate=0.662 / base=0.611 (lift=+0.051, n=5027)
- prev_sum_le_9 => next_shares_digit_with_prev: rate=0.584 / base=0.611 (lift=-0.027, n=1519)
- prev_double => next_sum_gt_prev: rate=0.495 / base=0.472 (lift=+0.023, n=1923)
- prev_has_consec => next_shares_digit_with_prev: rate=0.633 / base=0.611 (lift=+0.022, n=3015)

ホールドアウト残存 (p<0.05):
- prev_sum_le_9 => next_sum_gt_prev: holdout 0.876 vs 0.474 (lift=+0.402, p=2.214e-99)
- prev_sum_ge_18 => next_sum_gt_prev: holdout 0.091 vs 0.474 (lift=-0.383, p=2.775e-89)
- prev_has_zero => next_sum_gt_prev: holdout 0.681 vs 0.474 (lift=+0.206, p=1.1e-31)
- prev_double => next_shares_digit_with_prev: holdout 0.501 vs 0.612 (lift=-0.111, p=6.18e-10)
- prev_all_diff => next_shares_digit_with_prev: holdout 0.657 vs 0.612 (lift=+0.045, p=2.654e-05)

## クロス（ミニ視点の再出現）
- 今回の下2桁が直近5回に含まれていた率: 0.0459 (帰無≈0.0490, lift=-0.0032, p=0.2338)
- ボックス種別の遷移は周辺分布にほぼ一致（例 all_diff→all_diff≈0.721）

## 結論
1. **当たりの先読み**としては、ミニ／スト／ボはいまも偶然性の枠内。
2. **関係性**は存在する（型の比率、連続、条件付きの偏り、レジーム）。
3. 『5回中4回』のような形は見つかるが、多くはホールドアウトで消える。残っても買い目の的中率を理論値から大きく動かすほどではない。
4. ホールドアウトで強く残った `prev_sum_le_9 => next_sum_gt_prev` などは、**合計が極端な翌日は『前回より大きい／小さい』が起きやすい**という算術・平均回帰に近い関係で、ミニ／スト／ボの当選番号を指す法則ではない。
5. `prev_double => 前回と数字共有しにくい` も、ダブルは数字種が少ないための組合せ効果寄り。

保存: `n3_k_of_n_*.csv`, `n3_conditional_rules_*.csv`, `relation_mine_summary.json`
