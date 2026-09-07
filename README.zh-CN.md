<p align="center">
  <img src="img/kwipu_tagline_en.svg" width="384" alt="Kwipu — Ask your notes">
</p>

# Kwipu

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-orange.svg)](https://ollama.com/)
[![LlamaIndex](https://img.shields.io/badge/framework-LlamaIndex-purple.svg)](https://www.llamaindex.ai/)
[![Obsidian Compatible](https://img.shields.io/badge/Obsidian-compatible-7C3AED.svg)](https://obsidian.md/)
[![MCP Server](https://img.shields.io/badge/MCP-compatible-blue.svg)](https://modelcontextprotocol.io/)

[English](README.md) | **简体中文** | [Tiếng Việt](README.vi.md)

Kwipu 可将文档文件夹转换为属性图 RAG 索引，你可以通过交互式终端、3D Web 界面或 MCP 客户端探索和查询该索引。它既适用于普通知识文件夹，也适用于 Obsidian 风格的 vault。

> **关于“完全本地运行”：** 选择本地 Ollama LLM 和嵌入模型时，Kwipu 可以完全在本地运行。有意设置的默认 LLM 是 `gpt-oss:20b-cloud`，它可能会将文档分块、检索到的上下文和问题发送给其提供方。[建立索引前，请选择云端或本地模式](#选择云端或本地模式)。

## 选择使用路径

| 我想要…… | 从这里开始 |
|---|---|
| 直接在终端中询问笔记 | [仅使用终端](#仅使用终端) |
| 在浏览器中探索图并提问 | [快速开始：Web-UI](#快速开始web-ui) |
| 使用自己的笔记或 Obsidian vault | [使用自己的文档文件夹](#使用自己的文档文件夹) |
| 通过 MCP 连接 AI 客户端 | [MCP-服务器](#mcp-服务器) |
| 配置或部署系统 | [配置参考](#配置参考) |
| 运行测试或贡献代码 | [开发者设置](#开发者设置) |

## Kwipu 的功能

- 从 `.md`、`.txt`、`.pdf` 和 `.docx` 文档构建属性图。
- 使用 LLM 提取语义关系，并从 wikilink 和 YAML frontmatter 中提取结构关系。
- 结合向量相似度、BM25、时间元数据和可选的同义词检索。
- 基于源文档分块生成回答并返回引用。
- 在交互式 3D 图中可视化实体、文档和关系。
- 监视源文件夹并安全地更新持久化存储。
- 支持英语、意大利语、法语、德语、西班牙语和葡萄牙语模式。
- 通过终端、Web API 和 MCP 提供同一套知识。

## Web 界面

### 1. 提出有来源依据的问题并打开其来源

![带有图和来源预览的 Kwipu 回答](img/second%20brain.jpeg)

### 2. 重建各次会议和评审之间的变更

![Kwipu 重建项目时间线](img/second%20brain_2.jpeg)

### 3. 比较人员、角色和支持文档

![Kwipu 比较项目角色及其引用](img/second%20brain_3.jpeg)

<details>
<summary>终端和 Obsidian 示例</summary>

![Kwipu 终端基于 Obsidian 项目笔记进行回答](img/screen.png)

![更新 Obsidian 会议笔记后 Kwipu 重新构建](img/screen_2.png)

</details>

## 选择云端或本地模式

Kwipu 连接兼容 Ollama 的端点，默认地址为 `http://localhost:11434`。端点位于本地本身并不能保证模型在本地执行。

| 模式 | LLM | 数据行为 | 首次使用前 |
|---|---|---|---|
| 默认云端模式 | `gpt-oss:20b-cloud` | Ollama 可能会将上下文和问题转发给模型提供方。请查看该提供方的隐私、留存和数据存放位置政策。 | `ollama pull gpt-oss:20b-cloud` |
| 本地示例 | `qwen2.5:7b` | 当两个模型和 Ollama 端点均位于本地时，推理会保留在本机。 | `ollama pull qwen2.5:7b` |

在默认配置中，两种模式均使用本地嵌入模型：

```powershell
ollama pull nomic-embed-text
```

远程 Ollama 端点会将数据发送到该主机。对于非 loopback 端点，Kwipu 要求使用 HTTPS；仅在受信任网络上明确允许不安全 HTTP 时例外。

## 快速开始：Web UI

以下引导式设置面向 Windows PowerShell。[Linux 和 macOS 的等效命令](#linux-和-macos-的等效命令)见后文。如果只需要终端界面，请完成第 1–6 步，并在启动 bridge 和 frontend 之前停止。

### 1. 安装并验证前置条件

请安装：

- [Git](https://git-scm.com/downloads)，或以 ZIP 格式下载仓库。
- [Python 3.12 或更高版本](https://www.python.org/downloads/)。
- [Ollama](https://ollama.com/download)。
- 仅当需要 Web 界面时，安装带有 npm 的 [Node.js](https://nodejs.org/)。

打开 PowerShell，并验证所需命令：

```powershell
git --version
py -3.12 --version
ollama --version
node --version
npm --version
```

如果找不到某个命令，请安装对应的前置条件，打开新的 PowerShell 窗口，然后重新运行检查。仅使用终端的用户不需要 Node.js 或 npm。

### 2. 下载 Kwipu 并安装其运行时

```powershell
git clone https://github.com/benmaster82/Kwipu.git
Set-Location .\Kwipu

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip==25.1.1
python -m pip install -r .\bridge\requirements.txt

# Web interface only:
npm --prefix .\frontend ci
```

`bridge/requirements.txt` 包含核心终端依赖，因此安装一套 Python 环境即可支持两种界面。如果下载的是 ZIP，请将其解压，并从解压后的 `Kwipu` 文件夹中运行 `git clone` 之后的命令。

如果 PowerShell 阻止激活虚拟环境，请为当前进程应用以下策略，然后重试：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 3. 添加文档

仓库已在 `knowledge_base/examples` 中包含一小套演示文档。要使用自己的文件，请在启动索引器之前，将 `.md`、`.txt`、`.pdf` 或 `.docx` 文件复制到 `knowledge_base` 中。

```text
Kwipu/
└── knowledge_base/
    ├── examples/
    └── your-notes/
        ├── project.md
        └── meeting-notes.pdf
```

Kwipu 会读取源文档，但不会重写它们。

### 4. 准备模型

确保 Ollama 正在运行。Ollama 桌面应用程序可能已经在运行服务；否则，请在**终端 1**中保持以下命令运行：

```powershell
ollama serve
```

在另一个 PowerShell 窗口中，拉取嵌入模型和且仅一个 LLM：

```powershell
ollama pull nomic-embed-text

# Cloud default:
ollama pull gpt-oss:20b-cloud

# OR local-only example:
# ollama pull qwen2.5:7b
```

云端模型可能会要求你完成 Ollama 账户或登录步骤。在选择预期的执行模式之前，请勿为敏感文档建立索引。

### 5. 使用一套一致的配置

每个进程都在启动时读取设置。PowerShell `$env:` 值仅适用于当前窗口，因此请将以下代码块粘贴到**索引器终端**和 **bridge 终端**中。

```powershell
Set-Location "C:\path\to\Kwipu" # replace with your actual folder
.\.venv\Scripts\Activate.ps1

$env:KWIPU_ROOT_DIR = (Get-Location).Path
$env:KWIPU_KNOWLEDGE_DIR = "knowledge_base"
$env:KWIPU_STORAGE_DIR = "storage_graph"
$env:KWIPU_EMBED_MODEL = "nomic-embed-text"
$env:KWIPU_OLLAMA_BASE_URL = "http://localhost:11434"
$env:KWIPU_QUERY_MAX_LENGTH = "4000"

# Run exactly one of these two lines:
$env:KWIPU_LLM_MODEL = "gpt-oss:20b-cloud" # cloud default
# $env:KWIPU_LLM_MODEL = "qwen2.5:7b"       # local example
```

如果选择本地模型，请在**两个**终端中注释掉云端配置行，并取消注释本地配置行。

> 对于共享终端/Web 设置，请优先使用环境变量，而不是 `geode_graph.py --llm-model`。CLI 标志只配置对应的终端进程；它们不会配置 bridge。

### 6. 启动索引器和终端界面——终端 2

应用配置代码块后，运行：

```powershell
python .\geode_graph.py --fast
```

保持此进程运行。首次使用时，请等待以下消息：

```text
Graph built and saved successfully.
```

复用现有存储时，对应的消息为：

```text
Graph loaded successfully.
```

随后，进程会显示：

```text
Type your question, or 'exit' to quit.
>
```

此时已经可以完全通过该终端使用 Kwipu：在 `>` 后输入问题并按 **Enter**，阅读基于来源生成的回答；完成后输入 `exit`。例如：

```text
> Who works on Project Alpha, and what are their roles?
```

如果只需要终端界面，设置至此完成：不需要 bridge、Node.js 或 frontend。如果希望 Kwipu 监视文档文件夹的变更，请保持该终端打开。

如果索引器输出 `No files found. Waiting for documents...`，请确认文件位于配置的 `KWIPU_KNOWLEDGE_DIR` 下。

### 7. 启动 API bridge——终端 3

要使用浏览器 UI，请打开另一个 PowerShell 窗口，粘贴第 5 步中的同一配置代码块，然后运行：

```powershell
$env:BRIDGE_HOST = "127.0.0.1"
$env:BRIDGE_PORT = "8765"
python -m bridge
```

保持 bridge 运行。成功启动时会包含以下消息：

```text
Uvicorn running on http://127.0.0.1:8765
```

### 8. 检查 health 并启动 frontend——终端 4

从仓库根目录运行：

```powershell
$health = Invoke-RestMethod -Uri "http://127.0.0.1:8765/health"
$health | ConvertTo-Json -Depth 6
```

继续之前，请检查顶层 `status`、`property_graph.status` 和 `ollama.status` 是否均为 `ok`。然后启动 UI：

```powershell
npm --prefix .\frontend run dev
```

在浏览器中打开 **http://localhost:5173**。使用随附的演示文档尝试以下问题：

> **Who works on Project Alpha, and what are their roles?**

在每个终端中使用 **Ctrl+C** 停止相应进程。正常的 Web 会话会保持四个进程运行：Ollama（除非其桌面服务已在运行）、Kwipu 索引器/终端、bridge 和 Vite。

## 仅使用终端

终端是完整的 Kwipu 界面，而不只是后台索引器。它会构建或加载图、监视文档、接收问题并直接输出回答。它需要 Python 和 Ollama，但**不需要** FastAPI、Node.js 或浏览器。

完成上述通用模型和配置步骤后，运行：

```powershell
.\.venv\Scripts\Activate.ps1
python .\geode_graph.py --fast
```

然后在提示符处提问：

```text
> What decisions were made in the January 15 meeting?
> How did Project Alpha change between the two meetings?
> Who is responsible for the API deployment?
```

命令和行为：

- 输入问题并按 **Enter** 查询图。
- 输入 `exit`、`quit` 或 `esci` 关闭 Kwipu。
- 按 **Ctrl+C** 停止运行。
- 保持进程运行，以检测新建、修改或删除的文档。
- 省略 `--fast`，为终端查询启用额外的 LLM 同义词检索器。

若仅安装终端界面，使用 `python -m pip install -r .\requirements.txt` 即可。Web 快速开始中使用的范围更广的 bridge 依赖也包含这些核心依赖。

## Linux 和 macOS 的等效命令

进程顺序相同：Ollama → 索引器/终端 → bridge → frontend。请将 Windows 设置和环境变量语法替换为：

```bash
git clone https://github.com/benmaster82/Kwipu.git
cd Kwipu

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip==25.1.1
python -m pip install -r bridge/requirements.txt
npm --prefix frontend ci # web interface only

export KWIPU_ROOT_DIR="$PWD"
export KWIPU_KNOWLEDGE_DIR="knowledge_base"
export KWIPU_STORAGE_DIR="storage_graph"
export KWIPU_EMBED_MODEL="nomic-embed-text"
export KWIPU_OLLAMA_BASE_URL="http://localhost:11434"
export KWIPU_QUERY_MAX_LENGTH="4000"
export KWIPU_LLM_MODEL="gpt-oss:20b-cloud" # or qwen2.5:7b
```

在索引器和 bridge shell 中重复 `export` 代码块，然后仅启动所需进程：

```bash
# Complete terminal interface and watcher
python geode_graph.py --fast

# Web API, in another shell
python -m bridge

# Web frontend, in another shell
npm --prefix frontend run dev
```

按照适用于你操作系统的说明安装并启动 Ollama。在 macOS 上，Ollama 应用程序可以提供服务，而无需单独运行 `ollama serve` 终端。

## 使用自己的文档文件夹

你可以将笔记保存在仓库外部。请使用绝对源路径和单独的生成存储路径，并为终端/索引器、bridge 和 MCP server 重复使用相同的值：

```powershell
$env:KWIPU_ROOT_DIR = "D:\KwipuData"
$env:KWIPU_KNOWLEDGE_DIR = "D:\Notes\MyVault"
$env:KWIPU_STORAGE_DIR = "graph-index"
$env:KWIPU_LLM_MODEL = "qwen2.5:7b"
$env:KWIPU_EMBED_MODEL = "nomic-embed-text"
python .\geode_graph.py --fast
```

相对的知识库和存储路径会基于 `KWIPU_ROOT_DIR` 解析。源目录和生成的存储必须分开；Kwipu 会拒绝嵌套或重叠的布局，以保护源文档。

### 文档更新

| 文件系统变更 | 索引操作 |
|---|---|
| 首次启动且没有存储 | 完整构建 |
| 只有新建文件 | 增量插入 |
| 存在任何修改的文件 | 对该批次执行一次完整重建 |
| 存在任何删除的文件 | 对该批次执行一次完整重建 |
| 事件未伴随内容哈希变化 | 忽略 |

编辑器的原子保存可能表现为先删除后新建，因此会触发完整重建。每个存储目录只运行**一个**核心 CLI watcher。

## 核心 CLI 参考

Fast 模式会禁用每次查询时的 LLM 同义词检索器：

```powershell
python .\geode_graph.py --fast
```

独立使用时，可以通过仅限 CLI 的参数覆盖模型：

```powershell
python .\geode_graph.py --llm-model qwen2.5:7b --embed-model nomic-embed-text
```

这些标志不会传播到 bridge 或 MCP server。多个组件共享同一存储时，请使用环境变量。

## 工作原理

```text
Documents (.md/.txt/.pdf/.docx)
        │
        ▼
Structural preprocessing (wikilinks/frontmatter) + LLM path extraction
        │
        ▼
Persisted property graph and vectors (shared storage + revision manifest)
        │
        ▼
Synonym* + vector + BM25 + temporal retrieval
        │
        ▼
LLM answer with source context and citations

* Synonym retrieval is disabled in --fast mode, MCP, and bridge queries.
```

### 组件

- **核心 CLI** 构建并查询图，然后监视知识目录。
- **MCP server** 通过 MCP stdio 提供 `query_graph` 和 `query_graph_detailed`。
- **Bridge** 提供用于 health、图快照、只读查询和来源展开的版本化 JSON API。
- **Frontend** 使用 `3d-force-graph` 渲染图，并通过可配置的 API base 调用 bridge。

### 存储和进程模型

CLI 是指定的写入方。bridge 为只读组件，在 CLI 发布可用存储之前会返回 HTTP `503`。MCP 可在存储不存在时构建存储，但不会启动 watcher。

所有组件都使用共享的跨进程锁和 revision manifest。查询会比较 `storage_revision`，并自动重新加载新提交的完整代际。持久化操作会在同级 staging 代际中进行准备，暂时将上一代保留为 backup，然后以原子方式发布新代际。

不要针对一个存储目录运行多个 watcher。进程正在使用 `storage_graph`、`.storage_graph.staging`、`.storage_graph.backup` 或同级锁时，请勿删除它们。

## 配置参考

每个进程启动时都会从环境变量读取设置。更改值后，请重启受影响的进程。

### 核心配置

| 变量 | 默认值 | 含义 |
|---|---|---|
| `KWIPU_ROOT_DIR` | 仓库目录 | 默认和相对数据路径的基础目录。 |
| `KWIPU_LIVE_DIR` | — | `KWIPU_ROOT_DIR` 的兼容别名；`KWIPU_ROOT_DIR` 优先。 |
| `KWIPU_KNOWLEDGE_DIR` | root 下的 `knowledge_base` | 源文档目录。 |
| `KWIPU_STORAGE_DIR` | root 下的 `storage_graph` | 生成的持久化索引目录。 |
| `KWIPU_LLM_MODEL` | `gpt-oss:20b-cloud` | 用于提取和回答的 LLM；默认模型可以在云端执行。 |
| `KWIPU_MODEL_NAME` | — | `KWIPU_LLM_MODEL` 的兼容别名；后者优先。 |
| `KWIPU_EMBED_MODEL` | `nomic-embed-text` | 用于存储向量的嵌入模型。 |
| `KWIPU_OLLAMA_BASE_URL` | `http://localhost:11434` | 绝对 HTTP(S) Ollama 端点。 |
| `KWIPU_OLLAMA_TIMEOUT` | `300` 秒 | 正数的模型请求超时。 |
| `KWIPU_STORAGE_LOCK_TIMEOUT` | `30` 秒 | 等待共享存储锁的正数时限。 |
| `KWIPU_QUERY_MAX_LENGTH` | `4000` 个字符 | 规范化后问题的最大长度。 |
| `KWIPU_MAX_SOURCE_BYTES` | `10485760` 字节 | bridge 展开允许的最大源文件和提取文本大小。 |
| `KWIPU_ALLOW_INSECURE_REMOTE_OLLAMA` | disabled | 设为 `1`、`true`、`yes` 或 `on` 时，允许对非 loopback 主机使用明文 HTTP。 |

更改嵌入模型需要创建新的存储索引。仅更改 LLM 时可以加载现有向量，但之后的完整重建可能会提取出不同的关系。

### Bridge 配置

| 变量 | 默认值 | 含义 |
|---|---|---|
| `BRIDGE_HOST` | `127.0.0.1` | `python -m bridge` 使用的绑定地址。 |
| `BRIDGE_PORT` | `8765` | 经过验证的端口，范围为 1 到 65535。 |
| `BRIDGE_CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | 逗号分隔的浏览器 origin；拒绝通配符。 |
| `BRIDGE_ALLOWED_HOSTS` | `localhost,127.0.0.1,testserver` | 接受的 `Host` 值；拒绝通配符。 |
| `BRIDGE_HEALTH_OLLAMA_TIMEOUT` | `2` 秒 | `/health` 使用的 Ollama 超时。 |

bridge 还会使用上述所有核心设置。`python -m bridge` 会使用 `BRIDGE_HOST` 和 `BRIDGE_PORT`；直接调用 Uvicorn 时，请将它们作为 CLI 值传入：

```powershell
uvicorn bridge.app:app --reload --host $env:BRIDGE_HOST --port $env:BRIDGE_PORT
```

有关 API 契约和部署说明，请参阅 [bridge/README.md](bridge/README.md)。

### Frontend 配置

| 变量 | 默认值 | 含义 |
|---|---|---|
| `VITE_API_BASE` | `/api` | 浏览器 API base；相对值使用 Vite proxy。 |
| `VITE_BRIDGE_TARGET` | `http://127.0.0.1:8765` | 开发 proxy 目标。 |

使用默认配置时，Vite 会将 `/api/health` 重写到 bridge 上的 `/health`。生产环境静态部署必须提供等效的 reverse proxy，或使用绝对 `VITE_API_BASE`；浏览器直接访问时还必须匹配 `BRIDGE_CORS_ORIGINS`。

## MCP 服务器

请在 MCP 客户端配置中使用 Python 解释器和脚本的绝对路径。由于 CLI 标志只适用于 `geode_graph.py`，请使用环境变量配置模型和路径。

```json
{
  "mcpServers": {
    "kwipu": {
      "command": "C:/path/to/Kwipu/.venv/Scripts/python.exe",
      "args": ["C:/path/to/Kwipu/kwipu_mcp_server.py"],
      "env": {
        "KWIPU_KNOWLEDGE_DIR": "C:/path/to/vault",
        "KWIPU_LLM_MODEL": "qwen2.5:7b",
        "KWIPU_EMBED_MODEL": "nomic-embed-text"
      }
    }
  }
}
```

MCP server 在 fast 检索模式下运行，且不会启动 watcher。它提供：

- `query_graph(question)`——以文本形式返回回答。
- `query_graph_detailed(question)`——返回带有引用的 `{"answer": "...", "citations": [...]}`，引用按 node ID 去重。

选择 `gpt-oss:20b-cloud` 时，需考虑前述云端隐私影响。需要仅在本地执行时，请使用已安装的本地模型。

## Bridge API 和来源展开

bridge 的主要端点为：

| 端点 | 用途 |
|---|---|
| `GET /health` | 检查存储、已配置模型和 Ollama 连接。 |
| `GET /graph/snapshot` | 返回 3D 界面使用的图。 |
| `POST /query` | 提出问题并接收回答和引用。 |
| `GET /expand?node_id=<opaque-id>` | 读取图节点所表示的引用来源。 |

来源展开会直接读取 UTF-8 Markdown/文本，并在不调用 LLM 的情况下提取 PDF/DOCX 文本。输入过大返回 `413`；不支持的格式返回 `415`；无效 UTF-8 或结构化提取失败返回 `422`；临时来源 I/O 错误返回 `503`。

## 故障排除

| 症状 | 检查内容 |
|---|---|
| 无法识别 `python`、`ollama`、`node` 或 `npm` | 安装缺少的前置条件，打开新终端，然后运行其 `--version` 命令。 |
| `Activate.ps1` 被阻止 | 运行 `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`，然后重新激活环境。 |
| `Ollama is not running` | 启动 Ollama 应用程序或运行 `ollama serve`；验证 `http://localhost:11434/api/tags`。 |
| `Missing model(s)` | 运行 Kwipu 输出的确切 `ollama pull <model>` 命令。确保索引器和 bridge 使用相同的模型名称。 |
| `No files found. Waiting for documents...` | 将支持的文件放入 `KWIPU_KNOWLEDGE_DIR`，并确认 CLI 标题中输出的路径。 |
| 浏览器未打开 | 保持 Vite 运行，并手动打开 `http://localhost:5173`。 |
| Health 为 `degraded` | 检查 `property_graph.detail`、`ollama.detail` 和 `/health` 中的 `models` 列表。 |
| 查询返回 `503` | 先启动 CLI/索引器，并等待图成功构建/加载。此外还要检查存储路径、锁和嵌入兼容性。 |
| 查询返回 `502` | 检查 bridge 日志和 Ollama 可用性；查询引擎或模型请求失败。重试不应用来掩盖持续性错误。 |
| 查询返回 `400 Question is too long` | 后端会报告当前限制。默认值为 `4000`；其他值（例如 `99`）表示 `KWIPU_QUERY_MAX_LENGTH` 已被覆盖。请在启动 bridge 前进行设置，并重启 bridge。 |
| 端口 `8765` 或 `5173` 已被占用 | 停止现有进程，或以一致方式更改 bridge/Vite 设置。 |
| 嵌入模型不匹配 | 停止所有 Kwipu 进程，恢复构建存储时使用的模型，或将生成的存储移到其他位置并让 CLI 重建。切勿删除源文档目录。 |

使用以下命令检查 PowerShell 覆盖值：

```powershell
Get-ChildItem Env:KWIPU_QUERY_MAX_LENGTH
```

为当前终端设置文档所述默认值，并重启 bridge：

```powershell
$env:KWIPU_QUERY_MAX_LENGTH = "4000"
python -m bridge
```

## 项目结构

```text
Kwipu/
├── geode_graph.py                # Core engine, interactive CLI, and watcher
├── kwipu_config.py               # Canonical environment configuration
├── kwipu_storage.py              # Inter-process lock and atomic JSON helpers
├── kwipu_mcp_server.py           # MCP stdio server
├── lang_config.py                # Multilingual patterns and date/relation helpers
├── requirements.txt              # Core/terminal and MCP dependencies
├── requirements-dev.txt          # Bridge/runtime/test dependency inputs
├── requirements-dev.lock         # Hashed Python 3.12 Linux CI lock
├── requirements-dev-windows.lock # Hashed Python 3.12 Windows CI lock
├── bridge/                       # FastAPI app and read-only query adapter
├── frontend/                     # TypeScript/Vite 3D client
├── knowledge_base/examples/      # Example source documents
├── img/                          # Logo and screenshots
├── tests/                        # Standard-library unittest suite
└── storage_graph/                # Generated active index, gitignored
```

生成的同级 staging 和 backup 目录也会被 gitignore，并由系统自动管理。

## 开发者设置

使用适用于平台的哈希锁文件，安装完整的 bridge/runtime/test 环境。

### Windows，Python 3.12

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip==25.1.1
python -m pip install --require-hashes -r .\requirements-dev-windows.lock
python -m unittest discover -s tests -p "test_*.py" -v
```

### Linux CI 环境，Python 3.12

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip==25.1.1
python -m pip install --require-hashes -r requirements-dev.lock
python -m unittest discover -s tests -p "test_*.py" -v
```

Frontend 验证命令为：

```powershell
npm --prefix .\frontend ci
npm --prefix .\frontend run typecheck
npm --prefix .\frontend run build
npm --prefix .\frontend audit
```

只能按照 [CONTRIBUTING.md](CONTRIBUTING.md) 中记录的固定工作流，从 `requirements-dev.txt` 重新生成依赖锁，然后审查完整 diff。有关所有贡献和验证要求，请参阅该指南。

## 许可证

MIT
