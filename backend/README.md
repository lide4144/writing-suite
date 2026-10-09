# Novel Agent Platform Backend

FastAPI 服务与 ARQ worker，负责平台的核心 API、数据库迁移、项目文件管理、Preset、Artifact registry 和章节工作流运行时。

## 主要能力

- Project、Model Registry、Preset CRUD 与 YAML/JSON Schema 校验
- 项目目录初始化、manifest 管理和独立 Git 提交
- Artifact 版本、Schema 校验与 lineage
- Workflow/DAG runner、Run/Node 状态机、重试与取消
- Event Log、LLM 调用记录、SSE 事件流和调试 API
- 默认的确定性 `FakeProvider`，无需真实模型即可运行测试工作流

## 本地开发

从仓库根目录执行：

```bash
cp .env.native.example .env.native
make native-provision   # 首次执行，需要 sudo；准备 PostgreSQL 16 + pgvector 和 Redis
make native-up
make smoke
```

后端直接访问 `http://127.0.0.1:8000`，推荐通过统一入口 `http://127.0.0.1:18080` 访问。完整环境说明见 [`../docs/DEV_ENVIRONMENT.md`](../docs/DEV_ENVIRONMENT.md)。

## 测试

```bash
make test-backend
make test-backend-integration  # 需要可用的 PostgreSQL 和 Redis
```
