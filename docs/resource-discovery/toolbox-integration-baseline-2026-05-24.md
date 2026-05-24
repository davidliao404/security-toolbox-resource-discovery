# 工具箱联调基线 - 2026-05-24

## 1. 基线范围

本文给安全工具箱团队作为资源发现网关 FastAPI 联调的固定参照。

- 分支：`master`
- 提交：`25522a2 fix: harden gateway quality gates`
- API 契约：`docs/resource-discovery/toolbox-api-contract.md`
- 交接说明：`docs/resource-discovery/toolbox-handoff.md`
- 生产就绪记录：`docs/resource-discovery/production-readiness-checklist.md`

本基线用于工具箱侧适配接口、签名、分页、状态处理和错误处理。它不是生产上线声明；生产运维能力仍按 `docs/superpowers/plans/2026-05-24-production-operations-hardening.md` 推进。

## 2. 工具箱必须遵守的签名规则

每个请求必须发送以下请求头：

- `X-Tenant-Id`
- `X-Client-Id`
- `X-Timestamp`
- `X-Nonce`
- `X-Signature`

签名算法为 HMAC-SHA256。canonical request 按以下顺序拼接：

```text
METHOD
PATH_WITH_QUERY
TIMESTAMP
NONCE
SHA256_BODY_HEX
```

关键约束：

- `METHOD` 使用大写 HTTP 方法。
- `PATH_WITH_QUERY` 只包含路径和查询串，不包含协议、域名和端口。
- GET 查询参数必须按实际发送的 path+query 参与签名。
- POST 请求体签名使用实际发送的原始字节。
- `X-Nonce` 在有效窗口内只能使用一次，重放请求会被拒绝。
- 已认证租户必须匹配当前 scope profile 租户。

结果分页请求示例：

```text
GET
/api/v1/discovery/tasks/dt_20260524_000001/results?result_type=assets&limit=100
2026-05-24T10:00:00+08:00
nonce-20260524-000001
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

## 3. 联调调用顺序

1. `GET /api/v1/discovery/scope-profile`
2. `POST /api/v1/discovery/tasks`
3. `GET /api/v1/discovery/tasks/{task_id}`
4. `GET /api/v1/discovery/tasks/{task_id}/results?result_type=assets&limit=100`
5. `GET /api/v1/discovery/tasks/{task_id}/results?result_type=services&limit=100`
6. `GET /api/v1/discovery/tasks/{task_id}/results?result_type=source_evidence&limit=100`

工具箱轮询状态时应处理：

- `queued`：继续轮询。
- `running`：继续轮询。
- `retrying`：继续轮询，并展示供应商暂时失败或限速提示。
- `success`：分页拉取结果。
- `partial_success`：分页拉取已有结果，并展示失败来源。
- `failed`：展示错误，允许用户重新创建任务。
- `cancelled`：停止轮询。

## 4. 工具箱侧责任

- 不允许用户输入或透传 FOFA 原生查询语句。
- 只能提交结构化 `requested_scope`，并且只能缩小后台授权范围。
- 每次创建任务都必须使用最新 `scope-profile` 返回的 `profile_id`。
- 结果需要长期保存时写入工具箱本地资产库；网关只提供短期任务结果缓存。
- `freshness.stale` 表示外部测绘情报较旧，不代表资产已经下线。
- 不保存 FOFA API Key、供应商配置、签名密钥、完整认证头或未脱敏个人资料。

## 5. 本地质量基线

Windows 验证：

- `.\.venv\Scripts\python.exe -m pytest -q`
- `271 passed, 4 skipped in 4.21s`
- `.\.venv\Scripts\python.exe -m coverage run -m pytest -q`
- `271 passed, 4 skipped in 5.86s`
- `.\.venv\Scripts\python.exe -m coverage report`
- `TOTAL 2482 stmts, 45 miss, 98.19%`

WSL + 真实 PostgreSQL/Redis 验证：

- `RESOURCE_DISCOVERY_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/resource_discovery RESOURCE_DISCOVERY_TEST_REDIS_URL=redis://localhost:6379/0 python -m pytest tests/test_postgres_store.py tests/test_redis_queue.py tests/test_worker_retry.py -q -rs`
- `27 passed in 1.23s`
- `RESOURCE_DISCOVERY_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/resource_discovery RESOURCE_DISCOVERY_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/resource_discovery RESOURCE_DISCOVERY_TEST_REDIS_URL=redis://localhost:6379/0 python -m pytest -q`
- `275 passed in 4.76s`

远端 CI：

- 提交 `25522a2` 已触发 `CI #43` 和 `production-like-gateway #7`。
- 当前本地环境不能可靠读取最终状态，工具箱联调前应在 GitHub Actions 页面确认两个 workflow 均为绿色。

## 6. 本基线不包含

- 云端主动扫描。
- 漏洞验证、弱口令验证或攻击链验证。
- 长期资产库。
- 客户端密钥轮换后台。
- 租户日配额、月配额和供应商集中限速。
- 生产集中审计检索、告警和租户级留存策略。
