# Implementation Status

最后更新：2026-09-13；运行环境已从 Docker Compose 改为 native 源码运行并完成实机验证；M2 已实现，M3 尚未开始

## 运行环境（2026-09-13 修订）

原计划以 Docker Compose 交付 M0。本机（DroidSpaces Debian 13 / aarch64）实测 Docker 不可用，因此改为 native 源码运行，Compose 保留为可选路径。详见 [`DEV_ENVIRONMENT.md`](DEV_ENVIRONMENT.md) 与规格 §0.1。

| 项 | 状态 | 证据 |
| --- | --- | --- |
| Docker 不可用 | 已确认（内核能力） | dockerd 因 bridge 网络驱动初始化失败退出：`failed to create FILTER chain DOCKER: iptables: No chain/target/match by that name`；内核 `6.6.127-android15` 缺 `bridge`/`br_netfilter`，iptables 无 `filter` 表。与 user namespace 无关 |
| PostgreSQL 16 + pgvector | 已实现（native） | PGDG `postgresql-16` 16.15 + `postgresql-16-pgvector` 0.8.6；`make native-migrate` 实机通过；`select extversion from pg_extension where extname='vector'` → 0.8.6 |
| Redis + ARQ heartbeat | 已实现（native） | Redis 8.0.2 由 systemd 托管（`make native-provision` 写入 `PrivateUsers=no` drop-in，其余 hardening 保留）；`/api/health` 中 `redis` 与 `worker` 组件均为 `ok` |
| Caddy 统一入口 | 已实现（native） | `Caddyfile.native`，`http://127.0.0.1:18080`；`/api/health` 与 `/` 均实机 200 |
| Next.js 首页 | 已实现 | standalone 构建 + `npm run start`，经 Caddy 返回首页 |
| 一键验证 | 已实现 | `make smoke`：health 三组件 + 首页标记 + 内置 Preset 全部通过 |
| 重启恢复 | 已验证 | `make native-restart` 后 `make smoke` 再次通过 |
| Compose 路径 | 保留但本机不可验收 | `compose.yaml`、`compose.test.yaml`、`Caddyfile`、`compose-*` 目标保留 |

native 路径引入并修复的环境问题：`Caddyfile.native` 站点地址必须显式 `http://`，否则明文请求被当作 HTTPS 站点拒绝；`npm run start` 等包装进程必须按进程组停止，否则残留子进程占用 3000 端口；`.env.native.example` 含空格的值必须加引号（该文件被 bash `source`）；Debian 的 `redis-server.service` 因 `PrivateUsers=yes` 在本机 systemd 下无法建立 user namespace（`status=217/USER`），由 `make native-provision` 写入一行 drop-in 后恢复 systemd 托管（**user namespace 本身可用**：`unshare -Ur`、`bwrap`、临时 `PrivateUsers` 单元均实测正常）。

## M0

| 范围 | 状态 | 说明 |
| --- | --- | --- |
| FastAPI `/health` | 已实现 | 直接路径和 Caddy `/api/health` 兼容路径均可用；native 实机返回 200，三个组件均为 `ok`。 |
| PostgreSQL 16 + pgvector | 已实现 | native：PGDG `postgresql-16` 16.15 + `postgresql-16-pgvector` 0.8.6；Compose 路径配置保持 `pgvector/pgvector:pg16`。 |
| Redis + ARQ worker heartbeat | 已实现 | worker 写入带 TTL 的 heartbeat key；native 下 Redis 由 systemd 托管（`make native-provision` 写入 `PrivateUsers=no` drop-in）。 |
| Next.js 占位首页 | 已实现 | 暴露稳定的 `data-testid` 和 `window.__APP_BUILD__`；standalone 构建经 Caddy 返回。 |
| Caddy 统一入口 | 已实现 | native `Caddyfile.native`（`127.0.0.1:18080`）；Compose 使用 `Caddyfile` 与官方 ARM64 release 二进制。 |
| Compose 运维约束 | 已配置（本机不可验收） | healthcheck、restart policy、named volumes、internal network、非 root 运行；保留为可选路径。 |
| Alembic migration | 已实现 | 0001 启用 pgvector；0002 M1 领域基础表；0003 M2 运行时表。三者在 native PG 16.15 上实际执行通过。 |
| 自动化文件 | 已实现 | `.env.example`、`.env.native.example`、`Caddyfile.native`、Makefile、README、native/Compose smoke。 |
| 最小单元测试 | 已实现 | backend pytest、frontend Vitest、CLI pytest。 |

## M1

