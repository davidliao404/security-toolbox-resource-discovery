# 安全工具箱互联网暴露面资源发现 PoC

这是“安全工具箱”互联网暴露面资源发现模块的第一版可执行 PoC。当前实现默认使用离线 fixture 数据，验证从资产种子到管理者报告草稿的最小链路，不需要 FOFA 密钥，也不会执行云端主动扫描。

## 当前能力

- 根据根域名、组织名、IP 段生成受控 FOFA 查询计划。
- 从 FOFA-like fixture 数据加载资产发现结果。
- 归一化为资产、暴露服务和来源证据。
- 按 `domain_or_ip + port + protocol + service` 去重。
- 生成远程访问、管理后台、测试环境、数据库暴露和中间件暴露等被动风险线索。
- 生成管理者摘要报告和技术附录数据。

## 本地运行

创建虚拟环境并安装测试依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

如果系统没有可用 `python`，可使用 Codex 工作区自带 Python 路径创建 `.venv`。

运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

运行离线 PoC：

```powershell
.\.venv\Scripts\python.exe -m resource_discovery.cli --seeds examples\seeds.json --fixture tests\fixtures\fofa_results.json
```

命令会向 stdout 输出 JSON，其中包含：

- `report`
- `assets`
- `services`
- `risk_hints`
- `source_evidence`

## 安全边界

当前 PoC 只使用 fixture 数据，不调用真实 FOFA API，不保存 SaaS 密钥，不执行端口扫描、漏洞验证、弱口令验证或渗透测试。所有风险项均为被动发现线索，需要在客户私有化安全工具箱内进行本地验证。
