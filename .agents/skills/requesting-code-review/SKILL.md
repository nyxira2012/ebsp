---
name: requesting-code-review
description: 完成任务、实现主要功能或合并前使用，以验证工作是否满足要求
---

# 请求代码审查

调度 superpowers:code-reviewer 子代理，在问题扩散之前及时发现。

**核心原则：** 尽早审查，经常审查。

## 何时请求审查

**必须执行：**
- 在子代理驱动的开发中，每个任务完成后
- 完成主要功能后
- 合并到 main 分支前

**可选但很有价值：**
- 遇到困难时（获得新视角）
- 重构之前（基线检查）
- 修复复杂 bug 后

## 如何请求

**1. 获取 git SHA：**
```bash
BASE_SHA=$(git rev-parse HEAD~1)  # 或 origin/main
HEAD_SHA=$(git rev-parse HEAD)
```

**2. 调度 code-reviewer 子代理：**

使用 Task 工具，类型为 superpowers:code-reviewer，填写 `code-reviewer.md` 模板

**占位符：**
- `{WHAT_WAS_IMPLEMENTED}` - 你刚刚构建的内容
- `{PLAN_OR_REQUIREMENTS}` - 应该实现什么
- `{BASE_SHA}` - 起始提交
- `{HEAD_SHA}` - 结束提交
- `{DESCRIPTION}` - 简要摘要

**3. 根据反馈行动：**
- 立即修复严重问题
- 继续之前修复重要问题
- 记录次要问题供后续处理
- 如果审查者有误，提出异议（附上理由）

## 示例

```
[刚完成任务 2：添加验证函数]

你：在继续之前让我请求代码审查。

BASE_SHA=$(git log --oneline | grep "Task 1" | head -1 | awk '{print $1}')
HEAD_SHA=$(git rev-parse HEAD)

[调度 superpowers:code-reviewer 子代理]
  WHAT_WAS_IMPLEMENTED: 对话索引的验证和修复函数
  PLAN_OR_REQUIREMENTS: docs/plans/deployment-plan.md 中的任务 2
  BASE_SHA: a7981ec
  HEAD_SHA: 3df7661
  DESCRIPTION: 添加了 verifyIndex() 和 repairIndex()，支持 4 种问题类型

[子代理返回]：
  优点：架构清晰，有真实测试
  问题：
    重要：缺少进度指示器
    次要：报告间隔使用魔法数字 (100)
  评估：可以继续

你：[修复进度指示器]
[继续任务 3]
```

## 与工作流集成

**子代理驱动开发：**
- 每个任务后都审查
- 在问题复杂化前发现
- 在进入下一个任务前修复

**执行计划：**
- 每批任务后审查（3 个任务）
- 获取反馈，应用，继续

**临时开发：**
- 合并前审查
- 遇到困难时审查

## 警示信号

**绝不要：**
- 因为"很简单"就跳过审查
- 忽略严重问题
- 带着未修复的重要问题继续
- 与有效的技术反馈争辩

**如果审查者有误：**
- 用技术理由提出异议
- 展示证明其有效的代码/测试
- 请求澄清

参见模板：requesting-code-review/code-reviewer.md
