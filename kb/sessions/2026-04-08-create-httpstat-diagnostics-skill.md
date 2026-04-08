---
created: 2026-04-08
tags:
  - skill
  - diagnostics
  - agent
---

# 为 httpstat 创建 HTTP 性能诊断 Skill

## 概要

本次 session 为 httpstat 项目创建了 Phase 2 规划中的 Skill 层——一个面向 AI Agent 的 HTTP 性能诊断技能。Skill 指导 Agent 自动安装 httpstat、运行结构化诊断、识别瓶颈阶段（DNS/TCP/TLS/Server/Transfer）并给出修复建议。通过 skill-creator 工具进行了两轮迭代评估：第一轮在 httpstat 项目目录中运行（baseline 也能发现 httpstat.py 导致差异不明显），第二轮在干净目录中运行（baseline 只能用 raw curl -w，skill 引导 Agent 自动 pip install httpstat），最终 with-skill pass rate 91.7% vs baseline 78.3%，验证了 skill 的价值。

## 修改的文件

- `skills/httpstat/SKILL.md`：新建，httpstat 诊断 skill 主文件，包含 setup（自动安装）、运行方式、JSON 输出解读、5 类瓶颈诊断指南、诊断工作流、curl 命令转换、SLO 参考
- `skills/httpstat/evals/evals.json`：新建，3 个评估用例（慢 API 诊断、curl 命令调试、TLS 开销对比）
- `AGENTS.md`：修正 JSON schema 中 headers 字段从 text 改为 dict 示例

## Git 提交记录

- `b525ca5` feat: add httpstat diagnostics skill for HTTP performance debugging

## 注意事项

- **Skill 不依赖项目目录**：skill 使用 `which httpstat || pip install httpstat` 模式，确保在任何目录下都能工作，不假设 httpstat.py 在当前目录
- **评估环境隔离很重要**：第一轮在项目目录中运行时 baseline 也能发现 httpstat.py，导致 pass rate 无差异（均 91.7%）；第二轮在 /tmp 干净目录中运行才体现出 skill 的真正价值
- **测试污染问题**：并行运行 with-skill 和 baseline 时，with-skill agent 先 pip install 了 httpstat 到全局 PATH，后续 baseline agent 也能用到。理想情况下应使用独立虚拟环境
- **redirect 断言两组都未通过**：eval 2 中"HTTP 是否提到可能重定向到 HTTPS"这一断言对两组都失败，属于非区分性断言，可考虑在后续迭代中移除或改进 skill 中相关指导
