# UAMS 正式部署（Nginx + systemd）

本目录提供正式部署所需的配置和前端原子发布脚本。

> **当前服务器状态（2026-10-29 复核）**：
> - Nginx **1.28.3 已安装并运行**，80 端口由 Ubuntu 默认站点占用；
> - 默认站点 `/etc/nginx/sites-enabled/default` 声明了 `listen 80 default_server`；
> - UAMS 站点与 `uams-backend.service` 尚未安装；
> - 当前执行环境仍无可用免密 sudo，系统级安装/切换**尚未执行**；
> - 现有 Vite + uvicorn 服务仍在运行。
>
> 下面命令需在有 sudo 权限的终端执行。

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
| `preflight-nginx.sh` | 只读检查 Nginx/80/default_server/站点/静态目录/8000 |
| `preflight-system.sh` | 只读检查 venv/env_guard/MySQL/unit/8000/静态目录 |

## 3. 安装步骤（需要 sudo）

### 3.1 备份现有系统配置

```bash
STAMP=$(date +%Y%m%d_%H%M%S)
sudo cp -a /etc/nginx "/etc/nginx.backup.$STAMP" 2>/dev/null || true
sudo cp -a /etc/systemd/system/uams-backend.service "/etc/systemd/system/uams-backend.service.bak.$STAMP" 2>/dev/null || true
```

### 3.2 只读预检

```bash
cd /home/nglsyuyu/Software_Develop/Software_Develop/uams
./deploy/preflight-nginx.sh || true
./deploy/preflight-system.sh || true
```

当前预期（未部署前）：

- Nginx 已安装、80 由默认站点监听；
- `sites-enabled/uams` 不存在；
- `/var/www/uams/current` 不存在；
- 8000 由当前 Vite/uvicorn 服务的后端占用；
- `uams-backend.service` 未安装。

### 3.3 安装 Nginx 与 rsync

```bash
sudo apt update
sudo apt install -y nginx rsync
command -v nginx && nginx -v
```

### 3.4 安装站点配置与默认站点处理

**实际配置结论**：Ubuntu 默认站点已占用 `listen 80 default_server`。因此：

- UAMS 配置**不声明** `default_server`，避免重复；
- 必须备份并停用默认站点，使 UAMS 成为唯一监听 80 的站点；
- 若本机还有其他 80 站点，不要强行把 UAMS 设为 default_server，改用域名/server_name 区分或人工确认。

```bash
cd /home/nglsyuyu/Software_Develop/Software_Develop/uams
STAMP=$(date +%Y%m%d_%H%M%S)

# 再次确认：除 default 外是否还有其他 80 站点
grep -Rsl "listen[[:space:]]\+80" /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null

sudo cp deploy/nginx/uams.conf /etc/nginx/sites-available/uams
sudo ln -sfn /etc/nginx/sites-available/uams /etc/nginx/sites-enabled/uams

# 备份并停用默认站点：必须移出 sites-enabled 目录。
# 仅在 sites-enabled 内改名（如 default.disabled）仍会被 include sites-enabled/* 加载。
if [ -e /etc/nginx/sites-enabled/default ]; then
  sudo mv /etc/nginx/sites-enabled/default "/etc/nginx/default.disabled.$STAMP"
fi

sudo nginx -t
```

停用默认站点后，80 上只剩 UAMS，访问 `http://<服务器IP>/` 才会进入 UAMS 而不是欢迎页。

### 3.5 部署前端（构建 + 原子切换）

```bash
bash deploy/deploy-frontend.sh
```

脚本行为：

1. 先 `npm run build`，成功后才创建 release；
2. 复制到 `/var/www/uams/releases/<时间戳>`，权限 `a+rX`；
3. 若 Nginx 已安装，先 `nginx -t`；失败则不切换；
4. 用临时软链 + `mv -T` 原子替换 `current`；
5. 记录上一有效版本到 `/var/www/uams/previous`；
6. Nginx 运行中则 `systemctl reload`；失败自动回滚 `current`；
7. Nginx 未安装/未运行时仍发布静态文件，但明确警告，不假装已上线；
8. 只清理 `releases/` 下符合时间戳、且不是 `current`/`previous` 的旧版本。

