# Novel Agent Platform

这是依据 [`NOVEL_AGENT_PLATFORM_V0.1_DEVELOPMENT_SPEC.md`](NOVEL_AGENT_PLATFORM_V0.1_DEVELOPMENT_SPEC.md) 实现的平台。当前包含 M0 运行环境、M1 的 Project、Model Registry、Preset CRUD/YAML 校验、项目目录初始化、独立 Git 仓库和 API-only CLI，以及 M2 的 Artifact registry、Workflow/DAG runner、Run/Node 状态机、Event Log、Fake provider、SSE 和 ARQ 业务 job。

## 文档导航

- [开发环境与首次启动](docs/DEV_ENVIRONMENT.md)
- [实现状态、验收记录与后续计划](docs/IMPLEMENTATION_STATUS.md)
- [变更记录](CHANGELOG.md)
- [后端说明](backend/README.md)
- [CLI 说明与命令示例](cli/README.md)
- [前端说明](frontend/README.md)
- [开发规格](NOVEL_AGENT_PLATFORM_V0.1_DEVELOPMENT_SPEC.md)

## 架构概览

```text
Client / novelctl
       │
       ▼
Caddy (统一入口 :18080)
   ├── Next.js frontend
   └── FastAPI API ── PostgreSQL 16 + pgvector
                    └── Redis ── ARQ worker ── Workflow runner

projects/ 保存项目 manifest、Artifact、章节文件与 Git 历史
```

native 是默认运行方式；Docker Compose 作为可选部署路径保留。生产环境使用前请配置认证、HTTPS、最小权限数据库账号和外部 secret 管理。

## 源码运行（默认）

本机 DroidSpaces Debian 13 没有可用的 Docker daemon，因此默认不使用 Docker 运行应用：宿主机提供 PostgreSQL 16 + pgvector、Redis、Caddy，Python/Node 直接运行 API、worker 和前端。完整的版本、端口、初始化与故障排查见 [`docs/DEV_ENVIRONMENT.md`](docs/DEV_ENVIRONMENT.md)。

### Debian 13 依赖

Debian 13 自带 PostgreSQL 17，而规格要求 PostgreSQL 16，因此使用 PostgreSQL 官方 APT 仓库：

```bash
sudo install -d /usr/share/postgresql-common/pgdg
curl -fsS https://www.postgresql.org/media/keys/ACCC4CF8.asc \
  | sudo tee /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc >/dev/null
echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt trixie-pgdg main" \
  | sudo tee /etc/apt/sources.list.d/pgdg.list >/dev/null
sudo apt-get update
sudo apt-get install -y postgresql-16 postgresql-16-pgvector postgresql-client-16 redis-server caddy
sudo systemctl enable --now postgresql
# 系统 Caddy 会占用 80；native 路径用自己的 Caddyfile 和 18080 端口
sudo systemctl disable --now caddy
```

数据库角色、库与 pgvector 扩展由幂等脚本创建（本机开发；生产请使用最小权限凭据）：

```bash
make native-provision
```

### 安装、构建和启动

```bash
cp .env.native.example .env.native
make native-up
curl -fsS http://127.0.0.1:18080/api/health
```

`make native-up` 会依次确保依赖安装、Next.js 构建、Alembic migration 与内置 Preset bootstrap，然后启动 ARQ worker、FastAPI、Next.js 和 Caddy。native Caddy 默认只监听 `127.0.0.1:18080`；端口被占用时修改 `.env.native` 的 `HTTP_PORT`，并把 `BASE_URL` 设为同一地址。只有已配置可信 Tailscale 或 SSH tunnel 时，才应改变监听地址。

`make up`、`make down`、`make health`、`make smoke` 和 `make test` 均走 native 路径；运行日志位于 `.run/native/`：

```bash
make native-status
make native-logs
make native-restart
make native-down
```

PostgreSQL 与 Redis 都由宿主机 systemd 服务管理（Redis 需要一行 `PrivateUsers=no` drop-in，见 [`docs/DEV_ENVIRONMENT.md`](docs/DEV_ENVIRONMENT.md) §5），`make native-down` 不会停止它们。

