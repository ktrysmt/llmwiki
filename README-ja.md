# llmwiki

[English / 英語](README.md)

任意のディレクトリに溜めたテキストファイルから、エンティティベースのナレッジWikiを自動生成・維持する Claude Code プラグイン。

[Andrej Karpathy の LLM Wiki パターン](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)を構造の土台とし、[karesansui-u/delta-zero](https://github.com/karesansui-u/delta-zero) に着想を得た矛盾管理機能を加えたもの。

## 前提条件

- Python >= 3.12

## 構成

```
.claude-plugin/
  plugin.json               # プラグインマニフェスト
skills/
  make/                     # /llmwiki:make -- Wiki生成・更新
    SKILL.md
    scripts/
      llmwiki_preprocess.py # 決定論的前処理 + sha256変更検出
      makeindex.py          # Wikiカタログ生成
      llmwiki_decay.py      # Decay候補検出
    llmwiki/
      schema.md             # Wikiページのテンプレート+マージルール
  query/                    # /llmwiki:query -- 自然言語でWikiに質問
    SKILL.md
  lint/                     # /llmwiki:lint -- 健全性チェック+Decay降格
    SKILL.md
  metabolize/               # /llmwiki:metabolize -- 矛盾の検出・解決
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
| /llmwiki:make | 入力ファイルからWikiを生成・更新 | 自動(dormant promotion含む) |
| /llmwiki:query | Wikiに自然言語で質問し回答を得る | フィードバック時のみ(要承認) |
| /llmwiki:lint | 健全性チェック + Decay/Promotion提案 | 降格・昇格時のみ(要承認) |
| /llmwiki:metabolize | 矛盾の検出・分類・解決(偽陽性含む) | 要承認 |
| /llmwiki:docs | テーマ指定でドキュメント生成 | なし(外部出力のみ) |

## 使い方

### /llmwiki:make -- Wiki生成・更新

```
/llmwiki:make              # プロジェクトルートをスキャン
/llmwiki:make ~/work/dump  # 外部ディレクトリをスキャン
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
- contradictions（「needs review」フラグの件数。/llmwiki:metabolize への導線を案内）
- decay candidates（被参照0 かつ90日以上未更新のページ）
- promotion candidates（dormant だが被参照 > 0 のページ）

### /llmwiki:metabolize -- 矛盾の解決

```
/llmwiki:metabolize
```

Wiki内の「needs review」フラグ（矛盾）を llmwiki 独自の実用分類 -- temporal / scope / genuine / none（偽陽性） -- に分類し、人間の判断を仰いで解決する。
genuine 型の矛盾解決時は source_type の信頼度順序（primary > secondary > derived）を考慮して優先候補を提示する。

### /llmwiki:docs -- ドキュメント生成

```
/llmwiki:docs 本番環境のアーキテクチャ概要
```

Wikiの知識を組み合わせ、テーマ指定の構造化ドキュメントを生成する。

## インストール

プラグインとして（全スキルが一括でインストールされる）:

```
/plugin marketplace add ktrysmt/claude-plugins
/plugin install llmwiki@ktrysmt
```

## ルール

- 入力ディレクトリは読み取り専用。スキルは変更・削除しない
- Wikiページは削除しない。stale/orphan はフラグのみ
- 矛盾する情報は両値を日付付きで保持しフラグする。LLMは解決しない
- エンティティIDは小文字 kebab-case、aliases は日英両方
- source_type の信頼度順序: primary > secondary > derived。判定はパス+内容の両方から行う
- /llmwiki:metabolize, /llmwiki:lint の降格・昇格, /llmwiki:query のフィードバックは人間の承認が必要
- 全スキルの操作は `.llmwiki/log.md` に時系列で記録される
