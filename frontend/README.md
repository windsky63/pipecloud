# Vue3 Pipecloud Frontend

Pipecloud 的前端应用，基于 Vue 3、Vite、Vuetify 和 VisActor VTable 构建。

## 开发命令

```bash
npm install
npm run dev
npm run build
```

## 局域网开发访问

Vite 开发服务器默认监听所有网络接口。复制项目到另一台电脑并安装依赖后：

1. 在 `backend` 目录启动 Django：

   ```bash
   python manage.py runserver
   ```

2. 在 `frontend` 目录启动前端：

   ```bash
   npm run dev
   ```

3. 查看 Vite 输出中的 `Network` 地址，或在 Windows 中运行 `ipconfig` 获取该电脑的
   IPv4 地址。局域网内的其他设备可访问：

   ```text
   http://<运行项目电脑的IPv4地址>:5173
   ```

前端 API 使用 `/api` 相对路径，并由 Vite 转发到同一台电脑上的
`127.0.0.1:8000`，因此不需要向局域网单独开放 Django 的 8000 端口。
如果 Windows 防火墙弹出提示，请允许 Node.js 在“专用网络”中通信；也要确保设备
处于同一局域网，且路由器未启用客户端隔离。

## 关键目录

- `src/router/`: 路由配置，页面入口统一指向 `src/views/<PageName>/index.vue`。
- `src/views/`: 页面目录。每个页面使用独立文件夹，包含页面入口、局部 Vue 组件和页面 README。
- `src/components/`: 跨页面复用组件，例如页面标题、数据表格、仪表盘和确认弹窗。
- `src/api/`: 后端接口封装。
- `src/services/`: 前端共享状态、主题、导航标签和业务辅助逻辑。
- `src/assets/`: 前端静态资源。

## 页面目录约定

每个页面目录至少包含：

- `index.vue`: 路由入口，负责页面状态、接口调用和核心交互编排。
- `*.vue`: 页面内局部组件，用于拆分标题区、表单、列表、面板或可视化区域。
- `README.md`: 说明页面职责、路由和文件结构。
