# UAMS 正式部署（Nginx + systemd）

本目录提供正式部署所需的配置和前端原子发布脚本。

> **当前服务器状态（2026-10-29）**：Nginx 未安装，当前执行环境没有可用的免密 sudo。
> 因此系统级安装与切换**尚未执行**；现有 Vite + uvicorn 服务仍在运行。下面命令需在有 sudo 权限的终端执行。

## 1. 部署拓扑

```text
浏览器
  │  http://<服务器IP>/            （80，仅 Nginx 对外）
  ▼
Nginx
  ├── /            → /var/www/uams/current（Vue 构建产物）
  └── /api/        → 127.0.0.1:8000（FastAPI，仅回环）
                         │
                         ▼
                    MySQL 127.0.0.1:3306（uams）
```

- 正式环境不再运行 Vite 5173；
- FastAPI 由 `uams-backend.service` 管理；
- 教学资料仍通过鉴权 API 下载，不放入 Nginx 静态目录；
- Nginx 不暴露项目源码、`.env`、备份或 Git 文件。

## 2. 文件

| 文件 | 用途 |
|---|---|
| `nginx/uams.conf` | 站点配置：SPA 回退、`/api` 代理、静态缓存、敏感文件拒绝 |
| `systemd/uams-backend.service` | FastAPI 长期运行服务（127.0.0.1:8000） |
| `deploy-frontend.sh` | 构建前端并原子发布到 `/var/www/uams/current` |

## 3. 安装步骤（需要 sudo）

### 3.1 备份现有系统配置

```bash
STAMP=$(date +%Y%m%d_%H%M%S)
sudo cp -a /etc/nginx "/etc/nginx.backup.$STAMP" 2>/dev/null || true
sudo cp -a /etc/systemd/system/uams-backend.service "/etc/systemd/system/uams-backend.service.bak.$STAMP" 2>/dev/null || true
```

### 3.2 安装 Nginx 与 rsync

```bash
sudo apt update
sudo apt install -y nginx rsync
command -v nginx && nginx -v
```

### 3.3 安装站点配置

```bash
cd /home/nglsyuyu/Software_Develop/Software_Develop/uams
sudo cp deploy/nginx/uams.conf /etc/nginx/sites-available/uams
sudo ln -sfn /etc/nginx/sites-available/uams /etc/nginx/sites-enabled/uams

# 如存在默认站点且本机只用于 UAMS，先备份再停用（不要直接删除）
if [ -e /etc/nginx/sites-enabled/default ]; then
  sudo mv /etc/nginx/sites-enabled/default "/etc/nginx/sites-enabled/default.disabled.$STAMP"
fi

sudo nginx -t
```

### 3.4 部署前端（构建 + 原子切换）

```bash
bash deploy/deploy-frontend.sh
```

脚本会：

1. `npm run build`；
2. 复制到 `/var/www/uams/releases/<时间戳>`；
3. 原子切换 `/var/www/uams/current` 软链；
4. `nginx -t` + `systemctl reload nginx`；
5. 只保留最近 3 个发布版本。

### 3.5 安装并启动 systemd 后端

先停止当前开发模式后端，避免 8000 端口冲突：

```bash
./start.sh stop

sudo cp deploy/systemd/uams-backend.service /etc/systemd/system/uams-backend.service
sudo systemctl daemon-reload
sudo systemctl enable --now uams-backend.service
sudo systemctl start nginx
sudo systemctl enable nginx
```

### 3.6 验收

```bash
sudo systemctl status uams-backend.service --no-pager
sudo systemctl status nginx --no-pager
curl -s http://127.0.0.1:8000/health
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/api/v1/terms/active   # 期望 401/403/200
./start.sh --env production
```

浏览器验证：

- 首页、登录、三种角色工作台；
- 直接刷新 `/admin/students` 等子路由不 404；
- 上传/下载教学资料（需登录且属于该教学班）；
- 浏览器开发者工具中无跨域/协议错误。

## 4. 日常管理

```bash
sudo systemctl status uams-backend nginx
sudo systemctl restart uams-backend
sudo systemctl reload nginx
journalctl -u uams-backend -f
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log
./start.sh status
```

数据库校验：

- `uams-backend.service` 启动前执行 `env_guard.py check production`；
- 库名不是 `uams`、版本不等于 Alembic head 时，服务拒绝启动；
- 不会自动迁移。

## 5. 回滚

```bash
# 1) 停用新后端
sudo systemctl stop uams-backend.service
sudo systemctl disable uams-backend.service

# 2) 恢复 Nginx 配置（按备份名调整）
sudo rm -f /etc/nginx/sites-enabled/uams
sudo mv /etc/nginx/sites-enabled/default.disabled.<STAMP> /etc/nginx/sites-enabled/default 2>/dev/null || true
sudo nginx -t && sudo systemctl reload nginx
# 或恢复整目录：sudo rm -rf /etc/nginx && sudo mv /etc/nginx.backup.<STAMP> /etc/nginx

# 3) 回退前端发布（保留旧 release 时）
sudo ln -sfn /var/www/uams/releases/<上一个版本> /var/www/uams/current

# 4) 恢复原开发/演示启动（可选）
./start.sh start
```

## 6. 安全与端口

- 只放行 80/443；**不要**放行 3306 或 8000；
- 正式环境后端只监听 `127.0.0.1:8000`；
- 不在 Nginx 中 `alias` 整个项目目录；
- `.env`、`.git`、备份、`uploads` 不进入 `/var/www/uams`；
- 生产环境必须使用强数据库口令与随机 `JWT_SECRET`（`backend/.env`，不提交 Git）；
- 当前为 HTTP，建议后续配置 HTTPS（HSTS、证书自动续期）。

## 7. 当前待授权步骤

本机 `sudo -n true` 失败（需要交互式 sudo），因此以下命令尚未执行：

```bash
sudo apt install -y nginx rsync
sudo cp deploy/nginx/uams.conf /etc/nginx/sites-available/uams
sudo ln -sfn /etc/nginx/sites-available/uams /etc/nginx/sites-enabled/uams
sudo cp deploy/systemd/uams-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now uams-backend.service
sudo systemctl enable --now nginx
bash deploy/deploy-frontend.sh
```

在获得授权前，正式环境仍由当前的 Vite + uvicorn 临时方式提供；`./start.sh` 的正式环境选项会检查 Nginx/systemd 并拒绝在未安装时启动。
