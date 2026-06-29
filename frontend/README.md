# Vue3 Pipecloud Frontend

Pipecloud 的前端应用，基于 Vue 3、Vite、Vuetify 和 VisActor VTable 构建。

## 开发命令

```bash
npm install
npm run dev
npm run build
```

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
