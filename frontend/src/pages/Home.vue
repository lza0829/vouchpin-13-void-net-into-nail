<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const d = ref(null)
const err = ref('')
async function load() {
  err.value = ''
  try { d.value = await api.dashboard() } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <div class="grid" v-if="d">
      <div class="stat"><div class="k">业务日</div><div class="v">{{ d.business_day }}</div></div>
      <div class="stat"><div class="k">作废策略</div><div class="v" style="font-size:1rem;padding-top:.2rem">{{ d.void_policy === 'net_pin' ? '净额进钉' : '作废永不进钉' }}</div></div>
      <div class="stat"><div class="k">今日事件</div><div class="v">{{ d.event_count }}</div></div>
      <div class="stat"><div class="k">其中作废事件</div><div class="v">{{ d.void_event_count }}</div></div>
      <div class="stat"><div class="k">待钉 open</div><div class="v">{{ d.open_fact_count }}</div></div>
      <div class="stat"><div class="k">已作废事实</div><div class="v">{{ d.voided_fact_count }}</div></div>
      <div class="stat"><div class="k">待钉负向行</div><div class="v">{{ d.open_void_fact_count }}</div></div>
      <div class="stat"><div class="k">核销毛额</div><div class="v ticket">{{ d.redeem_gross_today }}</div></div>
      <div class="stat"><div class="k">作废额（负）</div><div class="v">{{ d.void_amount_today }}</div></div>
      <div class="stat"><div class="k">核销净额</div><div class="v ticket">{{ d.redeem_net_today }}</div></div>
      <div class="stat"><div class="k">日已钉扎</div><div class="v">{{ d.day_sealed ? '是' : '否' }}</div></div>
    </div>
    <p class="msg" v-if="!err">
      作废事件始终入湖可查、不物理删除；{{ d?.void_policy === 'net_pin'
        ? '净额进钉下负向对冲行随批次净额钉扎，sealed 后作废一律拒绝。'
        : '永不进钉下作废只置 voided，钉扎合计只含正向核销。' }}
    </p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>
</template>
