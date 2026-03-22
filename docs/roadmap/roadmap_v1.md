# VibeLens Roadmap v1

## Vision

VibeLens aims to become the standard observability layer for AI coding agents. Beyond viewing conversations, it provides deep semantic analysis, cost intelligence, and multi-agent coordination insights — giving developers and teams the tools to understand, optimize, and govern their agent workflows across every major coding CLI.

## Progress Snapshot

| Metric | Count |
|--------|-------|
| Total items | 54 |
| Completed | 18 |
| Remaining | 36 |
| Sections | 10 |

### Population Ratings

Each pending item is rated by how many users would use it:

- **HIGH** — Most users want this; strong draw for new users
- **MED** — A significant portion of active users would use this
- **LOW** — Niche; power users or specialists only

| Rating | Count | Reasoning |
|--------|-------|-----------|
| HIGH | 10 | Universal demand or prerequisite for adoption (cost, packaging, sharing, privacy) |
| MED | 21 | Valuable to active users but not a first-day need (analytics, parsers, performance) |
| LOW | 5 | Specialists only (export formats, data retention, schema specs, prompt scoring) |

## Focus Areas

1. **Cost Tracking** — Surface the true cost of agent-assisted development with cost estimation, model ROI comparisons, and burn rate trends.
2. **Session Insights** — Personalized analytics inspired by Claude Code `/insights`: session highlights, friction detection, and outcome scoring.
3. **Multi-Agent Analytics** — Concurrent session dashboards, sub-agent hierarchies, and per-agent performance scorecards.
4. **Session Graphs** — Session relationship DAGs, continuation chains, and conversation flow diagrams.
5. **Agent Parsers** — Universal ingestion for every major coding agent CLI, with automatic format detection.
6. **Skill Coaching** — Help users become more effective with their agents through pattern libraries and best practices.
7. **Packaging** — Zero-config installation via `uvx vibelens serve` with local-first privacy defaults.
8. **Performance** — Sub-second response times through incremental parsing, SQLite FTS5, and virtual scrolling.

---

## 1. Cost Tracking

Everyone wants to know what their agent sessions actually cost. This section builds on the existing token metrics infrastructure to surface dollar amounts, model comparisons, and spend trends.

- [x] **Token breakdown** — Per-step metrics: prompt, completion, cached, and cache-creation tokens
- [x] **Period comparisons** — Date-range filtering for usage trends across day/week/month
- [x] **Cost estimation** — Model-aware cost calculator using token counts and per-model pricing tables
- [ ] **Burn rate projection** `HIGH` — Simple extrapolation of recent spend trends over configurable lookback windows (not ML-based)
- [ ] **Cost-per-task-type** `MED` — Break down spend by conversation phase (debugging vs. implementation vs. exploration)
- [ ] **Model specialization ROI** `MED` — Compare cost-effectiveness across models (Opus vs. Sonnet vs. Haiku) by task type

## 2. Session Insights

Inspired by Claude Code's `/insights` report — which surfaces wins, friction points, outcomes, and usage personality — this section brings the same kind of personalized analytics to VibeLens. Rather than dry metrics, these features tell users *what went well, what went wrong, and how effective their sessions were*.

- [x] **Phase detection** — Sliding-window classification of conversation phases (exploration, implementation, debugging, verification, planning)
- [x] **Tool dependency graph** — DAG of tool call relationships with typed edges (read-before-write, error-retry, search-then-read)
- [ ] **Session highlights** `HIGH` — Auto-identify impressive accomplishments and wins from sessions (what you achieved)
- [ ] **Friction detection** `HIGH` — Surface where sessions went wrong: errors, rejected actions, wrong approaches, wasted cycles
- [ ] **Outcome scoring** `MED` — Rate sessions by goal achievement level (fully / mostly / partially / not achieved)
- [ ] **Error pattern recognition** `MED` — Detect recurring failure modes across sessions and suggest mitigations
- [ ] **Rework detection** `MED` — Identify repeated edits to the same code regions and quantify wasted effort
- [ ] **Prompt effectiveness scoring** `LOW` — Rate user prompts by outcome quality, iteration count, and agent confusion signals

## 3. Multi-Agent Analytics

Modern coding agents frequently spawn sub-agents and run concurrent sessions. VibeLens already renders sub-agent hierarchies and correlates sessions by project — the next step is giving users a real-time dashboard of concurrent activity and per-agent performance profiles.

