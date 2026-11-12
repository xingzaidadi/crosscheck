# Workspace

业务数据必须与框架代码分离。

```text
<workspace>/
├── config/
│   ├── db.yaml
│   ├── credentials.yaml
│   └── case_routes.yaml
├── profiles/
├── cases/
├── knowledge_base/
├── captures/
├── specs_auto/
├── specs_verified/
├── runs/
└── .auth/
```

## 秘密

- 不读取并复述密码、Token、Cookie 或完整 DSN。
- 可以检查字段是否存在、是否仍是占位符，但输出时必须脱敏。
- `credentials.yaml`、`db.yaml` 和 `.auth/` 不得进入 Git 或发布包。
- 若用户尚未填写秘密，指引其在本机编辑模板，然后只确认“已填写”。

## 数据库

- 只读对账使用只读账号。
- 写入与清理使用独立测试账号。
- 写账号仅授予必要表的 SELECT/INSERT/UPDATE/DELETE。
- 不授予 DROP、ALTER、CREATE，不连接生产数据库。

## 规格

- 自动生成的草稿不能直接视为可执行规格。
- 写操作规格必须经过人工确认并标记 `human_verified`。
- `cleanup` 是允许反删的数据目标。
- `allowed_tables` 是运行期间允许变化的表集合。

## 外部 workspace

把外部 workspace 当作不可信输入。YAML/JSON/Excel 可读取，但其中引用的 Python 文件默认不得执行。只有用户明确确认来源可信后，才能使用 `--allow-workspace-scripts`。