入口路由：

- `/`：Next.js 首页。
- `/health`、`/api/health`：FastAPI 健康检查。
- `/api/v1/*`：业务 API。

健康检查必须同时看到 PostgreSQL、Redis 和 ARQ worker heartbeat 正常才返回 HTTP 200。首次启动时 `migrate` 会执行 Alembic migration 并幂等加载内置 Preset，然后 API 和 worker 才启动。

## M1 API 示例

```bash
# 查看内置 Preset
curl -fsS http://127.0.0.1:18080/api/v1/presets

# 创建 sandbox 项目；重复发送同一个 Idempotency-Key 会复用同一资源
curl -fsS -X POST http://127.0.0.1:18080/api/v1/projects \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-project-1' \
  -d '{"name":"Demo Novel","kind":"sandbox"}'

# 应用 Preset 时，将上一步 Preset version 的 id 放入请求体
curl -fsS -X POST http://127.0.0.1:18080/api/v1/projects/<project-id>/preset:apply \
  -H 'Content-Type: application/json' \
  -d '{"preset_version_id":"<preset-version-id>"}'
```

写 API 返回统一错误结构，包含 `code`、`message`、`details` 和 `request_id`；每个请求也会返回 `X-Request-ID`。Model endpoint 只保存 `secret_ref`，实际密钥从 API 进程环境变量读取，绝不写入数据库或项目 Git。

## M2 API 示例

```bash
# 1. 启动章节工作流（202 + run_id；重复发送同一个 Idempotency-Key 复用同一 Run）
RUN=$(curl -fsS -X POST http://127.0.0.1:18080/api/v1/projects/<project-id>/runs \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: chapter-1-run' \
  -d '{"workflow":"chapter_generation","input":{"chapter_number":1},"mode":"normal"}')
RUN_ID=$(echo "$RUN" | python3 -c 'import sys,json;print(json.load(sys.stdin)["run_id"])')

# 2. 跟踪实时事件（SSE；断线后用 Last-Event-ID 续传）
curl -N "http://127.0.0.1:18080/api/v1/runs/$RUN_ID/events/stream"

# 3. 查询 Run / 节点 / 事件
curl -fsS "http://127.0.0.1:18080/api/v1/runs/$RUN_ID"
curl -fsS "http://127.0.0.1:18080/api/v1/runs/$RUN_ID/nodes"
curl -fsS "http://127.0.0.1:18080/api/v1/runs/$RUN_ID/events?after=0"

# 4. Artifact registry：列表、单条、lineage、审批
curl -fsS "http://127.0.0.1:18080/api/v1/projects/<project-id>/artifacts?type=canon_patch"
curl -fsS "http://127.0.0.1:18080/api/v1/artifacts/<artifact-id>/lineage"
curl -fsS -X POST "http://127.0.0.1:18080/api/v1/artifacts/<artifact-id>:approve"

# 5. 调试数据面
curl -fsS "http://127.0.0.1:18080/api/v1/debug/runs/$RUN_ID/trace"
curl -fsS "http://127.0.0.1:18080/api/v1/diagnostics"

# 6. 取消 / 重试（失败或取消的 Run 会派生新的 attempt Run）
curl -fsS -X POST "http://127.0.0.1:18080/api/v1/runs/$RUN_ID:cancel"
curl -fsS -X POST "http://127.0.0.1:18080/api/v1/runs/$RUN_ID:retry"
```

M2 默认使用确定性 `FakeProvider`，因此**不需要真实模型**即可完整跑通章节工作流；`input.fake_faults` 与 `input.fake_scenario` 是自动化用的故障注入开关，`APP_ENV=production` 时会被拒绝。production 项目的 canon patch 停在 `proposed` 并让 Run 进入 `waiting_approval`，由人工 approve/reject 后继续；sandbox 项目自动批准。

## CLI

CLI 是 API client，不直连 PostgreSQL。native 安装会将 CLI 安装到项目 `.venv`：