| 范围 | 状态 | 说明 |
| --- | --- | --- |
| Project CRUD | 已实现 | 创建、列表、查询、改名、归档；创建时初始化 manifest、规范目录和独立 Git 仓库。 |
| Model Registry | 已实现 | Model endpoint/profile CRUD；endpoint test 只做 `/models` capability probe，敏感 key 通过 `secret_ref` 环境变量读取。 |
| Preset CRUD / YAML schema | 已实现 | 内置 `default` 与 `long_novel_high_quality`；版本不可变，支持新版本、读取和复制。 |
| Project preset apply | 已实现 | DB active preset version、`project.yaml` 和 Git commit 由同一 application service 协调。 |
| Idempotency / errors | 已实现 | 写请求支持 `Idempotency-Key`；统一错误 payload 和 `X-Request-ID`。 |
| CLI | 已实现 | API-only `novelctl`：health、project create/list、preset list/apply；JSON 输出和 0/2/3 退出码。 |
| M1 migrations | 已实现 | `0002_m1_domain_foundation.py` 与 SQLAlchemy metadata 对应。 |

## M2（Artifact 与 Workflow Runtime）

| 范围 | 状态 | 说明 |
| --- | --- | --- |
| M2 migrations | 已实现 | `0003_m2_workflow_runtime.py`：`workflow_definitions`、`runs`、`run_nodes`、`events`、`artifacts`、`artifact_edges`、`llm_calls`、`context_items`、`llm_call_context`；含状态 CheckConstraint、`events.sequence` Identity 与 `(run_id, node_key, attempt)` 唯一约束。 |
| Run/Node/Artifact 状态机 | 已实现 | `domain/states.py` 声明全部枚举与合法跃迁；非法跃迁抛 `ILLEGAL_STATE_TRANSITION`（409）；单测覆盖每条合法边与一组非法边。 |
| Artifact registry | 已实现 | 12 个 JSON Schema（`schemas/artifacts/`）+ `ArtifactSchemaRegistry` 校验；`content_hash` 只覆盖 type/schema_version/content（replay 可复现）；不原地覆盖，新版本经 `parent_id` 关联并把父版本置 `superseded`；`artifact_edges` 记录 `derived_from`/`input` lineage；文件按临时文件 + 原子 rename 写入项目 `artifacts/<type>/<id>.json`。 |
| Workflow DAG | 已实现 | 内置 `chapter_generation`（16 节点，含 Director→Retrieve→Plot→Idea/Character→Scene→Writer→Continuity+Critic→Quality Gate→Revision(≤3)→Style→Canon Extractor→审批→Canon Manager/Keep Draft）；定义校验（重复 key、未知依赖、环）；`branch_only`/`ends_workflow` 显式分支语义。 |
| Quality gate | 已实现 | 阈值来自 preset（`quality_gate.minimum`、`max_revision_iterations` 或 `revision.max_iterations`）；hard fail 优先；超限进入 `waiting_approval`；Revision 按 §8 回到 Continuity+Critic 重新验证。 |
| Runner 语义 | 已实现 | 节点级 attempt 行、pending→running→终态、transient-only 重试（超时/429/500/流中断/慢响应可重试；schema/permission/malformed 不重试）、取消传播到未执行节点、未走到的分支置 `skipped`、`waiting_approval` 只暂停不跳过。 |
| Provider | 已实现 | `FakeProvider`：确定性输出（temperature=0、固定 seed）、12 类 artifact 生成、6 类故障注入（timeout/429/500/malformed JSON/stream interruption/slow response）；`RecordedProvider`：按原始 `llm_calls` 顺序离线重放。 |
| Event Log / Tracing | 已实现 | append-only `events`（`sequence` 可续传）；§11 要求的 11 类事件全部可达（有覆盖测试），另有 `run.cancelled`、`node.failed`、`node.skipped` 等补充事件；`llm_calls` 保存 prompt/上下文引用/模型快照/采样参数/usage/latency/错误，写入前脱敏；`context_items` + `llm_call_context` 记录每次调用实际检索来源、rank 与 score。 |
| SSE | 已实现 | `GET /api/v1/runs/{run_id}/events/stream`，`text/event-stream`，`id:` = sequence，支持 `Last-Event-ID` 续传，终态后自动结束；已实机经 Caddy 验证流式输出。 |
| REST API | 已实现 | `POST /projects/{id}/runs`（202 + links）、`GET /projects/{id}/runs`、`GET /runs/{id}`、`GET /runs/{id}/nodes`、`:cancel`、`:retry`、`/events`、`/events/stream`、`GET /projects/{id}/artifacts`、`GET /artifacts/{id}`、`/lineage`、`:approve`、`:reject`、`GET /diagnostics`、`GET /debug/runs/{id}/{trace,events,llm-calls,context,artifacts,errors}`、`GET /workflows/{key}`；全部带 `operation_id`，无重复。 |
| 并发与幂等 | 已实现 | 所有写端点支持 `Idempotency-Key`（`actions` 表唯一约束 + 复用既有资源）；production 项目并发 mutating run 由 advisory lock + 活跃 run 查询拒绝，返回 `RUN_ALREADY_ACTIVE`（409）。 |
| ARQ 业务 job | 已实现 | `execute_run` 注册进 `WorkerSettings.functions`（保留 M0 infrastructure probe）；API 通过 ARQ pool 入队，队列不可用时返回 `RUN_ENQUEUE_FAILED`（503）。 |
| CLI | 已实现 | 新增 `run chapter|list|status|events|cancel|retry`（`--follow` 消费 SSE）、`artifact list|show|lineage|approve|reject`、`debug trace|errors|llm-calls|context`、`diagnostics`、`workflow`。 |
| Git 提交 | 已实现 | 成功后写 `chapters/NNNN/{brief.json,draft.md,final.md,summary.md}`，提交 trailer 含 `Run-Id` 与 `Artifact-Ids`；canon patch 批准后由 Canon Manager 唯一写入 `canon/facts.yaml`。 |
| 测试 | 已实现 | 266 unit + 26 integration（真实 PG/Redis 与进程内 worker）+ 31 CLI + 2 frontend；integration 默认从 `make test-backend` 排除，用 `make test-backend-integration` 运行。 |

