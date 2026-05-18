# AI Novel SaaS

AI 小说自动生产 SaaS 平台骨架：前端 Studio/Admin Console、FastAPI 后端、Postgres/Redis/Temporal/MinIO 基础设施。

## 一键部署

全新 Linux 服务器推荐使用傻瓜式安装命令：

```bash
curl -fsSL https://raw.githubusercontent.com/nanashiwang/ai-novel/main/install.sh | bash
```

这条命令会自动安装基础依赖和 Docker，拉取 GitHub 项目，并执行 `make deploy`。

自定义安装目录：

```bash
curl -fsSL https://raw.githubusercontent.com/nanashiwang/ai-novel/main/install.sh | APP_DIR=/opt/ai-novel bash
```

已经拉好代码时使用：

```bash
make deploy
```

快捷别名：

```bash
make d
```

完成后访问：

- 前端：http://localhost:3000
- 后端健康检查：http://localhost:8000/health
- Temporal UI：http://localhost:8080
- MinIO Console：http://localhost:9001

首次运行会自动从 `.env.example` 创建 `.env`。生产部署前请修改 `.env` 里的密钥和外部服务配置。

## 一键更新

```bash
make update
```

快捷别名：

```bash
make u
```

更新会执行：检查本地是否有未提交改动 → 从当前 GitHub 分支拉取最新代码 → 重新构建并启动容器。

## 常用快捷命令

```bash
make help      # 查看快捷命令
make logs      # 查看日志，别名 make l
make status    # 查看容器状态，别名 make s 或 make ps
make restart   # 重启前后端，别名 make r
make down      # 停止全部服务
make check     # 前后端基础校验 + compose 配置校验
```

## 本地开发

前端：

```bash
cd frontend
npm install
npm run dev
```

后端：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
uvicorn app.main:app --reload --port 8000
```
