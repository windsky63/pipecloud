# PrefabWorkspace

预制排产工作台页面，对应路由 `/prefab/:moduleKey`。

## 页面职责

- 按模块展示初始化、到货、防腐、下料、焊接和未来排产等工作台内容。
- 触发后端工作流脚本，并展示模块文件、统计面板、到货文件详情和下料可视化。
- 提供未来焊接排产参数、节假日设置、到货单上传和预排产确认操作。

## 文件结构

- `index.vue`: 页面入口，维护模块路由、接口调用、工作流动作、跨模块状态和 VTable 实例生命周期。
- `PrefabWorkspaceHeader.vue`: 页面标题区局部组件，封装当前页面对公共 `PageHeader` 的使用。
- `InitializationModule.vue`: 初始化模块，展示初始化统计和初始化脚本动作。
- `ArrivalModule.vue`: 到货模块，展示当天到货、到货单明细和到货单上传。
- `CuttingModule.vue`: 下料模块，展示焊口预排产匹配结果、参数开关、下料可视化和模块动作。
- `FutureScheduleModule.vue`: 未来排产模块，维护未来焊接排产参数和日历选择。
- `WeldingModule.vue`: 焊接模块，展示焊接统计面板和焊接脚本动作。
- `GenericModule.vue`: 防腐等通用工作流模块，展示模块动作。

## 拆分边界

子模块组件只负责本模块 UI 展示和用户事件上抛；数据加载、脚本执行、路由同步、项目参数和下料 VTable 渲染仍由 `index.vue` 统一管理，避免接口调用分散。
