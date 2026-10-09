# Native 开发环境（DroidSpaces Debian 13 / aarch64）

本机没有可用的 Docker daemon，因此本项目的默认运行方式是 **native 源码运行**：宿主机直接提供 PostgreSQL 16 + pgvector、Redis、Caddy，Python/Node 直接运行 API、worker 和前端。Docker Compose 仍然保留为可选部署路径。

规格依据：[`NOVEL_AGENT_PLATFORM_V0.1_DEVELOPMENT_SPEC.md`](../NOVEL_AGENT_PLATFORM_V0.1_DEVELOPMENT_SPEC.md) §0.1、§3.2、§15.3。

## 1. 已验证的版本

| 组件 | 版本 | 来源 | 说明 |
| --- | --- | --- | --- |
| OS | Debian 13 (trixie), aarch64 | — | DroidSpaces 环境；`/var/run/docker.sock` 权限拒绝且 `docker` 单元为 `failed` |
| PostgreSQL | 16.15 | PGDG `trixie-pgdg` | 与规格 §3.1 要求的 PostgreSQL 16 一致（Debian 13 自带的是 17） |
| pgvector | 0.8.6 | PGDG `postgresql-16-pgvector` | `CREATE EXTENSION vector` 由 migration 0001 执行 |
| Redis | 8.0.2 | Debian 13 `redis-server` | systemd 托管；需要一行 drop-in 放宽 `PrivateUsers`，见 §5 |
| Caddy | 2.6.2 | Debian 13 `caddy` | 使用仓库内 `Caddyfile.native`，`127.0.0.1:18080` |
| Python | 3.12.14 | `uv python install 3.12` | 与 compose 镜像的 3.12 对齐；系统 Python 为 3.13，也可用 |
| Node.js | 24.20.0 | nvm | Next.js 16 standalone |
| Git | 系统包 | Debian | 每个项目独立仓库，提交 trailer 记录 run/artifact |

## 2. 首次初始化

```bash
# 1. 系统依赖（需要 sudo）
sudo install -d /usr/share/postgresql-common/pgdg
curl -fsS https://www.postgresql.org/media/keys/ACCC4CF8.asc \
  | sudo tee /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc >/dev/null
echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt trixie-pgdg main" \
  | sudo tee /etc/apt/sources.list.d/pgdg.list >/dev/null
sudo apt-get update
sudo apt-get install -y postgresql-16 postgresql-16-pgvector postgresql-client-16 redis-server caddy
sudo systemctl enable --now postgresql

# 2. Python 3.12（可选；若系统已有 3.12 可跳过）
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12

# 3. 本机配置
cp .env.native.example .env.native

# 4. 角色/库/pgvector + Redis 单元 drop-in + 启动系统服务（幂等，需要 sudo）
make native-provision

# 5. 依赖安装 + 构建 + 迁移 + 启动
make native-up

# 6. 验证
curl -fsS http://127.0.0.1:18080/api/health
make smoke
```

`.env.native` 会被 `scripts/native_common.sh` 用 bash `source` 读取，因此含空格的值必须加引号（例如 `GIT_USER_NAME="Novel Agent Platform"`）。

## 3. 日常命令

```bash
make native-up          # 幂等：确保依赖/构建/迁移，然后启动全栈
make native-down        # 停止 caddy/frontend/api/worker（不停止 PostgreSQL/Redis 系统服务）
make native-restart     # 重启应用进程
make native-status      # postgres / redis / worker / api / frontend / caddy 状态
make native-logs        # 跟踪 .run/native/*.log
make native-migrate     # Alembic upgrade head + 内置 Preset bootstrap
make native-smoke       # 冒烟：health 三组件 + 首页 + 内置 Preset
make test-backend       # backend pytest（默认排除 integration 标记）
make test-frontend      # Vitest
make test-cli           # novelctl pytest
```

日志与运行状态位于 `.run/native/`（pid 文件 + 每个服务一个 `.log`）。项目数据位于 `projects/`，数据库数据由系统 PostgreSQL 管理。

## 4. 端口与入口

| 入口 | 地址 | 备注 |
| --- | --- | --- |
| 统一入口（Caddy） | `http://127.0.0.1:18080` | `/api/*`、`/health` → API；其余 → Next.js |
| API 直连 | `http://127.0.0.1:8000` | 仅 loopback，调试用 |
| 前端直连 | `http://127.0.0.1:3000` | 仅 loopback |
| PostgreSQL | `127.0.0.1:5432` | 系统 systemd 服务 |
| Redis | `127.0.0.1:6379` | 开发进程 |

