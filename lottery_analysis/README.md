# 宝くじ予測分析（ナンバーズ3軸＋ビンゴ5）

運ではなく**予測問題**として、過去抽選データから指標・関連性・金額ROIを検証するワークスペースです。

## データソース

| 対象 | URL | 役割 |
|------|-----|------|
| Numbers3 | https://numbers-renban.tokyo/numbers3/result_all | 抽選番号・ストレート口数・当せん金 |
| Bingo5 | https://bingo5.money-plan.net/history/ | 抽選番号・1等口数・当せん金 |
| みずほ公式 | backnumber ページ | 参照用（当環境ではJS/アクセス制限で取得不可） |

## 使い方

```bash
cd lottery_analysis
pip install -r requirements.txt
python scripts/fetch_data.py
python scripts/clean_data.py
python scripts/analyze.py          # 番号予測の棄却（全体）
python scripts/payout_ev.py        # 参考: 単価最適化（予想ではない）
python scripts/predict_hypotheses.py  # 本線: 予想仮説＋¥1000運用
python scripts/foresight_exhaustive.py  # トップ5先読み網羅
python scripts/relation_mine.py         # 関係性探査
python scripts/horizon_analysis.py      # 毎回/数日/週の再分析
```

主なレポート:
- ホライズン別再分析: `reports/HORIZON_ANALYSIS_REPORT.md`
- 予想仮説と予算制約: `reports/PREDICTION_AXIS_REPORT.md`
- 番号予測棄却: `reports/REPORT.md`
- ペイアウト参考: `reports/PAYOUT_EV_REPORT.md`
## 検証の枠組み

1. 帰無仮説: IID一様乱数
2. 記述統計（頻度・連・スライド等）は必ず帰無シミュレーションと比較
3. 予測は時系列ウォークフォワード（リーク禁止）
4. 戦略はホールドアウト区間の的中率と円ROIで評価
5. ミラーデータの連続同一数字ストリークは汚染として除去してから評価

「法則に見えるもの」は、上記を通らない限り採用しません。
