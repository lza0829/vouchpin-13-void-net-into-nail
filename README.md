# Vouchpin（券钉簿）

券事件入湖 → 核销事实钉扎 → 批次互证。

## 作废（void）相对钉扎合计的全局互斥策略

系统通过 `settings.void_policy` 在两套互斥语义中二选一，**全链路（作废入口 / open 集合 / 预览 / 批头 / 批明细快照 / 事件湖）同源贯彻，运行时只生效一种**：

- `never_pin`（默认，**作废永不进钉**）
  - 作废只把正向 open 核销事实置为 `voided`（回链作废事件，不物理删除），不产生负向事实；
  - 钉扎集合与批次 `total_amount` 只含正向核销，预览 open 随作废减少且不含负向行；
  - 作废事件以负金额单独留在事件湖，可查但不进 sealed 合计。
- `net_pin`（**净额进钉**）
  - 钉前同日「先核销后作废」时，作废另写一条同额负向事实（`open_void`，回链被对冲的正向事实）；
  - 钉扎合计按净额计入，批头快照 `void_net_count` / `void_net_amount`，批明细正负成对可看对冲；
  - 预览合计与将钉合计严格一致（同一 `pin_candidates` 口径）。

共同铁律：

- 已 sealed 后的作废**一律拒绝（409）**，不得改该批净额，也不落其它业务日；
- 任何策略都**不物理删除**作废事件或事实；
- 存在待钉（open/open_void）事实时禁止切换策略，避免同一批行串口径。

## 接口

- `GET/PUT /api/settings/void-policy`：查看/切换全局策略（body `{"void_policy":"never_pin|net_pin"}`）
- `GET /api/redeem/preview`：待钉集合预览（含 `void_policy`、`void_net_*`、`positive_count`）
- `POST /api/redeem/seal`：钉扎，返回值与预览合计一致
- `GET /api/batches` / `GET /api/batches/{id}`：批头（含净额字段）与批明细快照（`matches_header` 自洽校验）
- `POST /api/events`：`issue` / `redeem` / `void`；void 金额自动取负的原核销额

## 本地运行

- API: `cd backend && python -m uvicorn app.main:app --port 10800`
- Web: `cd frontend && npm install && npm run dev`（5800）

## 测试

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/ -v
```

覆盖两策略 × 三场景（核销后作废再钉 / 钉后再作废 / 作废后预览）、策略切换护栏、
无物理删除、预览与批头/快照同源一致、v1→v2 SQLite 迁移。

端到端冒烟（需先起服务）：

```bash
SMOKE_BASE=http://localhost:10800/api python -I scripts/smoke.py
```
