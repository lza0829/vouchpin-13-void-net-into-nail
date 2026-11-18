from __future__ import annotations

# 作废相对钉扎合计的全局互斥策略（settings.key = void_policy）
# never_pin：作废永不进钉——只作废/移除 open 核销事实，钉扎集合只含正向核销
# net_pin  ：净额进钉——钉前同日的作废生成负向事实，与正向核销净额计入批次
VOID_POLICY_NEVER_PIN = "never_pin"
VOID_POLICY_NET_PIN = "net_pin"
VOID_POLICIES = (VOID_POLICY_NEVER_PIN, VOID_POLICY_NET_PIN)
DEFAULT_VOID_POLICY = VOID_POLICY_NEVER_PIN
