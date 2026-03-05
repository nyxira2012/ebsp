---
name: tester
description: 把项目代码进行测试，修正。在用户需要测试项目时，使用本skill。
---

# 代码测试器

使用多个工具逐一进行测试，并修复出现的问题。

> **虚拟环境说明**
> - 本项目使用虚拟环境 `.venv`
> - **Mac/Linux**: 使用 `.venv/bin/python` 和 `.venv/bin/pytest`
> - **Windows**: 使用 `.venv\Scripts\python.exe` 和 `.venv\Scripts\pytest.exe`

## 第一步：类型检查
使用 pyright 进行静态类型检查：
- **Mac/Linux**: `.venv/bin/pyright`
- **Windows**: `.venv\Scripts\pyright.exe`

如果发现类型错误，分析错误信息并修复。pyright 会检查 `src/` 目录下的所有代码。

## 第二步：单元测试与集成测试

### 2.1 常规测试
先运行基础测试：
- **Mac/Linux**: `.venv/bin/pytest`
- **Windows**: `.venv\Scripts\pytest.exe`

### 2.1.1 只重测失败的用例
如果出现失败，重新运行失败的测试：
- **Mac/Linux**: `.venv/bin/pytest --lf -v --tb=long`
- **Windows**: `.venv\Scripts\pytest.exe --lf -v --tb=long`

### 2.1.2 详细模式
需要更详细的输出或进入调试：
- **Mac/Linux**: `.venv/bin/pytest -v --tb=long -s`
- **Windows**: `.venv\Scripts\pytest.exe -v --tb=long -s`

### 2.2 测试覆盖率
检查测试覆盖率，只在终端显示结果：
- **Mac/Linux**: `.venv/bin/pytest --cov=src --cov-report=term-missing`
- **Windows**: `.venv\Scripts\pytest.exe --cov=src --cov-report=term-missing`

## 第三步：模拟工具测试

### 3.1 Boss 挑战模拟器
- **Mac/Linux**: `.venv/bin/python scripts/sim/sim_challenge_boss.py`
- **Windows**: `.venv\Scripts\python.exe scripts\sim\sim_challenge_boss.py`

### 3.2 攻击表模拟器
- **Mac/Linux**: `.venv/bin/python scripts/sim/sim_attack_table.py`
- **Windows**: `.venv\Scripts\python.exe scripts\sim\sim_attack_table.py`

### 3.3 战斗模拟器
- **Mac/Linux**: `.venv/bin/python scripts/sim/sim_combat.py`
- **Windows**: `.venv\Scripts\python.exe scripts\sim\sim_combat.py`

## 第四步：问题修复原则

当测试失败时，按以下原则处理：

1. **分析错误信息**：仔细阅读错误堆栈和失败原因
2. **定位问题代码**：根据错误信息定位到具体文件和行号
3. **简洁修复**：直接修改问题代码，不要创建复杂封装
4. **重新测试**：运行对应的测试确认问题已解决
5. **回归测试**：确保修复没有引入新的问题

## 最后：打扫卫生

删除`.coverage`、`.pytest_cache/`等临时和缓存文件及文件夹

## 其他注意事项

- pyright 配置文件：`pyrightconfig.json`（只检查 src/，排除 test_*.py）
- pytest 配置文件：`pytest.ini`（已配置 -q --tb=line -rN 等参数，输出简洁）
- 测试文件位于 `tests/` 目录
- 修复问题后运行完整测试套件，避免遗漏
