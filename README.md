# Vue3 Pipecloud

Vue3 Pipecloud 是面向管道预制业务的前后端分离应用。前端负责项目选择、文件解析、库维护、排产工作台和排产单查看；后端负责 Django API、Excel 文件处理、管段解析和预制排产业务脚本调度。

## 前端关键目录

    frontend/src/views/
        页面视图。每个页面按文件夹组织，例如 views/PrefabWorkspace/index.vue，
        同目录包含页面局部组件和 README.md。

    frontend/src/services/
        前端共享状态和接口调用封装。

    frontend/src/router/
        前端路由配置。

    frontend/src/components/
        可复用组件目录。

    frontend/public/
        静态资源目录。

    frontend/README.md
        前端开发命令、目录约定和页面拆分说明。

## 后端关键目录

    backend/backend/
        Django 项目配置。

    backend/pipecloud/
        面向前端的业务接口、路由和脚本调度入口。

    backend/prefab_schedule/
        预制排产核心业务脚本和 Excel 数据目录。

    backend/prefab_schedule/初始化文件处理/
        原始焊口初始化数据处理。

    backend/prefab_schedule/到货管理/
        入库单导入和材料库维护。

    backend/prefab_schedule/防腐管理及排产/
        防腐委托与防腐材料库处理。

    backend/prefab_schedule/下料管理及排产/
        焊口预排产匹配、待确认防腐库和切割可视化数据来源。

    backend/prefab_schedule/焊接管理及排产/
        焊口库维护、自动焊划分和自动焊排产。

    backend/prefab_schedule/文件/
        业务 Excel 输入、输出、中间结果、材料库和备份目录。

    backend/README.md
        后端开发命令、目录说明和接口边界说明。

## 页面拆分约定

前端页面不再直接平铺在 `frontend/src/views` 下。每个页面使用独立目录：

    frontend/src/views/<PageName>/
        index.vue
        <PageName>Header.vue
        README.md

`index.vue` 作为路由入口，保留页面级状态、接口调用和核心交互；同目录 Vue 文件承载页面局部组件，后续可继续把表单、列表、弹窗和可视化区域从入口中拆出。
