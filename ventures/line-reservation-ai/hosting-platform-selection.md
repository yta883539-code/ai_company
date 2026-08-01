# ホスティング基盤の選定

## 背景
tech-stack.mdでは「サーバーレス関数(例: Cloud Functions / Lambda相当)を想定」という
方向性のみを記載し、具体的な採用先は未確定のままだった。automated-test-suite.mdの
「次の課題」でも「ホスティング基盤が固まった段階でCIでの自動実行を検討する」としており、
prototype/engine.pyの実装がある程度進んだ今、具体的な候補を比較し方針を決めておく。

本ドキュメントは技術選定(比較・決定)のみを行うものであり、実際のアカウント作成・
プロジェクト作成・支払い設定は行わない(手順6の絶対厳守事項によりオーナー承認が必要な
アクションのため、着手時点で改めてpending-approval.mdに記録する)。

## 前提条件(要件の整理)
- LINE Messaging APIのWebhookを受信する公開HTTPSエンドポイントが必要(数秒以内に応答する必要あり)。
- トラフィックは低い(1店舗あたり1日数十件程度を想定)ため、従量課金・使わない時間はゼロ課金に
  近い構成が望ましい(tech-stack.mdの「限界費用がほぼゼロに近い設計」方針と一致)。
- prototype/engine.pyは標準ライブラリのみのPythonで実装済み。言語・ランタイムを変えると
  移植コストが発生するため、Pythonをそのまま実行できることを優先する。
- idle-conversation-trigger-design.mdで設計済みの「Webhook受信便乗トリガー」方式(専用
  スケジューラを持たず、Webhookリクエストのたびに間引き付きでmaybe_run_idle_cleanup()/
  maybe_run_archive()を呼ぶ)と相性が良いこと。
- 予約データ・会話状態は現状engine.py内のインメモリ辞書だが、実運用では関数の再起動・
  スケールアウトで状態が失われるため、軽量な永続ストア(スプレッドシート的なシンプルさ、
  tech-stack.md参照)への置き換えが前提となる。

## 比較した候補

| 候補 | Python実行 | 低トラフィック時コスト | 状態ストアとの相性 | 運用の手軽さ | 備考 |
|---|---|---|---|---|---|
| GCP Cloud Functions (Python) + Firestore | ◎ 標準サポート | ◎ 月200万回まで無料枠、以降従量課金 | ◎ Firestoreはドキュメント単位のシンプルなKVに近く、engine.pyの辞書構造(会話状態・予約枠)と親和性が高い | ◎ サーバー管理不要、コンソールも平易 | 言語をPythonのまま移行でき最も移植コストが低い |
| AWS Lambda (Python) + DynamoDB | ◎ 標準サポート | ◎ 月100万回まで無料枠、以降従量課金 | ○ DynamoDBもKV的だがスキーマ設計・課金体系(RCU/WCU or オンデマンド)の学習コストがGCPよりやや高い | ○ サーバー管理不要だがIAM等の設定項目が多く初期学習コストが高め | 機能・信頼性は十分だが本ventureの規模には設定の複雑さが過剰 |
| Cloudflare Workers + Durable Objects/KV | △ Python実行はベータ相当(Pyodide経由)で標準ライブラリ制約あり | ◎ 無料枠が手厚くリクエスト単価も安い | ○ Durable Objectsは会話単位の状態保持に向くが概念習得コストがある | △ Pythonサポートが発展途上でengine.pyの移植に伴うリスクが読みにくい | エッジ実行の低レイテンシは魅力だがPython実行の成熟度が現時点でネック |
| Fly.io / Render等のコンテナ常駐PaaS | ◎ 任意のPythonランタイムをそのまま実行可能 | △ 常駐(最小インスタンス数1)前提のプランが多く、低トラフィックでも一定の固定費が発生しやすい | ◎ 任意のDB(SQLite永続ボリューム等)を自由に組み合わせ可能 | ○ Dockerfile運用に慣れていれば容易 | tech-stack.mdの「限界費用がほぼゼロ」方針とは相性がやや悪い(常駐課金) |

## 決定
**GCP Cloud Functions (Python) + Firestore** を第一候補として採用する。

理由:
1. prototype/engine.pyがPython標準ライブラリのみで書かれており、Cloud Functionsの
   Python 3ランタイムへほぼそのまま移植できる(言語移植コストが実質ゼロ)。
2. 無料枠(月200万回呼び出し)だけで立ち上げ期の低トラフィックを十分カバーでき、
   tech-stack.mdの「限界費用がほぼゼロに近い設計」方針と合致する。
3. Firestoreはドキュメント単位のシンプルなデータモデルで、engine.py内の
   `_ConversationState`・`BookingSlotManager`の予約枠辞書といった既存のインメモリ構造を
   比較的小さな変更でドキュメント/コレクションへ置き換えられる見込み。
4. Webhook受信のたびに関数が起動する構成のため、idle-conversation-trigger-design.mdの
   「Webhook受信便乗トリガー」方式(専用スケジューラ不要)をそのまま活かせる。

Fly.io等の常駐コンテナ型は自由度が高い一方、低トラフィックでも一定の固定費が発生しやすく
今回のMVP方針とは合わないため見送り。AWS LambdaはGCPと同等の要件を満たせるが、
IAM等の設定項目の多さから初期の学習コストがやや高いと判断し次点とした。Cloudflare
Workersは低コストで魅力的だがPython実行環境が発展途上のため、標準ライブラリの挙動に
差異が出た場合の手戻りリスクを避け、今回は見送った。

## 未確定・今後の課題
- Firestoreへの具体的なデータモデル(コレクション設計: 会話状態・予約枠・通知ログの
  それぞれをどう分割するか)は未設計。次のステップとして着手候補とする。
- GCPプロジェクトの実際の作成・請求先アカウントの設定は「アカウント作成」に該当するため、
  着手時点で改めてpending-approval.mdに記録しオーナー承認を得てから行う(本ドキュメントの
  検討・決定自体は実行を伴わないため今回はpending-approval.md記載を要しない)。
- Cloud FunctionsからLINE Messaging API・LLM APIへの外向き通信のタイムアウト設計
  (LLM応答待ちでWebhook応答が遅延した場合の挙動)は未検討。
- CI(GitHub Actions等)からCloud Functionsへのデプロイ自動化は、実際のGCPプロジェクト
  作成後の課題として残す。
