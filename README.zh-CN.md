# Remix

[English](README.md)

`Remix` 是一个通用的 artifact 重构与合成工具。
它可以分析、比较、重组和重建 skill、协议、模块、功能特性、产品以及复合 bundle。

Remix 是一个**独立工具**。除了 Python 和 jsonschema，没有任何外部依赖。
如果需要自我进化或治理集成，可以安装可选的 `skill-se-kit` 插件。

## 快速开始

```bash
pip install .
```

分析来源（只出评分，不构建）：

```bash
remix analyze \
  --brief '{"target_profile":"skill","target_job":"评估来源质量"}' \
  --sources '[{"kind":"file","path":"./source.md"}]'
```

比较来源（排名 + 策略方案）：

```bash
remix compare \
  --brief '{"target_profile":"skill","target_job":"选出最佳来源"}' \
  --sources '[{"kind":"file","path":"./a.md"},{"kind":"file","path":"./b.md"}]'
```

完整流水线（分析 → 比较 → 构建 → 验证）：

```bash
remix run \
  --brief '{"target_profile":"skill","target_job":"构建一个代码审查 skill"}' \
  --sources '[{"kind":"file","path":"./my-skill.md"}]'
```

查看可用的 target profile：

```bash
remix profiles
```

## 核心工作流

1. **采集** — 收集 brief（目标需求）和 sources（现有素材）
2. **归一化** — 将多种来源格式转换为规范表示
3. **分析** — 对每个来源在可配置的维度上评分（0–5 分制）
4. **比较** — 排名、硬性门禁过滤、发现互补配对
5. **合成** — 生成 2–3 个策略方案（保守加固、平衡合成、前向移植）
6. **构建** — 物化选定的输出 artifact
7. **验证** — 运行 profile 特定的检查
8. **审计与交接** — 生成 provenance 轨迹和发布元数据

## 目标 Profile

| Profile | 输出 | 适用场景 |
|---------|------|----------|
| `skill` | manifest.json, SKILL.md, tests.md | Agent skill |
| `protocol` | schema.json, 示例, 兼容性矩阵 | 互操作协议 |
| `module` | 包结构, 源码, 测试 | 可复用代码包 |
| `feature` | spec, 发布计划, 验收标准 | 产品特性 |
| `product` | PRD, 路线图, 能力地图 | 产品定义 |
| `compound` | 以上 profile 的递归组合 | 多 artifact 系统 |

## 可配置评分

评分维度和权重支持每次运行时通过 brief 配置：

```json
{
  "target_profile": "skill",
  "target_job": "...",
  "scoring_overrides": {
    "task_fit": { "weight": 1.5 },
    "testability": { "weight": 0.5 },
    "custom_dimension": { "weight": 1.0, "score": 4.2 }
  }
}
```

每个 target profile 自带合理的默认权重，只需覆盖你关心的部分。

## 扩展点

| 扩展 | 用途 | 是否必须 |
|------|------|----------|
| `Analyzer` | 替换启发式评分为 LLM 或自定义分析 | 否（默认启发式） |
| `Validator` | 自定义 manifest/proposal 校验 | 否（默认空实现） |
| `EvolutionBackend` | 自我进化经验记录 | 否（默认空实现） |

都是 Python `Protocol` 类，注入即可使用：

```python
from remix import RemixRuntime

runtime = RemixRuntime(
    analyzer=my_llm_analyzer,
    validator=my_validator,
    evolution_backend=my_backend,
)
```

## 可选：Skill-SE-Kit 集成

如果希望 Remix 记录经验并逐渐进化：

```bash
pip install ".[evolution]"
```

```python
from remix import from_skill_runtime

runtime = from_skill_runtime(
    skill_root="/path/to/skill",
    protocol_root="/path/to/protocol",
)
```

这是**可选的**。没有它 Remix 完全可以独立工作。

## 仓库结构

```text
remix/
  SKILL.md           — skill 描述，供 agent 发现
  manifest.json      — 机器可读的 skill 元数据
  README.md
  README.zh-CN.md
  pyproject.toml
  src/remix/         — 核心实现
  tests/             — 测试
```

## 相关项目

- [Skill-SE-Kit](https://github.com/d-wwei/skill-se-kit)：可选的自我进化插件
- [Agent Skill Governor](https://github.com/d-wwei/agent-skill-governor)：可调用 Remix 的治理层
