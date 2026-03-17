# OpenList Skill

面向 AI Agent 的 OpenList 文件管理 skill。

用于在 OpenList 中安全地浏览文件、移动文件、重命名、删除单个路径，以及创建和管理离线下载任务。

可作为 Agent skill 使用，也可直接通过命令行运行。

## 功能

- 路径检查：查看文件或目录是否存在
- 目录浏览：列出指定目录内容
- 文件整理：移动文件、重命名文件或目录
- 删除保护：删除前先预览，再确认执行
- 离线下载：创建、查询、取消离线下载任务
- 审计记录：预览、执行、拒绝、查询都会留下日志

## 特点

- 两步执行：所有写操作都先 `preview-*`，再 `apply`
- 更适合 Agent：先展示要做什么，再真正执行
- 默认更保守：不允许覆盖写入，不支持批量删除
- 可追踪：每次关键操作都会写入审计日志

## 项目结构

```text
skills/
├─ README.md
└─ openlist/
   ├─ SKILL.md
   ├─ scripts/
   │  └─ openlist.py
   └─ tests/
      └─ test_openlist.py
```

## 安装

### Manual

```powershell
git clone <your-repo-url>
```

## 配置

运行前需要设置：

- `OPENLIST_BASE_URL`：OpenList 地址
- `OPENLIST_TOKEN`：OpenList Token

可选项：

- `OPENLIST_TIMEOUT_SECONDS`
- `OPENLIST_VERIFY_TLS`
- `OPENLIST_AUDIT_PATH`

支持从以下位置读取：

- 环境变量
- 仓库根目录 `.env`
- `openlist/.env`

## 使用

脚本入口：

```powershell
python skills/openlist/scripts/openlist.py <command> [options]
```

查看目录：

```powershell
python skills/openlist/scripts/openlist.py fs-list --path "/downloads" --json
```

移动文件：

```powershell
python skills/openlist/scripts/openlist.py preview-move `
  --src-path "/from/report.pdf" `
  --dst-dir "/archive/" `
  --json > move.plan.json

python skills/openlist/scripts/openlist.py apply --plan-file move.plan.json --json
```

重命名：

```powershell
python skills/openlist/scripts/openlist.py preview-rename `
  --path "/archive/report.pdf" `
  --new-name "report-2026.pdf" `
  --json > rename.plan.json

python skills/openlist/scripts/openlist.py apply --plan-file rename.plan.json --json
```

删除：

```powershell
python skills/openlist/scripts/openlist.py preview-delete `
  --path "/archive/report.pdf" `
  --json > delete.plan.json

python skills/openlist/scripts/openlist.py apply --plan-file delete.plan.json --json
```

离线下载：

```powershell
python skills/openlist/scripts/openlist.py preview-offline-create `
  --url "https://example.com/file.iso" `
  --dst-dir "/downloads/" `
  --json > offline.plan.json

python skills/openlist/scripts/openlist.py apply --plan-file offline.plan.json --json
```

查询审计：

```powershell
python skills/openlist/scripts/openlist.py audit-show --plan-id "<plan-id>" --json
```

## 常用命令

- `ping`
- `whoami`
- `fs-get`
- `fs-list`
- `preview-move`
- `preview-rename`
- `preview-delete`
- `preview-offline-create`
- `apply`
- `task-info`
- `task-list`
- `task-cancel`
- `audit-show`

更完整的说明见 [SKILL.md](E:/Project/openlist/skills/openlist/SKILL.md)。

## 安全注意事项

- 删除是不可逆操作
- 删除只支持单个明确路径
- 不允许删除根目录 `/`
- 写操作必须先预览，再执行
- 如果目标状态变化或 plan 不合法，`apply` 会拒绝执行

## 测试

```powershell
python -m unittest skills.openlist.tests.test_openlist
```

## License

MIT
