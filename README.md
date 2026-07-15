# Club Scout（cloud_model）

広尾サラブレッド倶楽部向けのカタログ即断ツール置き場です。

> **意思決定支援であり、的中・利益・満口取得を保証するものではありません。**

## 正本（今朝 Desktop 時点）

`club_scout/` … `C:\Users\youmz\Desktop\club_scout` を zip で受け取った正本。

```
club_scout/
  POCKET_CARD.txt
  decision.py / decide_cli.py / scorer.py / app.py …
  rules/buy_checklist.yaml      # 配点・即PASS・コンボ
  rules/hiroo_hit_map.yaml      # 厩舎・父・ヒット地図
  data/family_trainer_ranks.json
  data/candidates.json
  …
```

ローカル CLI 例:

```bash
cd club_scout
python decide_cli.py --name ディメンシオン'24 --dam ディメンシオン --trainer 須貝尚介 --sire ロードカナロア --price 2.2
```

母→母母の DB 解決は Autumn_Horses 側 DB（`config/db.yaml`）がある環境で有効。本公開リポ単体では JSON ランク＋YAML フォールバックが主になります。

## スマホ判断シート（GitHub Pages・ルート）

```
index.html              … NotebookLM風の判断シート1枚（評価点・基準・見る順）
mobile.html             … 点数計算機（補助）
manifest.webmanifest / sw.js / icon.svg
```

- 期待URL: https://youmzain-2003.github.io/cloud_model/
- Pages 初回だけ Settings → Pages → **Deploy from a branch** → `main` / `/ (root)` が必要（API では 403）

スマホ: URL を一度開く → ホーム画面に追加 → カタログ横でシート参照。

## 判定尺（正本と同じ）

| スコア | verdict |
|--------|---------|
| 12+ | GO |
| 8–11 | HOLD |
| 〜7 | PASS |

即PASS: 満口 / 骨折・跛行・手術・予後不良 / 一口4万超

## メモ

- private `Autumn_Horses` の同梱版と同期するときは、まずこの `club_scout/` を正とする。
- ルートの `mobile.html` は単体配布用。点数表を正本 YAML に完全一致させる作業は随時。
