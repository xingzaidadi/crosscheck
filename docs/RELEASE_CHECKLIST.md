# 发布清单

1. 工作树无修改、无未跟踪源码，版本号与 Git tag 一致。
2. `python run_tests.py` 全部通过，关键 UI 用例不得跳过。
3. `python scripts/acceptance_matrix.py` 全部通过。
4. `python -m pytest -q --junitxml=test-results.xml` 全部通过，并归档 JUnit XML。
5. `python scripts/verify_distribution.py` 在干净 venv 完成 wheel 安装、模板资源、doctor、init 和 demo。
6. 复制 `docs/external-acceptance.example.yaml`，填入两个真实系统报告后，通过 `python scripts/external_acceptance.py <manifest>`。
7. 执行 `python scripts/security_check.py`，通过依赖和源码安全扫描。
8. 执行 `crosscheck release --out dist/crosscheck-source.zip`。
9. 核对 ZIP 内 `RELEASE_MANIFEST.json` 的 commit 与 tag。
10. 核对 `crosscheck-source.zip.sha256`，并随包交付兼容矩阵、故障手册和产品说明。
11. 在目标电脑重新执行 `crosscheck doctor` 和 `crosscheck demo`。

CI 还必须通过 `coverage report --fail-under=55`；新增协议或数据库插件必须先通过 `tests/test_plugins.py` 类似的契约测试，再提交真实环境验收证据。内置回归只能标记为 contract/local_e2e，不能替代 external acceptance。当前状态见 `docs/IMPLEMENTATION_STATUS.md`。

CI 还执行 `pip-audit --strict` 和 `bandit -r core adapters db scripts -ll`；本地可运行 `python scripts/security_check.py`。

缺少真实外部系统环境时，第 5 项只能保持“待验收”，不得用本地模拟或编译测试冒充完成。