- [x] **Sub-agent hierarchy** — Recursive display of parent-child agent relationships with trajectory cross-references
- [x] **Cross-agent correlation** — Group trajectories by project path with overlapping time windows
- [ ] **Agent scorecards** `MED` — Per-agent performance profiles: speed, accuracy, token efficiency, tool preferences
- [ ] **Concurrent session dashboard** `MED` — Timeline view of overlapping sessions with Gantt-style visualization ([issue #2](https://github.com/JinghengYe/VibeLens/issues/2))

## 4. Session Graphs

Sessions form continuation chains, spawn sub-agents, and overlap in time. These features visualize session-level relationships built from `TrajectoryRef` cross-references.

- [x] **Activity heatmap** — 52-week GitHub-style contribution heatmap with daily session counts
- [x] **Usage-over-time chart** — Line chart for sessions, messages, and tokens across configurable time periods
- [x] **Conversation flow diagrams** — Phase-grouped visual flow of user-agent-tool interactions
- [ ] **Session relationship DAG** `MED` — Interactive graph built from `last_trajectory_ref` and `parent_trajectory_ref` cross-references ([issue #2](https://github.com/JinghengYe/VibeLens/issues/2))
- [ ] **Session continuation chains** `MED` — Visual linking of `last_trajectory_ref` continuation sequences

## 5. Agent Parsers

VibeLens already supports four agent formats (Claude Code, Codex, Gemini, Dataclaw) with automatic format detection. The next parsers — Cowork and OpenClaw — are low-effort additions that reuse existing infrastructure, while longer-term items like MCP integration and ATIF v2.0 require more architectural work.

- [x] **Claude Code parser** — Full JSONL parsing with sub-agent discovery and multi-model support
- [x] **Codex CLI parser** — OpenAI Responses API rollout format
- [x] **Gemini CLI parser** — Session JSON with project path resolution
- [x] **Dataclaw parser** — HuggingFace JSONL export ingestion
- [x] **Auto-detection** — Confidence-scored format fingerprinting across all supported formats
- [ ] **Cowork parser** `HIGH` — Reuse Claude Code parser with different discovery paths for `~/Library/Application Support/Claude/claude-code-sessions/`
- [ ] **MCP server integration** `HIGH` — Expose VibeLens analytics as MCP tools for agent self-reflection
- [ ] **OpenClaw parser** `MED` — JSONL at `~/.openclaw/agents/<agentId>/sessions/<SessionId>.jsonl`, similar pattern to Claude Code parser
- [ ] **OpenCode parser** `MED` — Support for OpenCode CLI session format
- [ ] **ATIF v2.0 spec** `LOW` — Next-generation trajectory interchange format with schema evolution support

## 6. Skill Coaching

Beyond analytics, VibeLens can help users become *better* at working with coding agents. By analyzing conversation histories, the platform can surface reusable patterns and best practices — similar to how Claude Code `/insights` suggests CLAUDE.md additions based on observed friction.

- [ ] **Productivity pattern library** `MED` — Curated tips from conversation analysis (prompt patterns, tool usage strategies, CLAUDE.md suggestions)
- [ ] **Guided onboarding** `MED` — Interactive walkthrough for new agent users
- [ ] **Best practices dashboard** `MED` — Aggregate patterns from high-quality sessions

## 7. Packaging

VibeLens currently requires manual setup with YAML configuration. [Issue #3](https://github.com/JinghengYe/VibeLens/issues/3) calls for `uvx vibelens serve` as a zero-config entry point — install from PyPI and it just works, reading from `~/.claude/` with localhost-only defaults.

- [ ] **PyPI packaging** `HIGH` — Distribute via `uvx vibelens serve` and `pip install vibelens` ([issue #3](https://github.com/JinghengYe/VibeLens/issues/3))
- [ ] **Zero-config launch** `HIGH` — Auto-detect `~/.claude/` without requiring YAML config file
- [ ] **Frontend asset bundling** `HIGH` — Include pre-built frontend assets in the Python package
- [ ] **Local-first privacy** `HIGH` — Bind to localhost by default with no external data transmission

## 8. Privacy & Security

Agent sessions contain sensitive data — file paths, code snippets, API keys, and sometimes credentials. VibeLens must provide tools to audit, protect, and manage this data responsibly.

- [x] **Upload isolation** — Session-token scoped upload pipeline for multi-tab browser safety
- [ ] **Sensitive data auditor** `MED` — Scan trajectories for leaked secrets, API keys, and PII
- [ ] **Data retention policies** `LOW` — Configurable auto-cleanup rules for old sessions and uploads

## 9. Performance

As users accumulate thousands of sessions, VibeLens must remain responsive. The current in-memory caching provides a solid baseline; the remaining items focus on reducing startup time, enabling persistent search, and keeping the UI smooth at scale.

- [x] **In-memory caching** — TTL-based caching for dashboard aggregations and search indices
- [ ] **Incremental parsing** `HIGH` — Parse only new/changed session files on subsequent loads
- [ ] **SQLite FTS5 search** `MED` — Replace in-memory search index with persistent full-text search
- [ ] **Virtual scrolling** `MED` — Efficiently render session lists with thousands of entries
- [ ] **File system watching** `MED` — Live-reload sessions as new JSONL entries are written
- [ ] **Lazy step loading** `MED` — Load conversation steps on-demand for large sessions

## 10. Sharing & Integration

VibeLens operates as a standalone tool today. These integrations connect it to the broader community — sharing sessions publicly, linking to commits, and exporting data for research.

- [x] **Shareable session links** — Generate a public permalink so users can share conversation details with others
- [ ] **GitHub integration** `MED` — Link sessions to commits, PRs, and issues for full development context
- [ ] **Slack / Discord bot** `MED` — Share session summaries and analytics in team channels
- [ ] **Multi-format export** `LOW` — Export to CSV, Parquet, and OpenTelemetry trace format
- [ ] **HuggingFace export** `LOW` — Publish anonymized trajectory datasets for research
