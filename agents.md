# httpstat 项目分析与下一阶段规划

## 1) 项目全貌（Current Snapshot）

### 仓库结构与形态
- 当前是“单文件 CLI”形态，核心逻辑集中在 `httpstat.py`（约 350 行）。
- 打包使用 `setup.py`，并已补充 `pyproject.toml`（PEP 517 构建入口）。
- 测试是 `httpstat_test.sh`（端到端 shell 脚本，依赖外网站点）。
- `Makefile` 仅提供 `test/build/publish` 的基础命令。

### 当前功能能力
- 核心行为：包装 `curl` 命令，收集 timing metrics 并输出可视化表格。
- 支持若干环境变量控制行为（如 `HTTPSTAT_SHOW_BODY`、`HTTPSTAT_METRICS_ONLY`）。
- 支持 metrics-only JSON 输出（对自动化友好，但语义仍偏“人类调试”）。

### 实测结论
- `--help`、`HTTPSTAT_METRICS_ONLY=true` 基本可用。
- `httpstat_test.sh` 已修复一处脆弱断言并在当前环境通过：
  - 过去的失败点是用例假设响应体“必然截断”，该假设对外站内容不稳定。
  - 已改为稳健断言（验证请求成功；仅在出现截断时再校验 `stored in`）。


## 2) 关键问题与技术债（按影响排序）

### A. 现代化不足（高优先级）
- 仍保留旧时代兼容痕迹（如 `from __future__ import print_function`、`PY3/xrange` 分支）。
- 打包链路停留在 `setup.py`；缺少 `python_requires`、现代构建后端、工具配置集中化。
- 无类型标注、无静态检查、无格式化规范，维护成本随改动指数上升。

### B. 可维护性不足（高优先级）
- `main()` 承担参数解析、执行命令、解析结果、渲染输出等多职责，耦合高。
- 环境变量布尔解析采用 `'true' in value.lower()`，语义宽松，容易误判。
- 错误处理和资源清理路径分散，临时文件生命周期控制可进一步收敛。

### C. 测试可靠性不足（高优先级）
- 仅有 shell E2E，强依赖公网与第三方站点行为，导致 CI/本地结果不稳定。
- 缺少单元测试，核心逻辑（指标换算、区间计算、输出 schema）没有稳定回归保障。

### D. Agent 适配能力不足（中高优先级）
- 当前 JSON 输出缺少 schema version、状态码语义、错误结构、上下文元数据。
- 缺少“可机器判断”的 SLO/阈值能力（例如总耗时超阈值即非 0 退出）。
- 输出模式较少，无法直接覆盖 Agent 常见流水线（JSONL、紧凑 JSON、纯错误对象）。


## 3) 下一阶段推进方案

## 3.1 Modernize（现代化）

### (a) Python 版本策略（去旧迎新）
- 建议最低支持版本提升到 `Python >=3.9`（可选 `>=3.10`，但需评估用户面）。
- 移除旧兼容代码（`__future__`、`PY3/xrange` 等）。
- 在打包配置中显式声明 `python_requires` 与 classifiers。

### (b) Simplify（简化代码）
- 将 `main()` 拆分为明确边界的函数：
  - `parse_args_and_env()`
  - `build_curl_command()`
  - `run_curl()`
  - `parse_metrics()`
  - `render_output()`
- 将“数据计算”与“终端渲染”分离：先得到统一 `ResultModel`，再决定输出形式。
- 引入最小必要类型标注，优先覆盖核心数据结构与函数签名。

### (c) 去冗余与不合理设计（保持功能不变）
- 统一布尔解析函数（严格支持：`1/0 true/false yes/no on/off`）。
- 收敛临时文件处理与清理逻辑（`try/finally` 或上下文管理）。
- 统一错误出口与退出码规范，避免分散 `quit()` 分支造成行为漂移。


## 3.2 增强 Agent 适配性（新功能建议）

### 输出与协议
- 新增 `--output`：`pretty | json | jsonl`（默认 `pretty`，兼容现有行为）。
- JSON 输出增加：
  - `schema_version`
  - `ok` / `exit_code`
  - `request`（url、method、curl_args 摘要）
  - `response`（status_line、remote/local endpoint）
  - `timings_ms`（原子指标 + range 指标）
  - `diagnostics`（stderr 摘要、重试信息、debug 元数据）

### 可判定调试能力
- 新增阈值参数：
  - `--max-total-ms`
  - `--max-connect-ms`
  - `--max-ttfb-ms`
- 当超阈值时返回专用退出码（例如 `4`），并在 JSON 中标记 `slo_pass=false`。

### Agent 流水线易用性
- 新增 `--quiet`（仅输出结构化结果，禁用装饰文本）。
- 新增 `--no-color`（覆盖 tty 自动判断，便于日志采集）。
- 新增 `--save <path>` 将结果写入文件（适合多步 Agent 工作流复用）。


## 3.3 扩展 Skills（提供 Skill 接口）

目标：让 Agent 通过标准 Skill 快速调用 httpstat 做网站访问诊断，避免每次重复拼装命令与解释指标。

### 建议 Skill 形态
- Skill 名称建议：`httpstat-network-debug`
- 目录建议：`<repo>/skills/httpstat-network-debug/`
- 组成建议：
  - `SKILL.md`：触发条件、工作流、输出约定、失败处理。
  - `scripts/run_httpstat.sh`：统一调用入口（默认 JSON 输出 + 稳定参数）。
  - `references/metrics.md`：指标释义、常见瓶颈模式、诊断建议模板。

### Skill 接口约定（建议）
- 输入参数（最小集）：
  - `url`（必填）
  - `method`（可选）
  - `headers`（可选）
  - `data`（可选）
  - `budget_ms`（可选）
- 输出对象（JSON）：
  - `summary`（一句话诊断）
  - `bottleneck_stage`（dns/connect/tls/server/transfer）
  - `metrics`（完整 timings）
  - `slo_pass`
  - `next_actions`（可执行建议列表）

### Skill 使用收益
- Agent 可稳定复用同一“调用模板 + 诊断模板”。
- 结果可直接进入后续任务（告警、报告、回归对比）。
- 降低不同 Agent/不同人手工解读偏差。


## 4) 推荐实施节奏（4 个迭代）

### Iteration 1（地基）
- 引入 `pyproject.toml`，保留兼容入口；声明 `python_requires`。
- 去除旧兼容代码；不改变 CLI 行为。
- 把 shell E2E 中不稳定断言改为稳健条件。

### Iteration 2（重构）
- 拆分 `main()` 职责，建立 `ResultModel`。
- 增加单元测试（指标换算、区间计算、布尔解析、退出码）。

### Iteration 3（Agent 能力）
- 增加 `--output`、`--quiet`、阈值参数与标准化 JSON schema。
- 增加结构化错误输出与退出码约定。

### Iteration 4（Skill 落地）
- 创建 `httpstat-network-debug` Skill（SKILL + script + reference）。
- 用真实站点样例验证“触发 -> 调用 -> 诊断 -> 建议”完整链路。


## 5) 完成标准（Definition of Done）
- 在声明的最低 Python 版本上测试全部通过。
- 结构化输出具备稳定 schema，并有测试锁定。
- 网络波动不再导致核心回归测试频繁误报。
- Agent 通过 Skill 可在单次调用中得到“可判定 + 可执行”的诊断结果。