首次部署时 Nginx 可能尚未启动：脚本会跳过 reload，完成静态文件发布并提示；随后启动 Nginx。

### 3.6 安装并启动 systemd 后端

先再次预检并停止当前开发模式后端，避免 8000 端口冲突：

```bash
./deploy/preflight-system.sh || true
./start.sh stop

sudo cp deploy/systemd/uams-backend.service /etc/systemd/system/uams-backend.service
sudo systemctl daemon-reload
# 启动前可先用现有后端验证 Nginx 静态页与 /api 代理（见 3.7 预验证）
sudo systemctl enable --now uams-backend.service
sudo systemctl enable nginx
sudo systemctl restart nginx
```

### 3.7 预验证与验收

**切换前预验证**（保留旧后端，先让 Nginx 指向旧 uvicorn：`127.0.0.1:8000`）：

```bash
# 安装站点配置、发布静态文件后，在停止旧服务前执行
IP=$(hostname -I | awk '{print $1}')
curl -s "http://$IP/" | grep -q '<div id="app"></div>' && echo "静态首页 OK"
curl -s -o /dev/null -w 'API HTTP %{http_code}\n' "http://$IP/api/v1/terms/active"  # 401/403/200
curl -s "http://$IP/admin/students" | grep -q '<div id="app"></div>' && echo "子路由刷新 OK"
```

**启动 systemd 后验收**：

```bash
sudo systemctl status uams-backend.service --no-pager
sudo systemctl status nginx --no-pager
curl -s http://127.0.0.1:8000/health
IP=$(hostname -I | awk '{print $1}')
curl -s -o /dev/null -w '首页 HTTP %{http_code}\n' "http://$IP/"
curl -s -o /dev/null -w 'API HTTP %{http_code}\n' "http://$IP/api/v1/terms/active"
curl -s "http://$IP/admin/students" | grep -q '<div id="app"></div>' && echo "Vue 子路由回退 OK"
./start.sh --env production
./start.sh status
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
sudo mv /etc/nginx/default.disabled.<STAMP> /etc/nginx/sites-enabled/default 2>/dev/null || true
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

本机 `sudo -n true` 失败（需要交互式 sudo）。Nginx 已安装并运行，但 UAMS 站点、systemd 服务与静态发布尚未安装：

```bash
cd /home/nglsyuyu/Software_Develop/Software_Develop/uams
STAMP=$(date +%Y%m%d_%H%M%S)

# 1. 站点配置
sudo cp deploy/nginx/uams.conf /etc/nginx/sites-available/uams
sudo ln -sfn /etc/nginx/sites-available/uams /etc/nginx/sites-enabled/uams
sudo mv /etc/nginx/sites-enabled/default "/etc/nginx/default.disabled.$STAMP"
sudo nginx -t

# 2. 前端原子发布（Nginx 已运行，会执行 nginx -t/reload）
bash deploy/deploy-frontend.sh

# 3. 预验证（仍由旧 uvicorn 提供 /api）
IP=$(hostname -I | awk '{print $1}')
curl -s "http://$IP/" | grep -q '<div id="app"></div>'
curl -s -o /dev/null -w '%{http_code}\n' "http://$IP/api/v1/terms/active"

# 4. 切换后端
./start.sh stop
sudo cp deploy/systemd/uams-backend.service /etc/systemd/system/uams-backend.service
sudo systemctl daemon-reload
sudo systemctl enable --now uams-backend.service
sudo systemctl restart nginx

# 5. 验收
./start.sh --env production
./start.sh status
```

在获得授权前，正式环境仍由当前 Vite + uvicorn 临时方式提供；`./start.sh` 的正式环境选项会检查 UAMS 站点/systemd/静态目录并拒绝在未安装时启动。
