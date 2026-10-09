# Novel Agent Platform Frontend

Next.js 前端应用。目前提供平台首页和构建信息展示；业务工作台页面属于后续 M3–M5 范围。

## 开发

从仓库根目录执行 native 启动会自动安装依赖并构建前端：

```bash
make native-up
```

单独开发前端：

```bash
npm ci --prefix frontend
npm run dev --prefix frontend
```

默认开发地址为 `http://127.0.0.1:3000`。测试：

```bash
make test-frontend
```
