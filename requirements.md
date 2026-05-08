# Realtime Meeting Copilot 要件定義

**作成日:** 2026-05-08  
**対象:** gpt-realtime-2 / Realtime API を利用した、会議内容をリアルタイムに構造化し成果物・アクションへ変換する疎結合システム  
**前提:** Hermes への組み込みは後段。まずは Hermes に依存しない独立システムとして設計する。

---

## 1. 背景

Google Meet / Zoom などの会議音声をリアルタイムに理解し、単なる文字起こしや翻訳に留まらず、会議目的に応じて以下を並列に進めるシステムを作る。

- 文字起こし
- 議事録・要約
- 質問リストの生成と優先順位づけ
- 要件定義
- リアルタイム図解
- Issue 候補作成・登録
- 会議終了後の実装開始

既存のリアルタイム翻訳OSSのような音声ルーティングを入口にしつつ、プロダクトの主眼は **Meeting → Structured Intent → Artifacts → Actions** への変換に置く。

---

## 2. 基本方針

### 2.1 Hermes 非依存・疎結合を優先

初期実装では Hermes に密結合しない。

- Realtime 音声処理
- 会議状態管理
- ワーカー実行
- 成果物生成
- 外部サービス連携
- 実装エージェント起動

を独立したコンポーネントとして設計する。

Hermes、Codex、Claude Code、OpenCode、GitHub Actions、Linear、Notion などは、後段で接続できる **外部実行先 / 外部ツール** として扱う。

### 2.2 Realtime モデルは「耳・即時判断・トリガー」に集中

Realtime モデルにすべての重い処理を担わせない。

Realtime 側の責務:

- 音声のリアルタイム理解
- partial / final transcript の生成
- 重要イベントの検出
- 会議中に出すべき短い質問・確認の生成
- ツール呼び出しやワーカー起動のトリガー

バックエンドワーカー側の責務:

- 長文要約
- 要件定義の整形
- Issue 候補の統合・重複排除
- 図解生成
- モック生成
- 実装計画生成
- 外部サービス登録
- コード実装エージェント起動

### 2.3 順次処理ではなく並列パイプライン

会議中に発生する transcript event を中心に、複数ワーカーが並列に状態を更新する。

```text
Audio Stream
  ↓
Realtime Session
  ↓
Transcript / Event Stream
  ↓
Event Bus + State Store
  ├─ Transcript Worker
  ├─ Rolling Summary Worker
  ├─ Question Prioritization Worker
  ├─ Requirement Worker
  ├─ Decision / Risk Worker
  ├─ Diagram Worker
  ├─ Mockup Worker
  ├─ Issue Candidate Worker
  └─ Post-meeting Action Worker
```

---

## 3. 想定ユースケース

### 3.1 開発相談 / 要件定義会議

**ゴール:** 会議時間内に実装に必要な未確定事項を潰し、会議終了後すぐ開発を開始できる状態にする。

主な出力:

- transcript.md
- summary.md
- requirements.md
- decisions.md
- open_questions.md
- architecture.md
- issue_candidates.json
- implementation_plan.md
- mockups/

リアルタイム支援:

- 要件を満たすために必要な質問を優先順位付きで提示
- UI / API / DB / 権限 / エラーハンドリングなどの未確認事項を検出
- 会議中に簡易モックや図解を提示
- 会議後に Issue 登録、ブランチ作成、実装エージェント起動

### 3.2 営業 / 商談

**ゴール:** 協業可能性を見極め、自社利益に自然につながる次アクションへ会話を整理する。

主な出力:

- account_summary.md
- pain_points.md
- opportunity_score.md
- negotiation_notes.md
- next_actions.md
- followup_email_draft.md
- crm_update.json

リアルタイム支援:

- 相手の課題・予算感・決裁構造・導入時期を推定
- 自社の強みが活きる論点を提示
- 次に聞くべき質問を提示
- フォローアップメールや提案書ドラフトを会議後に生成

### 3.3 採用面談

**ゴール:** 採用すべきかどうかを構造化して判断し、深掘り不足をリアルタイムで補う。

主な出力:

- interview_transcript.md
- candidate_scorecard.md
- strengths.md
- concerns.md
- followup_questions.md
- hiring_recommendation.md

リアルタイム支援:

- 技術力、事業理解、自走力、カルチャーフィットなどをスコアリング
- STAR 形式で回答の具体性を評価
- 深掘りすべき質問を提示
- 面談後の評価コメントを自動生成

### 3.4 登壇 / セミナー / 講演相談

**ゴール:** 打ち合わせ中に登壇内容の骨子を固め、終了後にスライド生成を開始する。

主な出力:

