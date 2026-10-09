# 版本时间线

本文件记录平台的重要版本节点与验证证据。

> 说明：本仓库在 **2026-09-13** 补建 Git 版本控制。此前的 M0/M1 工作已经存在于文件系统中但没有提交历史，因此下面的 M0–M2 条目按当时的实际工作记录与文件时间整理，Git 提交历史从 `v0.1.0-m2` 这个导入提交开始；之后每个里程碑一个提交与标签。

## [0.1.0-m2] — 2026-09-13

M2：Artifact 与 Workflow Runtime。规格依据 §17 M2、§5、§6、§8、§10.1、§11。

### 新增

- **数据模型**：迁移 `0003_m2_workflow_runtime`，新增 `workflow_definitions`、`runs`、`run_nodes`、`events`、`artifacts`、`artifact_edges`、`llm_calls`、`context_items`、`llm_call_context`（共 9 张表，含状态约束、`events.sequence` 可续传序号、`(run_id, node_key, attempt)` 唯一约束）。
- **状态机**：`domain/states.py` 实现 Run / Node / Artifact 三套枚举与合法跃迁，非法跃迁返回 `ILLEGAL_STATE_TRANSITION`。
- **Artifact registry**：12 份 JSON Schema（`schemas/artifacts/`）+ 校验器；`content_hash` 只覆盖 type/schema_version/content，因此 recorded replay 可复现相同哈希；产物不原地覆盖，新版本经 `parent_id` 关联并让父版本进入 `superseded`；`artifact_edges` 记录 lineage；文件以临时文件 + 原子 rename 落盘。
- **Workflow runtime**：内置 `chapter_generation` DAG（16 节点，§8 流程）；DAG 校验（重复 key、未知依赖、环）；质量门阈值来自 preset；revision 按 §8 回到 Continuity + Critic 重新验证，最多 3 次，超限进入 `waiting_approval`；节点级 attempt、transient-only 重试、取消传播、未走到的分支置 `skipped`；Style Editor 事实保护（§7）失败即保留原稿。
- **Provider**：确定性 `FakeProvider`（temperature=0、固定 seed、12 类 artifact、6 类故障注入）与 `RecordedProvider`（离线重放）。无需真实大模型即可跑通完整工作流。
- **可观察性**：append-only `events`；§11 要求的 11 类事件全部可达；`llm_calls` 记录 prompt / 上下文引用 / 模型快照 / 采样参数 / usage / latency，写入前脱敏；`context_items` + `llm_call_context` 记录每次调用实际检索来源、rank 与 score。
- **SSE**：`GET /api/v1/runs/{run_id}/events/stream`，支持 `Last-Event-ID` 续传，终态自动结束。
- **REST API**：runs（创建/列表/查询/节点/取消/重试/事件/流）、artifacts（列表/查询/lineage/审批）、`/diagnostics`、`/debug/runs/{id}/{trace,events,llm-calls,context,artifacts,errors}`、`/workflows/{key}`；全部带唯一 `operation_id`。
- **并发与幂等**：写端点支持 `Idempotency-Key`；production 项目并发 mutating run 由 advisory lock 拒绝并返回 `RUN_ALREADY_ACTIVE`；terminal run 的 `:retry` 派生新 attempt 而不改写历史。
- **ARQ 业务 job**：`execute_run` 注册进 worker；队列不可用时 API 返回 `RUN_ENQUEUE_FAILED`。
- **CLI**：`run chapter|list|status|events|cancel|retry`（`--follow` 消费 SSE）、`artifact list|show|lineage|approve|reject`、`debug trace|errors|llm-calls|context`、`diagnostics`、`workflow`。
- **Git 提交**：成功后写 `chapters/NNNN/{brief.json,draft.md,final.md,summary.md}`，commit trailer 含 `Run-Id` 与 `Artifact-Ids`；canon patch 经批准后由 Canon Manager 唯一写入。

### 验证

- `make test-backend`：266 passed；`make test-backend-integration`：26 passed；`make test-cli`：31 passed；`make test-frontend`：2 passed。
- 实机（经 Caddy `http://127.0.0.1:18080`）：创建 sandbox 项目 → `POST /runs` 202 → 真实 ARQ worker 执行 → `succeeded`；11 个 artifact、199 条事件、11 次 LLM 调用，`/debug/.../trace` 无错误；`/diagnostics` 全组件 ok。
- SSE 经 Caddy 实测流式输出；章节文件与 Git trailer 实测存在。

## [0.1.0-m1] — 2026-09-12 → 2026-09-13

M1：领域模型、Project 与 Preset。

- Project CRUD（创建/列表/查询/改名/归档），创建时初始化 manifest、规范目录与独立 Git 仓库。
- Model Registry（endpoint/profile），密钥只存 `secret_ref`。
- Preset CRUD 与 YAML JSON Schema 校验，内置 `default` 与 `long_novel_high_quality`，版本不可变。
- 项目目录初始化、路径穿越防护、原子写。
- 写 API 幂等（`Idempotency-Key`）、统一错误结构与 `X-Request-ID`。
- API-only CLI（health / project / preset），退出码 0 / 2 / 3。
- 迁移 `0002_m1_domain_foundation`。

## [0.1.0-m0] — 2026-09-12（运行时于 2026-09-13 改造）

M0：仓库骨架与运行环境。

- FastAPI `/health`（PostgreSQL / Redis / worker heartbeat 三组件）、Next.js 占位首页、Caddy 统一入口。
- Alembic `0001_enable_pgvector`；ARQ worker 与 TTL heartbeat。
- Compose 编排（healthcheck、named volume、internal network、非 root）。
- smoke 脚本与最小单元测试。
- **2026-09-13 运行环境改造**：本机 DroidSpaces Debian 13 的 Docker 不可用（内核缺 `bridge`/`br_netfilter`，iptables 无 `filter` 表，dockerd 初始化 bridge 网络驱动失败），改为 native 源码运行：PGDG PostgreSQL 16.15 + pgvector 0.8.6、Redis 8.0.2（systemd 托管，需一行 `PrivateUsers=no` drop-in）、Caddy 2.6.2、Python 3.12.14；新增 `scripts/native_*.sh`、`Caddyfile.native`、`.env.native.example` 与 `docs/DEV_ENVIRONMENT.md`。Compose 路径保留。

## 下一步（未发布）

- M3：完整章节流水线的 Agent 契约与 Prompt 模板、Context Builder 增强、Canon 冲突与时间有效性校验、真实 OpenAI-compatible provider。
- M4：WebUI 页面（当前只有占位首页）与 CLI 完整路径。
- M5：鉴权 token 与 scope、sandbox 管理、`debug replay`、Playwright E2E。
- M6：安全加固、备份恢复、部署手册。
