# uams/scripts —— 环境准备与运维脚本

## 作用

搭建和维护 UAMS 的**运行环境**（数据库安装、容器清理）。这些脚本需要 `sudo` 权限，只在新环境部署或环境调整时执行一次。

## 主要内容

| 文件 | 说明 |
|---|---|
| `setup_mysql.sh` | MySQL 8.4 原生安装与初始化：安装 `mysql-server`、启用并启动服务、写入 `/etc/mysql/mysql.conf.d/99-uams.cnf`（utf8mb4 / 严格模式 / `+08:00` / 仅回环监听）、创建 `uams` 库与 `uams_app` 用户、连接校验 |
| `uninstall_docker.sh` | 卸载 Docker 及其残留（项目已改用本机原生 MySQL，不再需要 Docker）：停止服务、卸载软件包、清理孤立依赖、删除 `/opt/docker-desktop` 与 `~/.docker` 等残留、移除 kvm 组、回收约 7.8 GB |

> 种子数据脚本（`seed_rbac.py`、`seed_demo.py`）位于 [`backend/scripts/`](../backend/scripts/)，不在本目录。

## 依赖关系

```
setup_mysql.sh      →  apt / systemctl / mysql / ~/uams-infra/.env（读取凭据）
uninstall_docker.sh →  apt / systemctl --user / 文件系统清理
```

两者均**不依赖应用代码**，可在后端依赖安装之前执行。

## 开发注意事项

1. **两个脚本都需要 `sudo`**，用法：`sudo bash uams/scripts/setup_mysql.sh`
2. `setup_mysql.sh` 从 `~/uams-infra/.env` 读取数据库密码，密码不出现在脚本内，也不进入命令行历史
3. `setup_mysql.sh` 会检测 `validate_password` 组件是否启用 —— 若启用，简单密码会被拒绝，脚本会给出处理提示
4. 两个脚本都幂等：已安装的组件会被跳过，不会重复安装或覆盖数据
5. `uninstall_docker.sh` 会执行删除操作，**运行前请通读**
6. 修改后必须语法检查：`bash -n <script>`

## 当前状态

- **已实现**：MySQL 安装初始化、Docker 卸载
- **说明**：项目已从 Docker + openGauss 方案切换到本机原生 MySQL，`uninstall_docker.sh` 是该切换的收尾脚本，保留备查

## 相关文档

- [docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md) — 部署说明
- [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md) — 环境准备
- [docs/DATABASE.md](../docs/DATABASE.md) — 数据库设计