- talk_brief.md
- audience_persona.md
- outline.md
- slide_structure.md
- key_messages.md
- speaker_notes_draft.md
- slides_draft.pptx / Google Slides draft

リアルタイム支援:

- 聴衆、目的、持ち帰り、ストーリーラインを整理
- 講演タイトル案や構成案を生成
- 図解やスライド構成を会議中に提示
- 会議終了後にスライド作成を開始

### 3.5 その他の展開候補

- 事業開発 / アライアンス会議
- 投資家面談 / 資金調達
- カスタマーサクセス / 導入支援
- プロダクトレビュー
- 法務 / 契約レビュー会議
- 経営会議
- 研究 / 論文ディスカッション
- 教育 / メンタリング

---

## 4. 会議モード

会議開始時にモードを選択する。

```yaml
meeting_mode:
  - development
  - sales
  - hiring
  - presentation
  - customer_success
  - fundraising
  - legal
  - executive
  - research
  - general
```

モードごとに以下を切り替える。

- 会議のゴール
- 出力成果物
- リアルタイム質問の評価基準
- スコアリング指標
- 使用可能なツール
- 会議終了後のアクション

---

## 5. 機能要件

### 5.1 音声入力

- Google Meet / Zoom / Slack Huddle 等の音声を入力できること
- macOS では BlackHole などの仮想オーディオデバイス利用を想定
- 将来的には Bot 参加、SIP、WebRTC、ブラウザ拡張なども検討
- 自分の声と相手の声の両方を扱えること
- partial transcript と final transcript を区別できること

### 5.2 文字起こし

- 会議音声をリアルタイムに文字起こしすること
- partial transcript は UI 表示用に使うこと
- final transcript は議事録・要件定義・Issue 化などの根拠として使うこと
- タイムスタンプを保持すること
- 可能であれば話者情報を保持すること

### 5.3 ローリング要約

- 30〜60秒ごとに会議内容を増分要約すること
- 要約は会議モードに応じた観点で構造化すること
- 会議終了時に最終議事録を生成すること

### 5.4 質問リスト生成・優先順位づけ

- 会議中に不足情報・曖昧な論点・意思決定が必要な点を検出すること
- 質問を以下のカテゴリに分類すること
  - blocker: 答えがないと次に進めない質問
  - high_impact: 品質・利益・意思決定に大きく影響する質問
  - clarification: 明確化した方がよい質問
  - later: 非同期確認でよい質問
- 会議中に提示する質問は数を絞ること
- 「今聞くべき質問」を優先して出すこと
- 質問が解消されたら状態を更新すること

### 5.5 要件定義

開発相談モードでは、会議中に要件定義を増分更新する。

含める項目:

- 背景・目的
- 対象ユーザー
- ユースケース
- 機能要件
- 非機能要件
- UI/UX 要件
- 権限・認証要件
- データ要件
- 外部連携
- 制約条件
- 決定事項
- 未確認事項
- 前提・仮説
- リスク
- 受け入れ条件

### 5.6 リアルタイム図解

- 会議中の概念・構造・フローを図解できること
- 図は差分更新できること
- Mermaid / SVG / HTML / Excalidraw JSON など疎結合な形式で出力すること
- 開発相談ではアーキテクチャ図、データフロー図、画面遷移図を生成すること
- 営業では課題構造、提案ストーリー、導入ステップを図解すること
- 登壇相談では講演構成やストーリーラインを図解すること

### 5.7 モック生成

- UI 要件が十分に出た場合、会議中に簡易モックを生成できること
- 初期は HTML 1枚または画像モックでよい
- 会議中に見せてフィードバックを得られること
- モックは確定仕様ではなく、議論の叩き台として扱うこと

### 5.8 Issue 候補作成

- 会議中に Issue 候補を自動生成すること
- 重複候補を統合すること
- 粒度を調整すること
- 各 Issue に根拠 transcript 範囲を紐づけること
- Issue は候補、ドラフト、承認済みの状態を持つこと

Issue 候補の例:

```json
{
  "title": "ユーザー権限ごとにダッシュボード表示を切り替える",
  "type": "feature",
  "priority": "P1",
  "confidence": 0.82,
  "source": "meeting transcript 12:30-15:10",
  "blocked_by": [
    "管理者/一般ユーザー以外のロール有無"
  ]
}
```

### 5.9 外部サービス登録

- GitHub Issue
- Linear Issue
- Notion page
- Google Docs
- Google Slides
- CRM
- ATS

などに登録できる設計にする。

初期実装では外部登録は承認制にする。

### 5.10 会議終了後アクション

会議終了時に以下を実行できること。

