<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const preview = ref(null)
const msg = ref('')
const err = ref('')

async function load() {
  err.value = ''
  try { preview.value = await api.preview() } catch (e) { err.value = e.message }
}
async function seal() {
  msg.value = ''; err.value = ''
  try {
    const r = await api.seal({})
    msg.value = `已钉扎批次 #${r.batch_id} · ${r.fact_count} 笔 · 净额合计 ${r.total_amount}`
      + (r.void_net_count ? `（含负向对冲 ${r.void_net_count} 笔 / ${r.void_net_amount}）` : '')
    await load()
  } catch (e) { err.value = e.message }
}
function rowTag(f) {
  if (f.status === 'open_void') return { text: '负向对冲', cls: 'bad' }
  return { text: f.status, cls: 'warn' }
}
onMounted(load)
</script>
<template>
  <div class="panel" v-if="preview">
    <div class="grid">
      <div class="stat"><div class="k">业务日</div><div class="v">{{ preview.business_day }}</div></div>
      <div class="stat"><div class="k">作废策略</div><div class="v" style="font-size:1rem;padding-top:.2rem">{{ preview.void_policy === 'net_pin' ? '净额进钉' : '作废永不进钉' }}</div></div>
      <div class="stat"><div class="k">将钉笔数</div><div class="v ticket">{{ preview.open_count }}</div></div>
      <div class="stat"><div class="k">其中正向</div><div class="v">{{ preview.positive_count }}</div></div>
      <div class="stat" v-if="preview.void_policy === 'net_pin'"><div class="k">负向对冲笔数</div><div class="v">{{ preview.void_net_count }}</div></div>
      <div class="stat" v-if="preview.void_policy === 'net_pin'"><div class="k">负向金额</div><div class="v">{{ preview.void_net_amount }}</div></div>
      <div class="stat"><div class="k">将钉净额合计</div><div class="v ticket">{{ preview.open_total }}</div></div>
      <div class="stat"><div class="k">已钉扎</div><div class="v">{{ preview.already_sealed ? '是' : '否' }}</div></div>
    </div>
    <div class="row">
      <button type="button" @click="seal" :disabled="preview.already_sealed || preview.open_count===0">钉扎本日核销</button>
      <button type="button" class="ghost" @click="load">刷新预览</button>
    </div>
    <p class="msg" v-if="preview.void_policy === 'never_pin'">作废永不进钉：被作废的正向事实已移出 open 集合，下表与合计只含正向核销。</p>
    <p class="msg" v-else>净额进钉：负向对冲行与正向核销按发生顺序同列，净额合计与钉扎后批次一致。</p>
    <p class="msg" v-if="msg">{{ msg }}</p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>
  <div class="panel">
    <table>
      <thead><tr><th>事实ID</th><th>券码</th><th>活动</th><th>金额</th><th>状态</th><th>对冲回链</th></tr></thead>
      <tbody>
        <tr v-for="f in (preview?.facts || [])" :key="f.id" :class="{ neg: f.status === 'open_void' }">
          <td>{{ f.id }}</td>
          <td>{{ f.coupon_code }}</td>
          <td>{{ f.campaign_code }}</td>
          <td>{{ f.amount }}</td>
          <td><span class="tag" :class="rowTag(f).cls">{{ rowTag(f).text }}</span></td>
          <td>{{ f.voided_fact_id ? `对冲事实 #${f.voided_fact_id}` : '—' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
