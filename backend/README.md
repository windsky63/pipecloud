# Vue3 Pipecloud Backend

Pipecloud 的后端服务，基于 Django 提供项目管理、文件解析、库维护和预制排产业务接口。

## 开发命令

```bash
pip install -r requirements.txt
python manage.py runserver
```

运行前可复制 `.env.example` 中的变量到系统环境或本地 `.env` 配置。
其中数据库密码和生产环境的 `DJANGO_SECRET_KEY` 不应提交到仓库。

## 关键目录

- `backend/`: Django 项目配置，包括 settings、urls、wsgi 和 asgi。
- `pipecloud/`: 面向前端的业务模型、路由和视图接口。
- `prefab_schedule/`: 预制排产核心业务脚本，覆盖初始化、到货、防腐、下料和焊接流程。
- `spool_analysis/`: IDF/PCF 解析和管段分析相关脚本。
- `file/`: 业务文件、项目文件、解析暂存结果和备份数据目录。

## 接口边界

前端主要通过 `pipecloud` 应用访问后端能力；排产脚本和 Excel 文件处理逻辑集中在 `prefab_schedule` 与 `spool_analysis` 中。新增后端能力时优先在 `pipecloud/views/` 中暴露稳定 API，再调用底层业务脚本。