非 root 用户无法绑定 80 端口，因此 native Caddy 使用 18080；这与 Compose 中 Caddy 容器内部监听 8080、宿主机再映射到 80 是同一套配置，只是少了端口映射。若确实需要 80，可在具备 root 的主机上把系统 Caddy 指向 `Caddyfile.native`，或调整 `net.ipv4.ip_unprivileged_port_start`。

## 5. 已知环境差异与处理

1. **Redis 单元需要一行 drop-in**：Debian 的 `redis-server.service` 启用了 `PrivateUsers=yes`，本机 systemd 为该单元建立 user namespace 时失败，报 `Failed to set up user namespacing: No such file or directory`，单元以 `status=217/USER` 退出。注意**这不是"user namespace 不可用"**：`unshare -U` / `unshare -Ur`、`bwrap`、以及临时单元（`systemd-run --property=PrivateUsers=yes`）在本机都实测正常，是该单元这组 hardening 的组合问题。`make native-provision` 会写入 `/etc/systemd/system/redis-server.service.d/20-private-users.conf`（仅 `PrivateUsers=no`，其余 hardening 保留）、`daemon-reload` 并 `enable --now redis-server`。修复后 `systemctl is-active redis-server` → `active`，`redis-cli ping` → `PONG`，`make native-status` 显示 `systemd redis-server.service`。若某台主机仍无法运行该单元，`scripts/native_ctl.sh` 会退回以开发进程方式启动 Redis（`127.0.0.1:6379`，关闭持久化，pid 记录在 `.run/native/redis.pid`）。
2. **Caddyfile.native 必须写 `http://`**：站点地址若只写主机名，Caddy 会按 HTTPS 站点处理，对明文请求返回 `Client sent an HTTP request to an HTTPS server`。文件内已固定为 `http://127.0.0.1:{$HTTP_PORT}`，并关闭 `auto_https`。
3. **进程组管理**：`api`/`web` 通过 `npm`、`uvicorn` 等包装进程启动，直接 kill 包装进程会残留真正监听端口的子进程。`scripts/native_ctl.sh` 使用 `setsid` 建立独立进程组并按进程组发送信号。
4. **系统 Caddy 服务**：安装 Debian 包时会启用 `caddy.service` 并占用 80 端口，本机已 `disable --now`，避免与 native Caddy 冲突。
5. **数据库角色是 SUPERUSER**：仅为本地开发，因为 Alembic 0001 需要执行 `CREATE EXTENSION vector`。生产环境必须换成最小权限角色并由 DBA 预装扩展。

## 6. 与 Compose 路径的等价性

- 相同的健康检查语义：PostgreSQL、Redis、worker heartbeat 三者都正常，`/api/health` 才返回 200。
- 相同的服务拓扑与启动顺序：migration/bootstrap → worker → API → web → Caddy。
- 相同的路由：`/api/*` 与 `/health` 到 API，其余到 Web。
- 相同的迁移：同一套 Alembic revision，native 与 Compose 共用。
- 差异：native 用宿主机服务与进程，Compose 用容器、named volume、healthcheck 与 restart policy；验证命令分别是 `make smoke` 与 `make compose-smoke`。

## 7. 故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `make native-up` 报 PostgreSQL 不可达 | 系统服务未启动 | `sudo systemctl start postgresql`，再 `make native-status` |
| `EADDRINUSE 127.0.0.1:3000` | 上一次的 node 子进程残留 | `make native-down`（会按进程组清理），必要时 `ss -ltnp \| grep 3000` 后手动 kill |
| `Client sent an HTTP request to an HTTPS server` | Caddyfile 站点地址缺少 `http://` | 使用仓库内 `Caddyfile.native` |
| `/api/health` 返回 503 `heartbeat_missing_or_stale` | worker 未运行或 Redis 不通 | `make native-status`、`tail -f .run/native/worker.log` |
| `ModuleNotFoundError: pgvector` | venv 未安装新增依赖 | `make native-install` |
| `sudo: a terminal is required` | 在非交互环境执行 provision | 用终端执行，或 `NATIVE_SUDO_FLAGS=-S` 并从 stdin 提供密码 |
