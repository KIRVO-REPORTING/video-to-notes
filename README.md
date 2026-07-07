# youtube-local-transcribe

Caption first. Local Whisper when needed. Searchable local reports. Optional Notion or Obsidian publishing.

`youtube-local-transcribe` turns YouTube, Bilibili, TED, and other `yt-dlp` supported video URLs into local transcripts, grounded summaries, browser-readable HTML reports, and optional Notion or Obsidian knowledge-base entries.

- [中文说明](#中文说明)
- [English](#english)

## 中文说明

### 这个项目是做什么的

`youtube-local-transcribe` 是一个面向 AI Coding Agent 和命令行用户的视频资料整理工具。它会优先下载视频自带字幕，在没有合适字幕时才使用本地 Whisper 转写，并把每个视频整理成可追溯的本地报告。

这个仓库包含两部分：

- `ytlt`: Python CLI，负责环境检测、用户配置、字幕下载、本地 Whisper fallback、报告生成、Notion/Obsidian 发布和本地 dashboard。
- `codex-skill`: Codex 技能说明，让 Codex 知道如何调用 `ytlt`、读取转写文本、写出有时间戳依据的摘要报告。

### 要解决的问题

长视频、课程、访谈、发布会和研究材料通常有几个麻烦：

- 字幕、转写、摘要和来源链接分散，后续很难复查。
- 很多视频其实有字幕，不需要一上来就跑本地 Whisper。
- AI 摘要如果没有绑定原始 transcript 和时间戳，可信度和可追溯性很弱。
- 处理过的视频缺少统一索引，时间久了很难找到以前的报告。

这个项目把流程固定下来：字幕优先，本地转写作为兜底，所有结果落到本地 workspace，并生成可搜索的 HTML dashboard。用户也可以把最终报告同步到 Notion 或 Obsidian。

### 复制给 Codex 或 Claude Code 的一行配置指令

把下面这一行复制给 Codex 或 Claude Code，它就可以按这个项目的方式安装和配置：

```text
请安装并配置 youtube-local-transcribe public 分支：克隆 https://github.com/KIRVO-REPORTING/youtube-local-transcribe-skill-public 的 public 分支，进入仓库后运行 python -m pip install -e .；如果当前工具是 Codex，请把 codex-skill 安装到 ~/.codex/skills/youtube-local-transcribe；然后运行 ytlt configure，让用户选择常用语言、硬件推荐的 Whisper fallback 模型或不安装模型，以及默认输出环境 local/notion/obsidian；最后用 ytlt process "VIDEO_URL" 处理视频。
```

### 工作流程简介

1. 用户给出一个视频 URL。
2. `ytlt process "VIDEO_URL"` 调用 `yt-dlp` 获取元数据和字幕。
3. 工具优先使用人工字幕或自动字幕；字幕不可用时，才走本地 Whisper。
4. 每个视频会生成独立目录，包含 `metadata.json`、`transcript.txt` 和 `report.html`。
5. Codex 或其他 Agent 读取 `metadata.json` 与 `transcript.txt`，写入有依据的 `summary.md`。
6. `ytlt finalize "<video-folder>"` 重新渲染最终 HTML 报告，清理下载的视频文件，并刷新 dashboard。
7. 根据配置或命令参数，把报告保留在本地 dashboard，或发布/更新到 Notion、Obsidian。

### 快速安装

```bash
git clone --branch public --single-branch https://github.com/KIRVO-REPORTING/youtube-local-transcribe-skill-public.git
cd youtube-local-transcribe-skill-public
python -m pip install -e .
```

安装后先运行交互式配置：

```bash
ytlt configure
```

配置会让用户选择三件事：

1. 常用语言，例如 `zh`、`en`、`ja`。
2. 本地 Whisper fallback 模型。默认推荐项会根据当前硬件选择；也可以选择 `none` 不安装模型，但不推荐，因为无字幕视频将无法本地转写。
3. 默认输出环境：`local`、`notion` 或 `obsidian`。

也可以用非交互方式配置：

```bash
ytlt configure --language zh --model-choice recommended --environment local --execute
ytlt configure --language zh --model-choice recommended --environment notion --execute
ytlt configure --language zh --model-choice recommended --environment obsidian --execute
ytlt configure --language zh --model-choice none --environment local
```

`--execute` 会安装推荐后端、确认 ffmpeg、按硬件条件下载或配置推荐模型，并写入 workspace 配置。`ytlt setup --execute` 仍然可用，但 public 分支推荐先用 `ytlt configure`，因为它同时保存语言和输出环境偏好。

处理一个视频：

```bash
ytlt process "VIDEO_URL"
```

默认 workspace：

```text
~/Documents/youtube
```

指定其它 workspace：

```bash
ytlt process "VIDEO_URL" --workspace /path/to/workspace
```

### 常用命令

| 场景 | 命令 |
|---|---|
| 交互式选择语言、模型和输出环境 | `ytlt configure` |
| 查看硬件推荐模型 | `ytlt recommend` |
| 下载字幕并生成报告 | `ytlt process "VIDEO_URL" --language zh --open` |
| 使用浏览器 cookies | `ytlt process "VIDEO_URL" --cookies-from-browser chrome` |
| 强制本地 Whisper 转写 | `ytlt process "VIDEO_URL" --force-transcribe` |
| 字幕缺失时不做本地转写 | `ytlt process "VIDEO_URL" --no-transcribe-fallback` |
| 写好 `summary.md` 后重新生成报告 | `ytlt finalize "/path/to/video-folder" --open` |
| 发布或更新 Notion 报告 | `ytlt finalize "/path/to/video-folder" --publish-notion` |
| 发布已有处理目录到 Notion | `ytlt publish-notion "/path/to/video-folder"` |
| 发布已有处理目录到 Obsidian | `ytlt publish-obsidian "/path/to/video-folder"` |
| 同步 workspace 里的报告到 Obsidian | `ytlt sync-obsidian` |
| 临时覆盖输出环境 | `ytlt finalize "/path/to/video-folder" --environment obsidian` |
| 重建本地索引 | `ytlt rebuild-index` |
| 打开本地 dashboard | `ytlt serve --open` |

每个处理后的视频目录位于：

```text
<workspace>/processed/
```

目录通常包含：

- `metadata.json`: 视频标题、来源、平台、时长、发布时间、处理时间和 transcript 来源。
- `transcript.txt`: 字幕或本地 Whisper 生成的全文。
- `summary.md`: Agent 或用户写入的摘要。
- `report.html`: 浏览器可读报告。

### Codex Skill 安装

从克隆后的仓库安装：

```bash
mkdir -p "$HOME/.codex/skills/youtube-local-transcribe"
rsync -a --delete codex-skill/ "$HOME/.codex/skills/youtube-local-transcribe/"
```

Windows PowerShell：

```powershell
$target = Join-Path $HOME ".codex\skills\youtube-local-transcribe"; if (Test-Path $target) { Remove-Item $target -Recurse -Force }; New-Item -ItemType Directory -Force $target | Out-Null; Copy-Item ".\codex-skill\*" $target -Recurse -Force
```

替换已安装技能后，重启 Codex，让新的 `SKILL.md` 元数据生效。

然后把视频链接发给 Codex，或直接说：

```text
Use youtube-local-transcribe to process this video and create a summary report: VIDEO_URL
```

### 发布到 Notion

如果用户在 Codex、ChatGPT 或其它 agent 环境里已经连接了 Notion connector/MCP，优先走 connector/MCP 路径：让 agent 在 Notion 里创建或复用 `本地视频报告数据库`，然后在 `ytlt finalize` 生成本地报告后，用 connector/MCP 写入或更新数据库行。这个路径不需要在本机设置 `NOTION_TOKEN`，也不要声称是 CLI 直接发布。

只有在纯命令行环境、没有 Notion connector/MCP 时，才需要创建 Notion integration token，把目标页面或 data source 分享给该 integration，然后设置：

```bash
export NOTION_TOKEN="secret_..."
export NOTION_DATA_SOURCE_ID="..."
```

目标变量三选一：

- `NOTION_DATA_SOURCE_ID`: 推荐，用于 Notion database/data source dashboard。
- `NOTION_PARENT_PAGE_ID`: 在普通 Notion 页面下创建报告页面。
- `NOTION_DATABASE_ID`: 自动解析 database 的第一个 data source。

处理时发布：

```bash
ytlt process "VIDEO_URL" --language zh --publish-notion
```

已有目录发布：

```bash
ytlt publish-notion "/path/to/processed/video-folder"
```

发布成功后，`metadata.json` 会记录 `notion_page_id`、`notion_url` 和 `notion_synced_at`，后续发布会更新同一条 Notion 页面，避免重复。

如果在 `ytlt configure` 中选择了 `notion`，`ytlt process` 和 `ytlt finalize` 会默认发布到 Notion。仍然可以用 `--environment local` 临时只生成本地报告。

在 agent 环境中，如果没有 CLI token 但有 Notion connector/MCP，流程是：

1. `ytlt process "VIDEO_URL"` 生成本地 transcript 和 report。
2. Agent 读取 `metadata.json`、`transcript.txt`、`summary.md`。
3. `ytlt finalize "<video-folder>"` 刷新本地报告。
4. Agent 通过 Notion connector/MCP 创建或更新报告数据库行。
5. Agent 把 Notion row URL 和本地 report path 返回给用户。

### 发布到 Obsidian

设置 Obsidian vault 路径：

```bash
export OBSIDIAN_VAULT_PATH="/path/to/your/vault"
```

可选配置：

```bash
export OBSIDIAN_REPORTS_DIR="Video Reports"
export OBSIDIAN_INDEX_NOTE="Video Reports Dashboard.md"
```

处理或 finalize 时发布：

```bash
ytlt finalize "/path/to/processed/video-folder" --publish-obsidian
ytlt publish-obsidian "/path/to/processed/video-folder"
```

同步整个 workspace：

```bash
ytlt sync-obsidian
```

Obsidian 发布会在 vault 中创建或更新一篇 Markdown 报告，并维护一个 dashboard note。报告包含 YAML frontmatter、视频元数据、摘要、时间戳链接、本地报告路径和可选全文 transcript。

### 本地开发

```bash
python -m pip install -e .
python -m unittest discover -s tests
```

字幕优先 smoke test：

```bash
ytlt process "https://www.ted.com/talks/sir_ken_robinson_do_schools_kill_creativity" --language en --no-transcribe-fallback
```

### 注意事项

- 需要 Python 3.9 或更新版本，推荐 Python 3.10+。
- 字幕永远优先于本地 Whisper。
- public 分支推荐 `ytlt configure`；`ytlt setup --execute` 只配置模型，不保存语言和输出环境偏好。
- 选择不安装 Whisper 模型不推荐；有字幕的视频仍可处理，但无字幕视频无法本地 fallback。
- 硬件模型选择规则见 `codex-skill/references/model-selection.md`。
- workspace、下载媒体、模型、虚拟环境和构建产物会被 `.gitignore` 排除。

## English

### What this project does

`youtube-local-transcribe` is a video knowledge capture workflow for AI coding agents and command-line users. It prefers existing captions, falls back to local Whisper only when captions are missing or unsuitable, and turns each video into a traceable local report.

This repository contains:

- `ytlt`: a Python CLI for machine probing, user configuration, caption download, local Whisper fallback, report generation, Notion/Obsidian publishing, and local dashboard serving.
- `codex-skill`: a Codex skill wrapper that teaches Codex how to run `ytlt`, read transcripts, and write grounded timestamped summaries.

### Problem it solves

Long videos, courses, interviews, conference talks, and research material are hard to reuse when transcripts, summaries, and source links are scattered. Many videos already have captions, so running local Whisper first wastes time and compute. AI summaries are also hard to trust when they are not tied back to transcript text and timestamps.

This project makes the workflow repeatable: captions first, local transcription only as fallback, all artifacts stored under one local workspace, searchable HTML reports, and optional Notion or Obsidian publishing.

### One-line setup prompt for Codex or Claude Code

Copy this single line into Codex or Claude Code:

```text
Install and configure the public branch of youtube-local-transcribe: clone the public branch from https://github.com/KIRVO-REPORTING/youtube-local-transcribe-skill-public, run python -m pip install -e . from the repo, install codex-skill to ~/.codex/skills/youtube-local-transcribe if this is Codex, then run ytlt configure so the user can choose their usual language, the hardware-recommended Whisper fallback model or no model, and the default output environment local/notion/obsidian; finally process a video with ytlt process "VIDEO_URL".
```

### Workflow overview

1. The user provides a video URL.
2. `ytlt process "VIDEO_URL"` uses `yt-dlp` to fetch metadata and captions.
3. The tool uses manual or automatic captions first; if captions are unavailable, it can fall back to local Whisper.
4. Each video gets its own folder with `metadata.json`, `transcript.txt`, and `report.html`.
5. Codex or another agent reads `metadata.json` and `transcript.txt`, then writes a grounded `summary.md`.
6. `ytlt finalize "<video-folder>"` re-renders the final HTML report, removes retained downloaded video files, and refreshes the dashboard.
7. Based on configuration or command flags, keep the report local or publish/update it in Notion or Obsidian.

### Quick install

```bash
git clone --branch public --single-branch https://github.com/KIRVO-REPORTING/youtube-local-transcribe-skill-public.git
cd youtube-local-transcribe-skill-public
python -m pip install -e .
```

Run the interactive configuration wizard after installing:

```bash
ytlt configure
```

The wizard asks for:

1. Usual language, such as `zh`, `en`, or `ja`.
2. Local Whisper fallback model. The default recommendation is based on detected hardware. Choosing `none` is allowed but not recommended because captionless videos cannot be transcribed locally.
3. Default output environment: `local`, `notion`, or `obsidian`.

Non-interactive examples:

```bash
ytlt configure --language en --model-choice recommended --environment local --execute
ytlt configure --language en --model-choice recommended --environment notion --execute
ytlt configure --language en --model-choice recommended --environment obsidian --execute
ytlt configure --language en --model-choice none --environment local
```

`--execute` installs the selected backend, verifies ffmpeg, downloads or configures the recommended model when needed, and writes workspace configuration. `ytlt setup --execute` remains available, but the public branch recommends `ytlt configure` because it also saves language and output-environment preferences.

Process a video:

```bash
ytlt process "VIDEO_URL"
```

Default workspace:

```text
~/Documents/youtube
```

Use another workspace:

```bash
ytlt process "VIDEO_URL" --workspace /path/to/workspace
```

### Common commands

| Use case | Command |
|---|---|
| Choose language, model, and output environment | `ytlt configure` |
| Inspect the hardware recommendation | `ytlt recommend` |
| Download captions and build a report | `ytlt process "VIDEO_URL" --language en --open` |
| Use browser cookies | `ytlt process "VIDEO_URL" --cookies-from-browser chrome` |
| Force local Whisper transcription | `ytlt process "VIDEO_URL" --force-transcribe` |
| Skip local transcription when captions are missing | `ytlt process "VIDEO_URL" --no-transcribe-fallback` |
| Re-render after writing `summary.md` | `ytlt finalize "/path/to/video-folder" --open` |
| Publish or update a Notion report | `ytlt finalize "/path/to/video-folder" --publish-notion` |
| Publish an existing folder to Notion | `ytlt publish-notion "/path/to/video-folder"` |
| Publish an existing folder to Obsidian | `ytlt publish-obsidian "/path/to/video-folder"` |
| Sync workspace reports to Obsidian | `ytlt sync-obsidian` |
| Temporarily override output environment | `ytlt finalize "/path/to/video-folder" --environment obsidian` |
| Rebuild local index | `ytlt rebuild-index` |
| Open local dashboard | `ytlt serve --open` |

Each processed video folder is created under:

```text
<workspace>/processed/
```

Typical outputs:

- `metadata.json`: title, source URL, platform, duration, publish time, processing time, and transcript source.
- `transcript.txt`: transcript from captions or local Whisper.
- `summary.md`: summary written by an agent or user.
- `report.html`: browser-readable report.

### Codex skill install

From a cloned copy of this repo:

```bash
mkdir -p "$HOME/.codex/skills/youtube-local-transcribe"
rsync -a --delete codex-skill/ "$HOME/.codex/skills/youtube-local-transcribe/"
```

Windows PowerShell:

```powershell
$target = Join-Path $HOME ".codex\skills\youtube-local-transcribe"; if (Test-Path $target) { Remove-Item $target -Recurse -Force }; New-Item -ItemType Directory -Force $target | Out-Null; Copy-Item ".\codex-skill\*" $target -Recurse -Force
```

Restart Codex after replacing an installed skill so the new `SKILL.md` metadata is loaded.

Then send Codex a video URL or ask:

```text
Use youtube-local-transcribe to process this video and create a summary report: VIDEO_URL
```

### Publish to Notion

If the user already has a Notion connector/MCP connected in Codex, ChatGPT, or another agent environment, prefer the connector/MCP path: have the agent create or reuse the `本地视频报告数据库` Notion database, then write or update the database row after `ytlt finalize` creates the local report. This path does not require setting `NOTION_TOKEN` locally, and the agent should not claim that the CLI published to Notion.

Only for CLI-only environments without a Notion connector/MCP, create a Notion integration token, share the target page or data source with the integration, then set:

```bash
export NOTION_TOKEN="secret_..."
export NOTION_DATA_SOURCE_ID="..."
```

Use exactly one target:

- `NOTION_DATA_SOURCE_ID`: recommended for a Notion database/data source dashboard.
- `NOTION_PARENT_PAGE_ID`: create report pages under a normal Notion page.
- `NOTION_DATABASE_ID`: resolve the database's first data source automatically.

Publish while processing:

```bash
ytlt process "VIDEO_URL" --language en --publish-notion
```

Publish an existing processed folder:

```bash
ytlt publish-notion "/path/to/processed/video-folder"
```

After publishing, `metadata.json` records `notion_page_id`, `notion_url`, and `notion_synced_at`; later publishes update the same Notion page instead of creating duplicates.

If `notion` was selected in `ytlt configure`, `ytlt process` and `ytlt finalize` publish to Notion by default. Use `--environment local` to generate only local files for a single run.

In an agent environment with no CLI token but with a Notion connector/MCP, the flow is:

1. `ytlt process "VIDEO_URL"` creates local transcript and report files.
2. The agent reads `metadata.json`, `transcript.txt`, and `summary.md`.
3. `ytlt finalize "<video-folder>"` refreshes the local report.
4. The agent creates or updates the Notion database row through the connector/MCP.
5. The agent returns the Notion row URL and local report path.

### Publish to Obsidian

Set your Obsidian vault path:

```bash
export OBSIDIAN_VAULT_PATH="/path/to/your/vault"
```

Optional settings:

```bash
export OBSIDIAN_REPORTS_DIR="Video Reports"
export OBSIDIAN_INDEX_NOTE="Video Reports Dashboard.md"
```

Publish during finalization or publish an existing processed folder:

```bash
ytlt finalize "/path/to/processed/video-folder" --publish-obsidian
ytlt publish-obsidian "/path/to/processed/video-folder"
```

Sync the whole workspace:

```bash
ytlt sync-obsidian
```

Obsidian publishing creates or updates a Markdown report note in the vault and maintains a dashboard note. Each report includes YAML frontmatter, video metadata, summary, timestamp links, local report path, and an optional full transcript.

### Local development

```bash
python -m pip install -e .
python -m unittest discover -s tests
```

Caption-first smoke test:

```bash
ytlt process "https://www.ted.com/talks/sir_ken_robinson_do_schools_kill_creativity" --language en --no-transcribe-fallback
```

### Notes

- Python 3.9+ is required. Python 3.10+ is recommended.
- Captions are always preferred before local Whisper.
- The public branch recommends `ytlt configure`; `ytlt setup --execute` only configures the model and does not save language or output-environment preferences.
- Choosing no Whisper model is not recommended. Captioned videos still work, but captionless videos cannot fall back to local transcription.
- Hardware model selection lives in `codex-skill/references/model-selection.md`.
- Generated workspaces, downloaded media, models, virtual environments, and build metadata are ignored by `.gitignore`.