- 最終議事録生成
- 要件定義確定版生成
- open questions の整理
- Issue 候補の提示
- 実装計画生成
- ユーザー承認後に Issue 登録
- ユーザー承認後に実装エージェント起動

---

## 6. 非機能要件

### 6.1 低遅延

- 会議中の UI 更新は数秒以内を目標とする
- リアルタイム質問提示は会話の流れを壊さない速度で行う
- 重い処理はバックグラウンドワーカーに逃がす

### 6.2 並列実行

- transcript stream を複数ワーカーが購読できること
- 各ワーカーは独立して失敗・再試行できること
- 1つのワーカー失敗が会議全体を止めないこと

### 6.3 疎結合

- Realtime API、LLM、外部ツール、ストレージを交換可能にすること
- Hermes への依存を持たないこと
- 後から Hermes を実行エージェントとして接続できること

### 6.4 監査性

- 生成された決定事項、要件、Issue には根拠 transcript を紐づけること
- 自動生成と人間承認済みを区別すること
- 会議中の提案・質問・登録アクションのログを残すこと

### 6.5 セキュリティ / プライバシー

- 録音・文字起こしの同意を前提にすること
- 会議データの保存範囲を設定できること
- APIキーや認証情報をコードに含めないこと
- 外部送信先を明示すること
- 機密会議ではローカル保存・外部登録無効化を選べること

---

## 7. システム構成案

```text
[Audio Capture]
  - Virtual Audio Device
  - Browser Extension
  - Meeting Bot
  - SIP / WebRTC
        ↓
[Realtime Gateway]
  - gpt-realtime-2 session
  - partial/final transcript events
  - low-latency intent detection
        ↓
[Event Bus]
  - transcript.final
  - transcript.partial
  - decision.detected
  - question.created
  - requirement.updated
  - issue.candidate.created
  - meeting.ended
        ↓
[State Store]
  - transcript
  - rolling summary
  - decisions
  - requirements
  - open questions
  - artifacts
        ↓
[Parallel Workers]
  - Summary Worker
  - Question Worker
  - Requirement Worker
  - Diagram Worker
  - Mockup Worker
  - Issue Worker
  - Action Worker
        ↓
[Outputs / Integrations]
  - Markdown files
  - Web dashboard
  - Slack notifications
  - GitHub / Linear / Notion
  - Coding agents
```

---

## 8. データモデル案

### 8.1 TranscriptEvent

```json
{
  "id": "evt_...",
  "meeting_id": "mtg_...",
  "type": "partial|final",
  "speaker": "speaker_1",
  "text": "...",
  "start_ms": 123000,
  "end_ms": 128000,
  "confidence": 0.91,
  "created_at": "2026-05-08T00:00:00Z"
}
```

### 8.2 Question

```json
{
  "id": "q_...",
  "meeting_id": "mtg_...",
  "question": "管理者と一般ユーザーで表示内容は変わりますか？",
  "category": "blocker",
  "priority": 1,
  "reason": "権限設計とDB設計に影響するため",
  "status": "open|answered|dismissed",
  "source_event_ids": ["evt_..."],
  "created_at": "2026-05-08T00:00:00Z"
}
```

### 8.3 RequirementItem

```json
{
  "id": "req_...",
  "meeting_id": "mtg_...",
  "category": "functional|non_functional|ui|data|integration|security",
  "text": "ユーザーはログイン後に自分のダッシュボードを閲覧できる",
  "status": "draft|confirmed|assumption|rejected",
  "source_event_ids": ["evt_..."],
  "updated_at": "2026-05-08T00:00:00Z"
}
```

### 8.4 IssueCandidate

```json
{
  "id": "issue_...",
  "meeting_id": "mtg_...",
  "title": "ダッシュボード閲覧機能を実装する",
  "body": "...",
  "type": "feature|bug|task|spike",
  "priority": "P0|P1|P2|P3",
  "status": "candidate|draft|approved|registered|rejected",
  "blocked_by_question_ids": ["q_..."],
  "source_event_ids": ["evt_..."],
  "external_url": null
}
```

---

## 9. UI / UX 要件

### 9.1 会議中ダッシュボード

表示するもの:

- 現在の文字起こし
- ローリング要約
- 今聞くべき質問 Top 3
- 決定事項
- 未確認事項
- 生成中の図解
- Issue 候補
- モード別スコア / 進捗

### 9.2 通知方針

- 会議を邪魔しないこと
- 質問は Top 1〜3 に絞ること
- blocker のみ強調表示すること
- Slack 通知は頻度制限すること
- 重要度が低いものはダッシュボード内に留めること

### 9.3 承認 UI

以下の操作には承認を挟む。

