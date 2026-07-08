# AI検索.jp トップ診断

AI検索.jpのトップページとして使う静的なAI検索対応診断ページです。

想定公開URL:

`https://xn--ai-ru9di64e.jp/ai-kensaku/`

## Files

- `index.html`: 診断ページのHTML。
- `styles.css`: 診断ページ専用スタイル。
- `config.js`: AEO+LP広告主リンクの設定。
- `diagnosis.js`: 診断スコア、リスク、ロードマップ生成ロジック。
- `offers.js`: 診断結果に応じた推奨サービス表示ロジック。
- `app.js`: ブラウザUIの描画とフォーム処理。

## Affiliate Parameters

AI検索.jpからAEO+LPへ送客するリンクには、既定で `agency_code=0001` を付与します。
URLに `aff_id`、`affiliate_id`、`partner_id`、`ref` のいずれかがある場合は、`aff_id` として引き継ぎます。

`/ai_kensaku_affiliate.js` がクリック時に `click_id` も付与するため、AEO+LP側では新規登録時に `agency_code`、`aff_id`、`click_id`、登録ユーザーIDを保存してください。
