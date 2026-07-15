# Club Scout（cloud_model）

広尾サラブレッド倶楽部向けの**カタログ即断ツール**を、スマホでオフライン利用できるよう置いた公開受け皿です。

> **意思決定支援であり、的中・利益・満口取得を保証するものではありません。**

## 公開URL

- 期待URL: https://youmzain-2003.github.io/cloud_model/
- エントリ: `index.html`（`mobile.html` と同内容）

## ルート構成（Pages は `/`）

```
cloud_model/
  index.html
  mobile.html
  manifest.webmanifest
  sw.js
  icon.svg
  README.md
```

サブフォルダに置かないこと（Pages ルートとずれて 404 になります）。

## スマホでの使い方

1. HTTPS の公開URLをスマホブラウザで一度開く（Service Worker がキャッシュ）
2. 共有メニュー等から「ホーム画面に追加」
3. 以降はオフラインでも判定可能

## Pages 有効化

どちらか一方:

### A. GitHub Actions（推奨）

1. リポジトリ **Settings → Pages**
2. **Source** を **GitHub Actions** にする
3. `main` への push（または Actions の `Deploy Club Scout to GitHub Pages` を手動実行）でデプロイ

### B. Deploy from a branch

1. **Settings → Pages**
2. **Deploy from a branch** → Branch: `main` → Folder: `/ (root)` → Save

## 判定の目安

| スコア | verdict |
|--------|---------|
| 12+ | GO |
| 8–11 | HOLD |
| 〜7 | PASS |

即PASS: 満口 / 骨折・跛行・手術・予後不良 / 一口4万超

配点・牝系・厩舎辞書は `mobile.html` / `index.html` 内に埋め込み済みです（単体HTMLでオフライン可）。

## 開発メモ

- ロジック本体の開発元は private `Autumn_Horses`（`club_scout/`）。本リポは公開静的配布専用。
- ローカル確認: ルートで簡易サーバを立てて `index.html` を開く（`file://` だと SW が動かない場合あり）。
