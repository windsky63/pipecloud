# Vue3 Pipecloud Backend

后端基于 Django，负责项目与业务数据持久化、文件解析和导出、各工序业务接口、预制排产脚本编排，以及计划完成情况同步和滚动等定时任务。

## 开发与运行

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py runserver
```

操作系统或部署平台注入的环境变量优先于 `.env`。数据库密码和生产环境的 `DJANGO_SECRET_KEY` 不应提交到仓库；当 `DJANGO_DEBUG=false` 时必须显式配置安全密钥。配置读取集中在 `backend/env.py`，布尔值、端口和任务执行时间会在启动阶段校验。

定时任务应作为独立常驻进程运行：

```bash
python manage.py run_scheduler
```

默认从每天 21:00（Asia/Shanghai）开始依次同步防腐、下料和焊接完成情况，并滚动未完成的下料与焊接计划。具体开关、时间和补偿执行窗口见 `.env.example`。手动预演或补跑可使用：

```bash
python manage.py update_plan_completion --dry-run
python manage.py update_plan_completion --date 20260630
```

测试：

```bash
python manage.py test pipecloud.tests
```

## 目录结构与职责

```text
backend/
├─ backend/                         Django 项目配置包
│  ├─ env.py                        类型化读取并校验 .env/系统环境变量
│  ├─ settings.py                   数据库、中间件、时区、日志等框架配置
│  ├─ scheduled_jobs.py             APScheduler 任务清单与执行时间定义
│  ├─ urls.py                       Django 根路由
│  ├─ asgi.py                       ASGI 服务入口
│  └─ wsgi.py                       WSGI 服务入口
├─ pipecloud/                       面向 Web 前端的 Django 业务应用
│  ├─ models.py                     项目、解析任务、计划摘要等持久化模型
│  ├─ urls.py                       /api/pipecloud 下的业务路由
│  ├─ middleware.py                 API 请求上下文和异常处理
│  ├─ views/                        按 API 领域拆分的控制层
│  │  ├─ common.py                  参数、响应、路径等公共辅助函数
│  │  ├─ projects.py                项目、约束、焊口和管段数据接口
│  │  ├─ file_parser.py             上传、解析、预览、恢复和确认导入
│  │  ├─ file_exports.py            项目文件树与异步批量导出
│  │  ├─ libraries.py               各类焊口/计划库的查询和编辑
│  │  ├─ workflow.py                仪表盘、工序动作和排产工作流
│  │  ├─ plans.py                   计划查询、移动、导入导出和保存
│  │  ├─ uploads.py                 通用业务文件上传
│  │  ├─ factory.py                 工厂场景所需的当日材料数据
│  │  └─ developer.py               数据库、任务和操作日志开发接口
│  ├─ services/                     可复用的领域服务层
│  │  ├─ db_storage.py              文件/表格数据的数据库存储基础能力
│  │  ├─ prefab_database.py         预制业务数据库读写与兼容层
│  │  ├─ project_tables.py          项目动态表与字段管理
│  │  ├─ project_constraints.py     项目约束读取与保存
│  │  ├─ idf_model_storage.py       IDF 模型及解析结果持久化
│  │  ├─ file_exports.py            文件树、安全路径和导出内容组织
│  │  ├─ file_export_jobs.py        批量导出后台任务状态管理
│  │  ├─ plan_completion.py         工序完成情况同步
│  │  └─ plan_rollover.py           未完成计划滚动
│  ├─ management/commands/          运维、迁移、同步和排产管理命令
│  ├─ migrations/                   Django 数据库迁移
│  └─ tests/                        API、服务、排产与回归测试
├─ prefab_schedule/                 Excel 驱动的预制排产核心逻辑
│  ├─ project_config.py             项目目录和业务文件定位
│  ├─ common_utils.py               跨工序 Excel/路径公共工具
│  ├─ schedule.py                   排产流程公共编排入口
│  ├─ initialization/               初始化数据、材料明细和预制焊口库
│  │  └─ auto_weld_split/           自动焊识别、连接提取和形状判断
│  ├─ arrival/                      到货配置与材料库维护
│  ├─ anti_corrosion/               防腐预排产匹配和委托生成
│  ├─ cutting/                      下料预排产、匹配和切割计划
│  └─ welding/                      焊接排产及自动焊排产
│     └─ auto_weld_schedule/        自动焊提取、材料明细和计划生成
├─ spool_analysis/                  IDF/PCF 解析、材料拆分和管段结构分析
├─ file/                            项目文件、临时解析结果、导出与备份
├─ manage.py                        Django 管理入口
├─ create_pipecloud_database.py     MySQL 数据库初始化辅助脚本
├─ requirements.txt                 Python 依赖
└─ .env.example                     可复制的后端配置模板
```

`file/` 是运行时数据目录，不应作为源码提交。视图层只负责鉴权/校验、调用服务并返回稳定 JSON；数据库与文件操作放在 `pipecloud/services/`，Excel 排产算法放在 `prefab_schedule/`，格式解析放在 `spool_analysis/`。

## 接口边界

前端统一访问 `/api/pipecloud`。新增功能时应优先在 `pipecloud/views/` 暴露稳定接口，在 `pipecloud/services/` 组织可测试的业务能力，再调用 `prefab_schedule/` 或 `spool_analysis/` 中的底层算法。所有由请求传入的文件路径都必须经过项目目录边界检查，避免访问项目运行目录之外的文件。