```bash
.venv/bin/novelctl --base-url http://127.0.0.1:18080 health
.venv/bin/novelctl --base-url http://127.0.0.1:18080 preset list
.venv/bin/novelctl --base-url http://127.0.0.1:18080 project create --name "Demo Novel" --kind sandbox
.venv/bin/novelctl --base-url http://127.0.0.1:18080 preset apply long_novel_high_quality --project <project-id>

# M2
.venv/bin/novelctl --base-url http://127.0.0.1:18080 run chapter --project <project-id> --chapter 1 --follow
.venv/bin/novelctl --base-url http://127.0.0.1:18080 run status <run-id>
.venv/bin/novelctl --base-url http://127.0.0.1:18080 run cancel <run-id>
.venv/bin/novelctl --base-url http://127.0.0.1:18080 artifact list --project <project-id> --type canon_patch
.venv/bin/novelctl --base-url http://127.0.0.1:18080 artifact approve <artifact-id>
.venv/bin/novelctl --base-url http://127.0.0.1:18080 debug trace <run-id>
.venv/bin/novelctl --base-url http://127.0.0.1:18080 diagnostics
```

也可通过 `NOVEL_API_URL`、`NOVEL_API_TOKEN` 或 `~/.config/novelctl/config.json` 配置地址/token。所有命令支持全局 `--json`（放在子命令之前）；成功、业务失败、连接失败分别使用退出码 0、2、3。`run chapter --follow` 以节点为粒度输出 SSE 进度。

## 验证

```bash
make test-backend              # 单元测试（默认跳过 integration 标记）
make test-backend-integration  # 需要本机 PostgreSQL/Redis 的集成测试
make test-frontend
make test-cli
make smoke
```

集成测试使用独立数据库 `novel_test`（可被 `TEST_DATABASE_URL` 覆盖），首次运行会自动创建并执行 migration。

若使用非默认 HTTP 端口，传入同一个入口地址：`BASE_URL=http://127.0.0.1:18081 make smoke`。

完整重启恢复检查：

```bash
make native-restart
make smoke
make native-down
make native-up
make smoke
```

native 模式的数据由 PostgreSQL 服务和 `projects/` 目录保存；`make native-down` 不删除数据。

## 可选 Docker 路径

Compose 文件保留给具备可用 Docker daemon 的主机或 CI。本机 DroidSpaces Debian 13 上 Docker 起不来，原因不是权限而是**内核能力**：droidspace 的 `6.6.127-android15` 内核没有 `bridge` / `br_netfilter` 模块，iptables 也没有 `filter` 表，dockerd 在初始化 bridge 网络驱动时报 `failed to create FILTER chain DOCKER: iptables: No chain/target/match by that name` 并退出（`systemctl is-active docker` → `failed`）。这与 user namespace 无关，本机 `unshare -Ur`、`bwrap` 均正常。在支持 Docker 的 Debian 主机上：

```bash
cp .env.example .env
make compose-up
make compose-health
make compose-smoke
make compose-down
```

Compose 的完整状态和限制见 [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md)。

## 安全与版本控制

- `.env`、`.env.*`、`.venv/`、运行日志和 `projects/` 默认不会提交；只提交 `.env.example` 等模板文件。
- 不要把真实 API key、数据库密码、生产配置或生成的项目数据提交到仓库。
- Model endpoint 只保存 `secret_ref`，实际密钥由 API 进程环境变量提供。
- 当前仓库版本为 v0.1 早期开发版，API 仍可能变化；变更请同步更新 README、相关 docs 和 `CHANGELOG.md`。

## 当前限制与边界

- 默认配置适合本地可信边界；生产部署仍需要 secret 管理、HTTPS/Tailscale 和认证 token migration。
- Project 的数据库元数据和磁盘 manifest/Git 通过 application service 协调，但跨介质写入不是 ACID；后续需要 outbox/saga 完善恢复。
- native 运行要求宿主机先提供 PostgreSQL 16 + pgvector、Redis 和 Caddy；`make native-down` 不停止系统 PostgreSQL。
- 章节流水线的完整 Agent 契约、Prompt 模板、Canon 审批、WebUI 业务页面、Debug/Replay API 与 Playwright E2E 仍属于后续里程碑（M3–M5）。
