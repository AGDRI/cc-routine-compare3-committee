# 新しいテーマで委員会を立ち上げる手順

テーマ固有の情報は `data/state.json` にしか無い。ルーティンのプロンプトもページも rules.md もテーマ非依存なので、そのままコピーして使う。

## 1. リポジトリを作る

```
cp -r committee-template <theme>-committee-repo
cd <theme>-committee-repo
# data/state.json の ____ を埋める（下の「state.json の埋め方」参照）
git init && git add -A
git -c user.email=noreply@anthropic.com -c user.name=Claude commit -m "Set up <theme> committee"
~/.local/bin/gh repo create cc-routine-<theme>-committee --public --source=. --remote=origin --push
```

push はサンドボックスのネットワーク制限に当たるので `dangerouslyDisableSandbox: true` で実行する。

## 2. ルーティンを作る

`RemoteTrigger` の `create` に以下を渡す。**`ROUTINE_PROMPT.md` の本文（`---` より下）をそのまま** `events[0].data.message.content` に入れる。テーマごとの書き換えは不要。

```json
{"name": "<テーマ>委員会ラウンド進行",
 "cron_expression": "0 */2 * * *",
 "job_config": {"ccr": {
   "environment_id": "env_01VwsGefcy95FzegPjcNrSh1",
   "session_context": {
     "model": "claude-sonnet-5",
     "allowed_tools": ["Read","Write","Edit","Bash","WebSearch","WebFetch"],
     "sources": [{"git_repository": {"url": "https://github.com/AGDRI/cc-routine-<theme>-committee"}}]},
   "events": [{"data": {"message": {"role": "user", "content": "<ROUTINE_PROMPT.md の本文>"}}}]}}}
```

注意:
- `environment_id` は必須。省略すると 400 になる。
- `update` は `job_config` を**丸ごと置き換える**。部分更新するとプロンプトが消えるので、必ず `events` 全体を再送する。
- cron の「分」はサーバー側で実行時刻付近に書き換えられる。時刻の指定は「何時間おきか」だけが効くと考えてよい。

## 3. ページを公開する

```
cp committee-template/page.html <theme>-committee.html
# <title> の1行だけテーマ名に書き換える
```

`Artifact` で publish（`capabilities: {"db": {}}`、favicon は絵文字1〜2字）。file_path がURLを決めるので、テーマごとに別ファイル名にすること。

## 4. 初回サイクルを試験実行して検証する

`RemoteTrigger` の `run` を1回打ち、5分ほど待って `get_run_log` で確認。生成された `cycle-1.json` を検証する:

- `rounds[].statements` 配列がある（人物名フィールドではない）
- 各ラウンドの口火を切る人物が前ラウンドと異なる
- 全メンバーが各ラウンドで最低1回発言し、サイクル内に最低1ラウンド同一人物の二度発言がある
- `conclusion` に `probability` がなく `stance` / `outlook`（bull > base > bear）がある
- guest があれば sources が実在URL、statements の中間位置、直後に委員の反応がある

## 5. 同期ループを回す

**クラウド側から Artifact へは書き込めない**（承認待ちで固まる。検証済み）。**ページ側から GitHub も読めない**（CSP。jsDelivr は `/npm/` のみで `/gh/` は不可）。したがって同期はインタラクティブセッションからしかできない。

`ScheduleWakeup` で1時間ごとに自分を起こし、以下を行うループを組む:

1. リポジトリを `git pull`（`dangerouslyDisableSandbox: true`）
2. 未同期のサイクルがあれば `Artifact` の `write_db` に batch で書き込む:
   - `cycles/cycle-N` ← `file_path` でJSONを直接指定
   - `state/meta` ← state.json の deskName/theme/subject/premise/scope/entryPrice/decisionHorizon/stances/outlookLabels/targetRoundsPerCycle/targetCycles/currentCycle/cadence/updatedAt/team
   - `meta/audit` ← `data/meta/audit.json` を `{"entries": [...]}` に包んだファイルを `file_path` で指定
3. 上記4の項目を検証
4. 次の `ScheduleWakeup`（3600秒）を入れる。`currentCycle > targetCycles` かつ全同期済みなら `stop: true`

報告は静かに。stance が変わった／base が前サイクル比±5%以上動いた／委員会が rules.md に自己修正ルールを追記した／検証で問題が出た／エラーで止まった、のいずれかのときだけ数行で報告する。

## state.json の埋め方

| フィールド | 中身 |
|---|---|
| `deskName` | ページ上部の小さなラベル。例「MEC Coverage Desk — 小規模投資会社 5人合議制」 |
| `theme` | 設問を1文で。**意思決定の形にする**。「Xは年内に◯円になるか」のような点予測にしないこと |
| `subject` | 対象（code / name / note） |
| `premise` | 設置者の仮説。「未検証の作業前提であり、妥当性自体も検証対象」と明記する |
| `scope.focus` | 議論すべき論点の列挙 |
| `scope.exclude` | **設置者が一般論の例として挙げただけの事柄**。ここに入れないと委員会が検証テーマに格上げしてしまう（メックで液冷化がそうなった） |
| `entryPrice` / `decisionHorizon` | ポジションの取得単価と判断期限。該当しないテーマなら null |
| `stances` | 結論の選択肢。投資以外なら「採用/保留/却下」等に差し替える |
| `outlookLabels` | 3シナリオの呼び名と単位 |
| `team` | メンバー。**役職の上下と学歴・経歴を相関させないこと**（設置者の明示的な要望） |

## 設計上の勘所

- **問いの形**: 点予測は当てられない。「何をすべきか」＋「3シナリオとその根拠」の形にすると、外れようのない予測ごっこにならず判断材料になる。
- **堂々巡りの防止**: 少人数固定だと必ず「一理ありますね」で収束する。rules.md の外部招聘（R1）と停滞判定（R2）がこれを壊す仕掛け。
- **自己修正の器**: 運営ルールをプロンプトではなくリポジトリの rules.md に置くことで、委員会自身が自己監査（R5）で問題を見つけてルールを追記できる。設置者が毎回指摘しなくても軌道修正が起きる。
- **変更してよい領域の線引き**: theme / premise / scope / subject / entryPrice / decisionHorizon / targetCycles / team / stances は設置者の領域。委員会は触らない。