## 明确未进入 M2

真实 OpenAI-compatible provider 调用与 Prompt 模板目录、完整 Agent 契约（12 类 Artifact 的 M3 版本化演进）、Canon 冲突/时间有效性/角色知识状态校验、认证 token 与 scope、`POST /debug/runs/{id}:replay` 与 sandbox 管理端点、WebUI 业务页面、Playwright E2E、快照恢复与备份脚本。

## 验证记录（native，2026-09-13）

已实际执行并通过：

- 依赖与服务：`apt` 安装 PGDG `postgresql-16` 16.15、`postgresql-16-pgvector` 0.8.6、Debian `redis-server` 8.0.2、`caddy` 2.6.2；`make native-provision` 幂等创建角色/库/扩展，输出 `novel@novel vector=0.8.6`。
- 迁移：`make native-migrate` 在 native PG 上执行 0001→0002→0003 并加载内置 Preset；`workflow_definitions` 等 9 张 M2 表存在。
- 全栈：`make native-up` 后 `make smoke` 通过（health 三组件 + 首页 + 内置 Preset）；`make native-restart` 后再次通过。
- M2 实机（经 Caddy `http://127.0.0.1:18080`）：创建 sandbox 项目 → `POST /projects/{id}/runs` 返回 202 → 真实 ARQ worker 执行 → 轮询到 `succeeded`（`current_node=canon_manager`）；产出 11 个 artifact、199 条事件、11 次 LLM call，`/debug/.../trace` 的 `errors` 为空；`/diagnostics` 全部组件 `ok`。
- SSE 实机：`curl -N .../events/stream` 收到 `run.queued`、`run.started`、`node.started`、`llm_call.started`、`artifact.created` 等帧，帧内含 `id:`/`event:`/`data:`，经 Caddy 反代正常流式输出。
- 章节产物与 Git：`chapters/0001/` 下 `brief.json`、`draft.md`、`final.md`、`summary.md` 均生成；`git log -1` 提交信息含 `Run-Id:` 与 `Artifact-Ids:`。
- 测试：backend `266 passed`（默认排除 integration）、`pytest -m integration` `26 passed`、CLI `31 passed`、frontend Vitest `2 passed`。
- Style Editor 事实保护（§7）：注入 `style_fact_diff` 的集成测试确认 run 以 `STYLE_EDITOR_FACT_CHANGE` 失败、Writer 原稿保留且不产生 `chapters/` 提交。
- 运行环境结论：Docker 不可用（`systemctl is-active docker` → `failed`，socket `permission denied`，无 rootless 替代），因此 M0/M2 验收全部走 native 路径；Compose 保留但不在本机验收。

## 下一步 M3

实现完整章节流水线的 Agent 契约与 Prompt 模板、Context Builder 的检索/预算增强、Canon 冲突与时间有效性校验、真实 OpenAI-compatible provider 与 capability probe，以及 `waiting_approval` 之后的人工编辑路径。
