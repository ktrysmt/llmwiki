# llmwiki

[English](README.md) | 日本語

任意のディレクトリに溜めたテキストファイルから、エンティティベースのナレッジWikiを自動生成・維持する Claude Code プラグイン。

[Andrej Karpathy の LLM Wiki パターン](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)を構造の土台とし、[karesansui-u/delta-zero](https://github.com/karesansui-u/delta-zero) に着想を得た矛盾管理機能を加えたもの。

## 前提条件

- Python >= 3.12

## インストール

プラグインとして（全スキルが一括でインストールされる）:

```
/plugin marketplace add https://github.com/ktrysmt/claude-plugins.git
/plugin install llmwiki@ktrysmt
```

## アップデート

```
claude plugin update llmwiki@ktrysmt
```

更新後、Claude Code を再起動すると新しいバージョンが反映される。

## 構成

```
.claude-plugin/
  plugin.json               # プラグインマニフェスト
skills/
  import/                   # /llmwiki:import -- Wiki生成・更新
    SKILL.md
    scripts/
      llmwiki_preprocess.py # 決定論的前処理 + sha256変更検出
      makeindex.py          # Wikiカタログ生成
      llmwiki_decay.py      # Decay候補検出
    llmwiki/
      schema.md             # Wikiページのテンプレート+マージルール
  query/                    # /llmwiki:query -- 自然言語でWikiに質問
    SKILL.md
  lint/                     # /llmwiki:lint -- 健全性チェック(検出・報告のみ)
    SKILL.md
  fix/                      # /llmwiki:fix -- 矛盾解決・降格・昇格の実行
    SKILL.md
  docs/                     # /llmwiki:docs -- Wikiからドキュメント生成
    SKILL.md
```

実行すると、プロジェクト側に `.llmwiki/` が生成される:

```
<project>/
  .llmwiki/
    config.json               # 永続設定 (input_dir 等)
    index.xml                  # エンティティカタログ (自動生成)
    entities.json             # エンティティ辞書 (蓄積される)
    entities/<category>/*.md  # Wikiページ (蓄積される)
    syntheses/*.md            # 合成ドキュメント (llmwiki:query が生成)
    log.md                    # セッション履歴 (追記される)
```

## スキル一覧

| スキル | 用途 | 書き込み |
|---|---|---|
| /llmwiki:import | 入力ファイルからWikiを生成・更新 | 自動(dormant promotion含む) |
| /llmwiki:query | Wikiに自然言語で質問し回答を得る | フィードバック時のみ(要承認) |
| /llmwiki:lint | 健全性チェック(検出・報告のみ) | なし(読み取り専用) |
| /llmwiki:fix | 矛盾解決・降格・昇格の実行 | 要承認 |
| /llmwiki:docs | テーマ指定でドキュメント生成 | なし(外部出力のみ) |

## 使い方

### /llmwiki:import -- Wiki生成・更新

```
/llmwiki:import              # プロジェクトルートをスキャン
/llmwiki:import ~/work/dump  # 外部ディレクトリをスキャン
```

Phase 0（前処理） -> Phase 1（LLMインジェスト） -> Phase 2（検証） の順に処理。
出力先はプロジェクトルートの `.llmwiki/`。

入力ディレクトリの引数は省略可能。省略時は `.llmwiki/config.json` に保存済みのパス、またはプロジェクトルートがデフォルトとなる。使用したパスは常に `config.json` に永続化される。

ソースファイルの SHA-256 ハッシュを frontmatter に記録し、内容変更・ソース消失を検出する:
- 新規ファイル: フルインジェスト
- 内容更新（sha256不一致）: 差分マージ
- ソース消失: Source Filesに記録（ページは削除しない）
- dormant ページ: 新規ソースがインジェストされた場合に自動で active に復帰

各ソースの `source_type` をファイルのパスと内容から判定し記録する（primary > secondary > derived）。

対象形式: `.json`, `.md`, `.csv`, `.tsv`, `.yaml`, `.yml`, `.hcl`, `.sh`

### /llmwiki:query -- Wikiへの質問

```
/llmwiki:query VPCのCIDR範囲は？
```

Wikiに蓄積された知識に対して自然言語で質問し、回答を得る。
回答過程で発見された関係性・新規エンティティ・矛盾・dormant promotionはユーザー承認の上でWikiにフィードバックされる。
価値ある合成回答は `.llmwiki/syntheses/` に保存して知識を蓄積できる。

### /llmwiki:lint -- 健全性チェック + Decay

```
/llmwiki:lint
```

以下を検出し修正アクションを提案する:
- orphan pages, broken links, stale pages, uncovered files
- contradictions（「needs review」フラグの件数。/llmwiki:fix への導線を案内）
- decay candidates（被参照0 かつ90日以上未更新のページ）
- promotion candidates（dormant だが被参照 > 0 のページ）

### /llmwiki:fix -- 問題の修正

```
/llmwiki:fix
```

lintが検出した問題を修正する: 矛盾を実用分類（temporal / scope / genuine / none）に分類して解決し、decay降格とdormant昇格を実行する。
genuine 型の矛盾解決時は source_type の信頼度順序（primary > secondary > derived）を考慮して優先候補を提示する。

### /llmwiki:docs -- ドキュメント生成

```
/llmwiki:docs 本番環境のアーキテクチャ概要
```

Wikiの知識を組み合わせ、テーマ指定の構造化ドキュメントを生成する。

#### Agent Teams によるバルク生成

`/llmwiki:docs` は1回の実行で1ドキュメントを生成する。環境別・プロダクト別など複数ドキュメントを一括で必要とする場合は、Agent Teams による並列生成を指示する:

```
以下のテーマそれぞれについて /llmwiki:docs を実行し、
Agent Teams で並列に処理して docs/ に保存してください:

- Production productA アーキテクチャ
- Production productB アーキテクチャ
- Test環境 構成概要
- デプロイ手順書
```

Claude Code がテーマごとにチームメンバーを割り当て、各メンバーが独立してWikiを読み、ドキュメントを生成し、指定パスに書き出す。以下のようなツリー構造のドメインを扱う場合に有効:

```
production/
  productA/  (EC2, RDS, ...)
  productB/  (ECS, ElastiCache, ...)
test/
  productA/
  productB/
```

追加のスキルや設定は不要。LLM がユーザーの指示を解釈して柔軟に動作する。

## 設定

設定は `.llmwiki/config.json` に保存される（初回の `/llmwiki:import` 実行時に自動生成）。カスタマイズはこのファイルを直接編集する。

```json
{
  "input_dir": "/absolute/path/to/input",
  "exclude_patterns": [
    "submodule-a/",
    "vendor/legacy-tool/",
    "*.generated.ts"
  ],
  "auto_approve": {
    "query_save_synthesis": true
  }
}
```

| キー | 型 | デフォルト | 説明 |
|---|---|---|---|
| `input_dir` | string | (プロジェクトルート) | 入力ディレクトリの絶対パス |
| `exclude_patterns` | string[] | `[]` | スキャン対象から除外する glob パターン（`.gitignore` の後に適用） |
| `auto_approve.query_save_synthesis` | bool | `true` | 合成回答の保存時にユーザー確認をスキップする |

### exclude_patterns

`.gitignore` ではカバーできないファイルやディレクトリ（サブモジュール、vendor 依存、生成ファイルなど）を除外する。gitignore 互換の glob 記法を使用:

| パターン | 効果 |
|---|---|
| `vendor/` | `vendor/` ディレクトリ以下を全て除外 |
| `sub/deep/` | ネストされたディレクトリを除外 |
| `*.generated.ts` | 任意の階層で glob にマッチするファイルを除外 |
| `ven*/` | ディレクトリパターンでもワイルドカードが使える |

パターンは `.gitignore` によるフィルタリングの後に適用されるため、`.gitignore` に既にある項目を重複して書く必要はない。

## ルール

- 入力ディレクトリは読み取り専用。スキルは変更・削除しない
- Wikiページは削除しない。stale/orphan はフラグのみ
- 矛盾する情報は両値を日付付きで保持しフラグする。LLMは解決しない
- エンティティIDは小文字 kebab-case、aliases は日英両方
- source_type の信頼度順序: primary > secondary > derived。判定はパス+内容の両方から行う
- /llmwiki:fix, /llmwiki:query のフィードバックは人間の承認が必要
- 全スキルの操作は `.llmwiki/log.md` に時系列で記録される

## `.llmwiki/` の管理

`.llmwiki/` は通常のビルド成果物ではない。Phase 1（LLMインジェスト）では `source_type` の判定、エンティティ抽出、矛盾検出といった非決定的な判断が含まれるため、同じ入力ファイルから同一のWiki状態が再現される保証がない。`_site/` や `node_modules/` とは異なり、入力だけから再生成できないデータとして扱う必要がある。

### パターン A: git 管理（チーム利用時の推奨）

人間がスキルを直接実行する場合は `.llmwiki/` を git で管理する。

- チームメンバー間でWiki状態を共有できる
- `git checkout` / `git revert` によるロールバック
- `/llmwiki:docs` の出力を特定の commit に紐づけて再現できる
- `/llmwiki:fix` の解決履歴が保持される

### パターン B: CI キャッシュ（CI 専用ワークフロー）

スキルの実行を CI（GitHub Actions 等）に限定する場合は、git にコミットせず CI キャッシュとして管理できる。

- `actions/cache` を入力ファイルのハッシュでキー付けし、差分処理（SHA-256 比較）を有効にする
- キャッシュ消失時のフォールバックとして永続ストレージ（S3 等）にバックアップを置く
- 注意: キャッシュが消えるとフル再生成が走り、LLM の非決定性によりWiki状態が変わりうる

スキルを実行する専用の CI パイプラインがない限り、パターン A を推奨する。

## Changelog

### v0.1

- テキストファイルからエンティティベースのWiki生成 (`/llmwiki:import`)
- 自然言語クエリとフィードバックループ (`/llmwiki:query`)
- "needs review" フラグによる矛盾検出と4類型分類 (`/llmwiki:fix`)
- 健全性チェック: orphan pages, broken links, stale pages, uncovered files (`/llmwiki:lint`)
- dormant ページの decay/promotion ライフサイクル (`/llmwiki:fix`)
- SHA-256 による変更検出と差分マージ
- ソース信頼度順序: primary > secondary > derived
- Wiki知識からのドキュメント生成 (`/llmwiki:docs`)
- config.json の exclude_patterns 対応

### v0.2

- primary 同士の temporal 矛盾の自動解消（常に有効）
- 矛盾の経過日数に基づく緊急度スコア
- 関連エンティティ間のクロスエンティティ矛盾検出（セマンティックチェック）
- 矛盾解消後の波及分析によるカスケード矛盾の防止
- ソースファイル別・カテゴリ別の矛盾統計（低品質ソースの特定）
- ファクト単位の来歴追跡: Key Facts に `[source: filename, type, date]` タグ
- lint での来歴欠損検出
- fix での来歴補完（矛盾解消時にページ全体の来歴を埋める）
- 検証不能な DeltaZero 記述を実在する研究に差し替え (EMNLP 2024, Chroma Research)

### v0.3

- スキル名を整理: `/llmwiki:make` → `/llmwiki:import`、`/llmwiki:metabolize` → `/llmwiki:fix`
- `/llmwiki:lint` を読み取り専用化（検出とレポートのみ）
- decay demotion と dormant promotion を `/llmwiki:lint` から `/llmwiki:fix` に移動し、承認が必要な書き込みを単一スキルに集約
- `/llmwiki:update` を追加: import → lint → fix を 1 コマンドで実行するパイプライン。決定論的な前処理をフェーズ間で共有
- `/llmwiki:query` のシンセシス保存を承認不要化（自動保存し事後報告）
- 全 `SKILL.md` に YAML frontmatter を追加 (`name`, `description`, `allowed-tools`, `argument-hint`)。副作用を持つスキルには `disable-model-invocation: true` を設定して自動起動を抑止
