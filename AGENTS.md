# httpstat 项目规划

## 1) 项目现状

- 单文件 CLI (`httpstat.py`, ~370 行)，Python >=3.9，版本 2.0.0。
- 打包完全由 `pyproject.toml` 驱动（setuptools），`setup.py` 已删除。
- 构建/发布使用 `uv build` / `uv publish`。
- 测试为 `httpstat_test.sh`（端到端 shell 脚本，依赖外网站点）。

### 已完成的现代化工作
- 去除所有 Python 2 兼容代码，shebang 改为 `#!/usr/bin/env python`。
- 全量 f-string，新式 class 语法，类型标注（`Env` 类 overload、`NoReturn`）。
- 严格布尔解析 `parse_bool()`，替代 `'true' in value.lower()`。
- 临时文件 `try/finally` 统一清理，不再泄漏。
- `quit()` 重命名为 `_exit()` 并标注 `NoReturn`。


## 2) 剩余技术债

### A. 测试可靠性不足（高优先级）
- 仅有 shell E2E，强依赖公网与第三方站点行为，CI/本地结果不稳定。
- 缺少单元测试，核心逻辑（指标换算、区间计算、`parse_bool`）没有稳定回归保障。

### B. Agent 适配能力不足（中高优先级）
- 当前 JSON 输出缺少 schema version、状态码语义、错误结构、上下文元数据。
- 缺少"可机器判断"的 SLO/阈值能力（例如总耗时超阈值即非 0 退出）。
- 输出模式较少，无法直接覆盖 Agent 常见流水线（JSONL、紧凑 JSON、纯错误对象）。


## 3) 下一阶段推进方案

### Phase 1：结构化输出 + SLO（本轮实施）

#### 输出格式
- 新增 `--format`（`-f`）：`pretty | json | jsonl`（默认 `pretty`，兼容现有行为）。
- `HTTPSTAT_METRICS_ONLY` 环境变量保留兼容，等价于 `--format json`。
- JSON v1 schema（最小集，后续通过 schema_version 扩展）：
  ```json
  {
    "schema_version": 1,
    "url": "...",
    "ok": true,
    "exit_code": 0,
    "response": {
      "status_line": "HTTP/2 200",
      "status_code": 200,
      "remote_ip": "...",
      "remote_port": "...",
      "headers": {"Content-Type": "application/json", "Server": "nginx", "...": "..."}
    },
    "timings_ms": {
      "dns": 5,
      "connect": 10,
      "tls": 15,
      "server": 50,
      "transfer": 20,
      "total": 100,
      "namelookup": 5,
      "initial_connect": 15,
      "pretransfer": 30,
      "starttransfer": 80
    },
    "speed": {
      "download_kbs": 1234.5,
      "upload_kbs": 0.0
    },
    "slo": {
      "pass": true,
      "violations": []
    }
  }
  ```

#### SLO 阈值
- 单一参数 `--slo key=value,...`，例如 `--slo total=500,connect=100,ttfb=200`。
- 支持的 key：`total`、`connect`、`ttfb`（starttransfer）、`dns`、`tls`。
- 超阈值时退出码为 `4`，JSON 中 `slo.pass=false`，`slo.violations` 列出超标项。
- pretty 模式下在输出末尾用红色标注超标指标。

#### 颜色控制
- 遵循 `NO_COLOR` 环境变量（https://no-color.org）。设置后禁用所有 ANSI 颜色。
- 不新增 `--no-color` 命令行参数，减少 flag 膨胀。

#### 其他 Agent 友好改进
- 新增 `--save <path>` 将结果写入文件（适合多步 Agent 工作流复用）。
- `--format json` 已天然抑制装饰文本，不另设 `--quiet`。

### Phase 2：Skill 层（进行中）
- `skills/httpstat/SKILL.md`：已完成初版诊断 skill，覆盖自动安装、瓶颈识别、SLO 阈值、curl 转换。
- `skills/httpstat/evals/evals.json`：3 个评估用例，经过两轮迭代验证。
- 待补充：诊断推理输出结构（bottleneck_stage、next_actions）尚未结构化为 JSON，目前以自然语言分析为主。


## 4) 完成标准（Definition of Done）
- `--format json` 输出具备 schema_version=1 的稳定结构，有单元测试锁定。
- `--slo` 阈值判定正确，退出码 `4` 有测试覆盖。
- `NO_COLOR` 正确禁用颜色输出。
- 不破坏现有 `pretty` 模式的默认行为。
