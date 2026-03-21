# Remix

[English](README.md)

`Remix` 是一个通用的 artifact 重构与合成系统。
它可以面向 skill、协议、模块、功能特性、产品以及复合 bundle 等对象，完成分析、比较、重组与重建。

`Remix` 是一个独立产品。
当重构流程需要自我进化、审计、provenance、verification 或 governed handoff 时，它会集成 `Skill-SE-Kit`，而不是把这些职责直接内嵌到自身里。

## 核心工作流

- 收集 brief 与目标约束
- 采集并归一化 source artifacts
- 并行分析多个来源
- 横向比较优劣势与结构模式
- 综合生成策略方案
- 构建选定的输出 artifact
- 做验证、打包与交接

## 当前实现重点

当前代码主要提供这些能力基础：

- artifact source intake
- planning 与 comparison 支架
- runtime orchestration
- build 与 verification 辅助能力
- 在需要 governed 或自我进化流程时集成 `Skill-SE-Kit`

## 仓库结构

```text
remix/
  README.md
  README.zh-CN.md
  src/remix/
  tests/
  docs/
  examples/
```

## 运行时入口

主运行时入口是 `remix.runtime.RemixRuntime`。

## 快速开始

先安装 `Skill-SE-Kit`，然后运行：

```bash
python3 -m pip install ../skill-se-kit
python3 -m pip install .
python3 -m unittest discover -s tests -p 'test_*.py'
```

## 与其他仓库的关系

- [Skill Evolution Protocol](https://github.com/d-wwei/skill-evolution-protocol)：共享 schema 与互操作合同
- [Skill-SE-Kit](https://github.com/d-wwei/skill-se-kit)：在需要时作为自进化运行时底座
- [Agent Skill Governor](https://github.com/d-wwei/agent-skill-governor)：可调用 Remix 并审查 governed 输出的治理层

