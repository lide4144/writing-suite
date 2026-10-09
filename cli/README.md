# novelctl

`novelctl` 是 Novel Agent Platform 的 API-only 命令行客户端，不直接访问 PostgreSQL。

## 安装

native 环境启动后，CLI 位于项目虚拟环境：

```bash
.venv/bin/novelctl --base-url http://127.0.0.1:18080 health
```

也可以从 `cli/` 单独安装：

```bash
python -m pip install -e cli
```

## 常用命令

```bash
novelctl --base-url http://127.0.0.1:18080 preset list
novelctl --base-url http://127.0.0.1:18080 project create --name "Demo Novel" --kind sandbox
novelctl --base-url http://127.0.0.1:18080 run chapter --project <project-id> --chapter 1 --follow
novelctl --base-url http://127.0.0.1:18080 run status <run-id>
novelctl --base-url http://127.0.0.1:18080 artifact list --project <project-id>
```

支持 `NOVEL_API_URL`、`NOVEL_API_TOKEN` 和 `~/.config/novelctl/config.json`。将 `--json` 放在子命令之前可获得机器可读输出。退出码：`0` 成功、`2` 业务错误、`3` 连接错误。
