# Vue3 Pipecloud Frontend

前端是基于 Vue 3 和 Vite 的单页应用，使用 Vuetify 构建界面、VisActor VTable 展示和编辑大型表格、Three.js 展示管段与预制工厂三维模型。页面通过统一 API 层访问 Django，并以当前项目作为业务上下文。

## 开发命令

```bash
npm install
copy .env.example .env
npm run dev
npm run build
```

`VITE_API_BASE_URL` 是浏览器使用的 API 根地址。开发服务器监听地址、端口、代理目标和超时由 `VITE_DEV_HOST`、`VITE_DEV_PORT`、`VITE_API_PROXY_TARGET`、`VITE_PROXY_TIMEOUT_MS` 控制。只有 `VITE_` 前缀变量会进入浏览器构建，密码或服务端密钥不可使用此前缀。

Vite 默认监听所有网络接口，局域网设备可打开 `http://<开发电脑 IPv4>:5173`。前端使用 `/api` 相对路径并由 Vite 代理到本机 Django，因此通常无需向局域网单独开放后端 8000 端口。

## 目录结构与职责

```text
frontend/
├─ public/                           原样发布的静态资源
│  └─ models/prefab-factory.fbx      预制工厂三维模型
├─ src/
│  ├─ main.js                        创建应用并装配 i18n、Vuetify 和路由
│  ├─ App.vue                        应用壳、侧栏、消息中心和运行日志
│  ├─ style.css                      全局主题变量和通用布局样式
│  ├─ i18n.js                        中英文界面文本及插值函数
│  ├─ api/                           按后端领域封装 HTTP 请求
│  │  ├─ http.js                     API 根地址、JSON 请求和统一错误解析
│  │  ├─ projects.js                 项目、约束、焊口和管段接口
│  │  ├─ fileParser.js               文件上传、解析任务和结果确认
│  │  ├─ fileExports.js              文件树及批量导出任务
│  │  ├─ libraries.js                焊口库和计划库接口
│  │  ├─ workflow.js                 工序动作、仪表盘和排产接口
│  │  ├─ plans.js                    计划查看、编辑和导入导出
│  │  ├─ uploads.js                  通用上传接口
│  │  ├─ factory.js                  工厂材料接口
│  │  └─ developer.js                开发工具接口
│  ├─ components/                    跨页面复用组件
│  │  ├─ UiMessageCenter.vue         全局成功、警告、错误消息展示
│  │  ├─ DataVTable.vue              通用大数据表格封装
│  │  ├─ FileUploadDropzone.vue      拖放与选择上传文件
│  │  ├─ UnsavedChangesDialog.vue    未保存修改确认
│  │  ├─ AppSidebar.vue              主导航和项目入口
│  │  └─ *DashboardPanel.vue         各工序仪表盘展示组件
│  ├─ composables/
│  │  └─ useRunLogPanel.js           可折叠、可拖动运行日志面板逻辑
│  ├─ config/
│  │  └─ runtime.js                  浏览器运行时 API 配置
│  ├─ plugins/
│  │  └─ vuetify.js                  组件、图标、语言和主题配置
│  ├─ router/
│  │  └─ index.js                    页面懒加载、重定向和项目选择守卫
│  ├─ services/                      跨页面状态与纯业务辅助逻辑
│  │  ├─ pipecloudState.js           系统摘要、界面设置和任务运行状态
│  │  ├─ projectState.js             当前项目持久化与项目访问提示
│  │  ├─ weldLibraryState.js         焊口库列表共享状态
│  │  ├─ uiMessages.js               全局消息发布、转发、历史与自动关闭
│  │  ├─ navigationLabels.js         业务模块和库的本地化名称
│  │  ├─ vtableTheme.js              VTable 主题适配
│  │  ├─ vtableSelectionCount.js     大表格选择计数与布局辅助
│  │  └─ pipeComponentRenderer.js    管件三维渲染辅助
│  └─ views/                         路由页面
│     ├─ PrefabHome/                 项目首页、项目数据和工序仪表盘
│     ├─ FileParser/                 Excel/IDF/PCF 上传、解析和结果恢复
│     ├─ PrefabWorkspace/            到货、防腐、下料、焊接排产工作台
│     ├─ PlanViewer/                 日历、甘特和计划文件编辑
│     ├─ WeldLibraryViewer/          焊口/计划库大表格维护
│     ├─ SpoolCheck/                 管段结构和三维检查
│     ├─ PrefabFactory/              三维工厂与当日材料展示
│     ├─ FileExport/                 项目文件批量导出
│     ├─ SystemSettings/             主题、语言、导航和消息设置
│     └─ DeveloperControls/          数据库、定时任务和操作日志
├─ index.html                        Vite HTML 入口
├─ vite.config.js                    开发服务器、代理和构建配置
├─ package.json                      npm 脚本与依赖
└─ .env.example                     前端环境变量模板
```

## 页面与代码约定

每个主要页面使用 `src/views/<PageName>/index.vue` 作为路由入口；页面专属标题、面板和说明放在同目录。跨页面复用的 UI 放入 `components/`，跨页面状态或无 UI 的业务逻辑放入 `services/`，可复用的组合式交互放入 `composables/`。

用户操作反馈通过 `services/uiMessages.js` 发布到 `UiMessageCenter.vue`。表单字段校验、长任务进度和必须持续可见的数据异常可以保留在当前页面，但操作结果同时应转发到消息中心，避免路由切换或页面局部布局使提示不可见。

新增后端调用时，应先在 `src/api/` 对应领域文件中封装请求，页面不要直接拼接 API 地址。新增路由页面应使用懒加载，并根据是否必须选择项目更新 `router/index.js` 的访问规则。
