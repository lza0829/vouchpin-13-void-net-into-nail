<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const rows = ref([])
const camps = ref([])
const policy = ref('')
const form = ref({ event_type: 'redeem', coupon_code: '', campaign_code: 'NEW10', amount: '' })
const msg = ref('')
const err = ref('')

async function load() {
  err.value = ''
  try {
    const [c, ev, p] = await Promise.all([api.campaigns(), api.events(), api.getVoidPolicy()])
    camps.value = c
    rows.value = ev
    policy.value = p.void_policy
    if (!form.value.campaign_code && camps.value[0]) form.value.campaign_code = camps.value[0].code
  } catch (e) { err.value = e.message }
}
async function submit() {
  msg.value = ''; err.value = ''
  try {
    const body = { ...form.value }
    if (body.amount === '') delete body.amount
    else body.amount = Number(body.amount)
    const r = await api.addEvent(body)
    msg.value = `已写入事件 #${r.event_id}` + (r.fact_id ? ` / 事实 #${r.fact_id}` : '')
      + (r.void_policy ? `（策略 ${r.void_policy}${r.voided_fact_id ? `，作用于事实 #${r.voided_fact_id}` : ''}）` : '')
    form.value.coupon_code = ''
    await load()
  } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <div class="row">
      <label>类型
        <select v-model="form.event_type">
          <option value="issue">发放</option>
          <option value="redeem">核销</option>
          <option value="void">作废</option>
        </select>
      </label>
      <label>券码 <input v-model="form.coupon_code" placeholder="C-2xxx" /></label>
      <label>活动
        <select v-model="form.campaign_code">
          <option v-for="c in camps" :key="c.code" :value="c.code">{{ c.code }} · {{ c.title }}</option>
        </select>
      </label>
      <label>金额 <input v-model="form.amount" :placeholder="form.event_type === 'void' ? '作废自动取负原核销额' : '可空=面额'" /></label>
      <button type="button" @click="submit">写入事件</button>
      <button type="button" class="ghost" @click="load">刷新</button>
    </div>
    <p class="msg" v-if="policy">
      当前全局策略：<strong>{{ policy === 'net_pin' ? '净额进钉' : '作废永不进钉' }}</strong>
      <template v-if="policy === 'never_pin'">——作废只把 open 事实置 voided，不产生负向行、不进钉扎合计。</template>
      <template v-else>——钉前同日作废生成负向对冲事实按净额钉；已 sealed 的作废会被拒绝。</template>
    </p>
    <p class="msg" v-if="msg">{{ msg }}</p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>
  <div class="panel">
    <table>
      <thead><tr><th>ID</th><th>类型</th><th>券码</th><th>活动</th><th>金额</th><th>业务日</th><th>时刻</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id" :class="{ neg: r.event_type === 'void' }">
          <td>{{ r.id }}</td>
          <td><span class="tag" :class="{ warn: r.event_type==='redeem', bad: r.event_type==='void' }">{{ r.event_type }}</span></td>
          <td>{{ r.coupon_code }}</td>
          <td>{{ r.campaign_code }}</td>
          <td>{{ r.amount }}</td>
          <td>{{ r.business_day }}</td>
          <td>{{ r.occurred_at }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
