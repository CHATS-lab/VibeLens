<p align="center">
  <img src="figures/logo.png" alt="VibeLens" width="120">
</p>

<h1 align="center">VibeLens</h1>

<p align="center">
  <strong>看清你的 AI 编程 Agent 到底在做什么。</strong><br>
  回放、分析、进化。
</p>

<p align="center">
  <a href="https://pypi.org/project/vibelens/"><img src="https://img.shields.io/pypi/v/vibelens?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/vibelens/"><img src="https://img.shields.io/pypi/pyversions/vibelens?style=for-the-badge&logo=python&logoColor=white&label=" alt="Python"></a>
  <a href="https://www.npmjs.com/package/@chats-lab/vibelens"><img src="https://img.shields.io/npm/v/@chats-lab/vibelens?style=for-the-badge&logo=npm&logoColor=white&label=npm" alt="npm"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="License"></a>
  <a href="https://vibelens.chats-lab.org/"><img src="https://img.shields.io/badge/Demo-live-brightgreen?style=for-the-badge&logo=google-chrome&logoColor=white" alt="Demo"></a>
</p>

<p align="center">
  <a href="https://vibelens.chats-lab.org/">在线体验</a> &middot;
  <a href="#快速开始">快速开始</a> &middot;
  <a href="#支持的-agent">支持的 Agent</a> &middot;
  <a href="#截图">截图</a> &middot;
  <a href="#数据捐赠">数据捐赠</a> &middot;
  <a href="docs/HUMAN_STUDY.md">用户研究</a> &middot;
  <a href="https://pypi.org/project/vibelens/">PyPI</a> &middot;
  <a href="https://www.npmjs.com/package/@chats-lab/vibelens">npm</a> &middot;
  <a href="CHANGELOG.md">更新日志</a>
</p>

<p align="center">
  <a href="README.md">English</a> &middot;
  <a href="README.zh-CN.md">中文</a>
</p>

---

<p align="center">
  <img src="figures/comic-blurb.jpg" alt="VibeLens 漫画：理解你的 Agent，调教它，驾驭它。">
</p>

<p align="center"><em>让 Agent 更懂你！</em></p>

---