- GitHub / Linear / Notion への登録
- CRM / ATS への登録
- 外部メール送信
- 実装エージェント起動
- PR 作成

---

## 10. MVP スコープ

最初の MVP は **Development Meeting Mode** に絞る。

### 10.1 MVPで作るもの

- 音声入力またはテキストストリーム入力
- Realtime API による文字起こし
- transcript 保存
- 30〜60秒ごとのローリング要約
- 質問リスト生成と優先順位づけ
- 要件定義 Markdown の増分更新
- Mermaid 形式の簡易図解生成
- Issue 候補 JSON 生成
- 会議終了時の implementation_plan.md 生成
- Slack または Web UI への結果表示

### 10.2 MVPでやらないもの

- 完全自動 Issue 登録
- 完全自動 PR 作成
- 本番CRM/ATS連携
- 高精度な話者分離
- 複雑なマルチモーダル画面理解
- 全会議モード対応

### 10.3 MVPの成功条件

- 30分の開発相談会議から、会議終了後5分以内に以下が生成される
  - transcript.md
  - summary.md
  - requirements.md
  - open_questions.md
  - architecture.md
  - issue_candidates.json
  - implementation_plan.md
- 会議中に blocker 質問を3件以上適切に提示できる
- Issue 候補のうち、人間が採用可能と判断するものが半数以上ある
- 生成された implementation_plan.md を元に、実装エージェントが初期実装に着手できる

---

## 11. 実装フェーズ案

### Phase 0: テキスト入力プロトタイプ

- 録音・Realtime API なし
- transcript テキストを擬似ストリームとして流す
- 並列ワーカーと成果物生成の検証を優先

### Phase 1: Realtime 文字起こし統合

- gpt-realtime-2 / Realtime API で音声入力を処理
- partial / final transcript event を生成
- transcript 保存とローリング要約を実装

### Phase 2: Development Meeting Mode

- 質問生成
- 要件定義更新
- Issue 候補生成
- Mermaid 図解生成
- implementation_plan.md 生成

### Phase 3: 会議中 UI

- Web dashboard
- Slack 通知
- Top questions 表示
- 図解表示
- Issue 候補レビュー

### Phase 4: 外部連携

- GitHub Issue 登録
- Linear 登録
- Notion / Google Docs 出力
- コーディングエージェント起動

### Phase 5: モード拡張

- Sales
- Hiring
- Presentation
- Customer Success
- Legal
- Executive

---

## 12. 未決事項

- gpt-realtime-2 の正確な API 仕様と tool calling / MCP 対応範囲
- 音声入力方式を最初にどれにするか
  - 仮想オーディオ
  - Bot 参加
  - ブラウザ拡張
  - SIP / WebRTC
- 初期 UI を Web dashboard にするか Slack 通知中心にするか
- Issue 登録先を GitHub に絞るか Linear も同時対応するか
- モック生成を MVP に含めるか Phase 3 以降に回すか
- 会議データ保存期間と削除ポリシー
- 話者分離の必要レベル

---

## 13. リスク

### 13.1 質問が多すぎて会議を邪魔する

対策:

- blocker / high_impact のみ会議中に表示
- clarification / later はダッシュボード内に留める
- 通知頻度を制限する

### 13.2 partial transcript に基づいて誤った要件化をする

対策:

- final transcript のみ確定成果物に使う
- partial は UI 表示と一時的な推論に限定する

### 13.3 自動 Issue / 実装が暴走する

対策:

- 初期は候補生成まで自動
- 外部登録・実装開始は承認制
- 生成物には根拠 transcript を必ず紐づける

### 13.4 会議内容の機密性

対策:

- 保存先と外部送信先を明示
- 機密モードでは外部連携を無効化
- ローカル保存または短期保存を選択可能にする

---

## 14. まとめ

このシステムは、単なるリアルタイム翻訳や文字起こしではなく、会議をリアルタイムに成果物とアクションへ変換するための基盤である。

初期は Hermes に依存しない疎結合な構成で、Development Meeting Mode に絞って実装するのが良い。

最終的には、会議モードごとに以下のような成果物生成とアクション実行を可能にする。

```text
開発相談     → 要件定義 / Issue / 実装開始
営業         → 商談整理 / 提案書 / CRM更新
採用         → 評価表 / 深掘り質問 / 合否判断
登壇相談     → 構成案 / スライド / 原稿
経営会議     → 決定事項 / KPI / TODO
法務会議     → 論点 / リスク / 修正文案
```

設計上の核は、以下の3点である。

1. Realtime モデルは低遅延な理解とトリガーに集中する
2. 成果物生成は並列ワーカーで進める
3. 外部登録・実装開始は承認ゲート付きで行う
