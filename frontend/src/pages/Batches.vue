<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref([])
const expanded = ref({})
const details = ref({})
const err = ref('')

async function load() {
  try { rows.value = await api.batches() } catch (e) { err.value = e.message }
}
async function toggle(b) {
  expanded.value[b.id] = !expanded.value[b.id]
  if (expanded.value[b.id] && !details.value[b.id]) {
    try { details.value[b.id] = await api.batchDetail(b.id) } catch (e) { err.value = e.message }
  }
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <p class="msg err" v-if="err">{{ err }}</p>
    <table>
      <thead>
        <tr><th>批次</th><th>业务日</th><th>状态</th><th>笔数</th><th>合计净额</th><th>负向笔数</th><th>负向金额</th><th>钉扎时刻</th><th></th></tr>
      </thead>
      <tbody>
        <template v-for="b in rows" :key="b.id">
          <tr>
            <td>#{{ b.id }}</td>
            <td>{{ b.business_day }}</td>
            <td><span class="tag ok">{{ b.status }}</span></td>
            <td>{{ b.fact_count }}</td>
            <td class="ticket-num">{{ b.total_amount }}</td>
            <td>{{ b.void_net_count }}</td>
            <td>{{ b.void_net_amount }}</td>
            <td>{{ b.sealed_at }}</td>
            <td><button type="button" class="ghost" @click="toggle(b)">{{ expanded[b.id] ? '收起明细' : '批明细快照' }}</button></td>
          </tr>
          <tr v-if="expanded[b.id] && details[b.id]">
            <td colspan="9">
              <p class="msg" v-if="!details[b.id].matches_header" style="color:var(--bad)">
                快照明细之和 {{ details[b.id].snapshot_total }} 与批头 {{ details[b.id].batch.total_amount }} 不一致！
              </p>
              <table>
                <thead><tr><th>序</th><th>事实ID</th><th>券码</th><th>活动</th><th>金额</th><th>状态</th><th>事件</th><th>对冲回链</th></tr></thead>
                <tbody>
                  <tr v-for="r in details[b.id].facts" :key="r.id" :class="{ neg: r.status === 'open_void' }">
                    <td>{{ r.seq }}</td>
                    <td>{{ r.fact_id }}</td>
                    <td>{{ r.coupon_code }}</td>
                    <td>{{ r.campaign_code }}</td>
                    <td>{{ r.amount }}</td>
                    <td><span class="tag" :class="{ bad: r.status === 'open_void' }">{{ r.status }}</span></td>
                    <td>#{{ r.event_id }}</td>
                    <td>{{ r.voided_fact_id ? `对冲事实 #${r.voided_fact_id}` : '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>