**VibeLens** 是一个开源工具，帮你可视化和分析 AI 编程 Agent 的会话。它直接读取你已有的会话日志，开箱支持 **11 个本地 Agent**（Claude Code、Codex、Gemini、Cursor，[查看完整列表](#支持的-agent)）。**分析每次会话**，把**效率提示**整理成可直接粘贴进 CLAUDE.md 的内容，把重复出现的工作流**沉淀成可加载的技能**。

> **只想先看看**？[在线 Demo](https://vibelens.chats-lab.org/)，无需任何安装。

## 快速开始

**前置要求**：[uv](https://docs.astral.sh/uv/)（推荐）或 Python 3.10+，二选一。

```bash
# macOS / Linux，粘贴到 Terminal 即可
curl -LsSf https://raw.githubusercontent.com/CHATS-lab/VibeLens/main/install.sh | sh
```
```powershell
# Windows，粘贴到 PowerShell 即可
irm https://raw.githubusercontent.com/CHATS-lab/VibeLens/main/install.ps1 | iex
```

已有 Python 3.10+：

```bash
pip install vibelens && vibelens serve
```

已有 `uv`（安装）

```bash
uv tool install vibelens && vibelens serve
```

已有 `uv`（不安装）

```bash
uvx vibelens serve
```

npm 命令安装（仍然需要 Python）：

```bash
npx @chats-lab/vibelens serve
```

后续直接使用 `vibelens serve` 启动。

浏览器输入 **http://localhost:12001**，正常情况下 VibeLens 会自行启动浏览器。

使用 `--port` 参数换端口（例如 `vibelens serve --port 8080`）。`Ctrl+C` 退出。

完整安装指南和故障排查：[docs/INSTALL.md](docs/INSTALL.md)。

<details>
<summary><b>还没装 uv 或 Python？</b></summary>

**安装 uv**（推荐，单文件二进制，不需要先装 Python）：

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# 或: brew install uv
```
```powershell
# Windows
irm https://astral.sh/uv/install.ps1 | iex
# 或: winget install --id=astral-sh.uv -e
```

**安装或升级 Python 3.10+**（备选）：

```bash
# macOS
brew install python@3.12

# Debian / Ubuntu
sudo apt update && sudo apt install -y python3 python3-pip

# Fedora / RHEL
sudo dnf install -y python3 python3-pip

# Arch
sudo pacman -S python python-pip
```
```powershell
# Windows
winget install --id Python.Python.3.12 -e
# 或: choco install python
```

官方下载：[python.org](https://www.python.org/downloads/) · [uv 文档](https://docs.astral.sh/uv/getting-started/installation/)

</details>

<details>
<summary><b>用 uv 装完后提示 <code>vibelens: command not found</code>？</b></summary>

这是因为 uv 工具的 bin 目录还不在你的 shell `PATH` 里。安装脚本会尝试自动补上，但只在**新开的终端窗口**里生效。

解决办法：

1. **新开一个终端**，再跑一次 `vibelens serve`。
2. **手动跑一次 PATH 修复**，然后重开终端：
   ```bash
   uv tool update-shell
   ```
3. **手动加到 PATH**（把路径换成 `uv tool dir --bin` 的输出）：
   ```bash
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc   # 或 ~/.bashrc
   source ~/.zshrc
   ```
4. **跳过 shim**，每次都用：
   ```bash
   uvx vibelens serve
   ```

</details>

## 支持的 Agent

| Agent | 数据格式 | 数据位置 |
|-------|--------|---------------|
| **Claude Code** | JSONL | `~/.claude/projects/` |
| **Codex** | JSONL + SQLite | `~/.codex/sessions/` |
| **Gemini CLI** | JSON | `~/.gemini/tmp/` |
| **Cursor** | SQLite | `~/.cursor/chats/` |
| **Copilot CLI** | JSONL | `~/.copilot/session-state/` |
| **Kilo Code** | SQLite | `~/.local/share/kilo/` |
| **Kiro** | JSONL + JSON | `~/.kiro/sessions/` |
| **OpenCode** | SQLite | `~/.local/share/opencode/` |
| **OpenClaw** | JSONL | `~/.openclaw/agents/` |
| **Hermes** | JSONL + SQLite | `~/.hermes/sessions/` |
| **CodeBuddy** | JSONL | `~/.codebuddy/projects/` |
| **Claude.ai（网页版）** | 导出 JSON | 拖拽上传 |

VibeLens 会自动识别你的所有 Agent 目录。

## 截图

### 会话可视化 & 数据看板

<table>
  <tr>
    <td width="50%">
      <kbd><img src="figures/01-session-visualization.png" alt="会话可视化" width="100%" /></kbd>
      <p align="center"><b>会话可视化</b><br>逐步时间线，包含消息、工具调用、思考块和子 Agent 派生。</p>
    </td>
    <td width="50%">
      <kbd><img src="figures/02-dashboard.png" alt="数据看板" width="100%" /></kbd>
      <p align="center"><b>数据看板</b><br>用量热力图、按模型的成本拆分、按项目的细分。</p>
    </td>
  </tr>
</table>

### 效率提示 & 个性化

<table>
  <tr>
    <td width="50%">
      <kbd><img src="figures/03-productivity-tips.png" alt="效率提示" width="100%" /></kbd>
      <p align="center"><b>效率提示</b><br>识别卡顿模式，给出具体的改进建议。</p>
    </td>
    <td width="50%">
      <kbd><img src="figures/04-skill-recommendation.png" alt="技能推荐" width="100%" /></kbd>
      <p align="center"><b>技能推荐</b><br>把工作流模式匹配到目录中的现成技能。</p>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <kbd><img src="figures/05-skill-creation.png" alt="技能定制" width="100%" /></kbd>
      <p align="center"><b>技能定制</b><br>根据你的会话模式生成新的 SKILL.md。</p>
    </td>
    <td width="50%">
      <kbd><img src="figures/06-skill-evolution.png" alt="技能进化" width="100%" /></kbd>
      <p align="center"><b>技能进化</b><br>基于真实会话，对已安装的技能做有针对性的改进。</p>
    </td>
  </tr>
</table>


### 开发者环境

```bash
git clone https://github.com/CHATS-lab/VibeLens.git
cd VibeLens
uv sync --extra dev
uv run vibelens serve
```

### 卸载

按当初的安装方式来：

```bash
# 用 pip 装的
pip uninstall vibelens

# 用 uv 装的（一行式安装走的就是这条路径，或者你自己跑了 `uv tool install`）
uv tool uninstall vibelens

# 用 npm 全局装的
npm uninstall -g @chats-lab/vibelens
```

VibeLens 把日志和缓存放在 `~/.vibelens/` 和当前工作目录的 `logs/` 下。想彻底清空就删掉：

```bash
rm -rf ~/.vibelens
```

## 数据捐赠

VibeLens 支持把你的 Agent 会话数据捐赠出来，用于推动编程 Agent 行为方面的研究。捐赠数据由东北大学的 [CHATS-Lab](https://github.com/CHATS-lab)（Conversation, Human-AI Technology, and Safety Lab）收集。

捐赠流程：上传数据 → 选择想分享的会话 → 点击 **Donate Data** 按钮。

## 参与贡献

欢迎贡献！提交前请确保代码通过 `ruff check` 和 `pytest`。

## 协议

[MIT](LICENSE)
