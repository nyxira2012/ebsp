---
name: tester
description: 把项目代码进行测试，修正。在用户需要测试项目时，使用本skill。
---

# 代码测试器

使用多个工具逐一进行测试，并修复出现的问题。

> **平台差异说明**
> - **Mac/Linux**: 使用 `python3` 命令
> - **Windows**: 使用 `python` 命令
> - 以下命令使用 `{{python}}` 占位符，执行时请根据平台替换

## 第一步：类型检查
使用 pyright 进行静态类型检查：


如果发现类型错误，分析错误信息并修复。pyright 会检查 `src/` 目录下的所有代码。

## 第二步：单元测试与集成测试

### 2.1 常规测试
先运行基础测试：
- **Mac/Linux**: `pytest`
- **Windows**: `pytest`

### 2.2 只重测失败的用例
如果出现失败，重新运行失败的测试：
- **Mac/Linux**: `pytest --lf -v --tb=long`
- **Windows**: `pytest --lf -v --tb=long`

### 2.3 详细模式
需要更详细的输出或进入调试：
- **Mac/Linux**: `pytest -v --tb=long -s`
- **Windows**: `pytest -v --tb=long -s`

### 2.4 测试覆盖率
检查测试覆盖率，只在终端显示结果：
- **Mac/Linux**: `pytest --cov=src --cov-report=term-missing`
- **Windows**: `pytest --cov=src --cov-report=term-missing`

## 第三步：模拟工具测试

### 3.1 Boss 挑战模拟器
- **Mac/Linux**: `python3 scripts/sim/sim_challenge_boss.py`
- **Windows**: `python scripts\sim\sim_challenge_boss.py`

### 3.2 攻击表模拟器
- **Mac/Linux**: `python3 scripts/sim/sim_attack_table.py`
- **Windows**: `python scripts\sim\sim_attack_table.py`

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
