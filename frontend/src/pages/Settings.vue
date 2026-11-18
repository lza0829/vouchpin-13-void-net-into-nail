<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
const day = ref('')
const policy = ref('never_pin')
const msg = ref('')
const err = ref('')

const POLICIES = [
  { value: 'never_pin', label: '作废永不进钉', tip: '只作废/移除 open 核销事实；钉扎集合与合计只含正向核销；作废事件单独可查' },
  { value: 'net_pin', label: '净额进钉', tip: '钉前同日作废生成负向对冲事实，按净额钉扎；已 sealed 的作废一律拒绝' },
]

async function load() {
  msg.value = ''; err.value = ''
  try {
    const [d, p] = await Promise.all([api.getDay(), api.getVoidPolicy()])
    day.value = d.business_day
    policy.value = p.void_policy
  } catch (e) { err.value = e.message }
}
async function saveDay() {
  msg.value = ''; err.value = ''
  try {
    const r = await api.setDay(day.value)
    msg.value = `业务日已设为 ${r.business_day}`
  } catch (e) { err.value = e.message }
}
async function savePolicy() {
  msg.value = ''; err.value = ''
  try {
    const r = await api.setVoidPolicy(policy.value)
    msg.value = r.changed ? `作废策略已切换为 ${r.void_policy}` : `当前已是该策略：${r.void_policy}`
  } catch (e) {
    err.value = e.message
    // 切换被 409 拒绝时回退选项到服务端真值
    const p = await api.getVoidPolicy()
    policy.value = p.void_policy
  }
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <div class="row">
      <label>业务日 <input v-model="day" placeholder="YYYY-MM-DD" /></label>
      <button type="button" @click="saveDay">保存业务日</button>
    </div>
  </div>
  <div class="panel">
    <h3 style="margin:0 0 .35rem">作废相对钉扎合计（全局互斥，只贯彻一种）</h3>
    <div class="row" style="align-items:flex-start">
      <label v-for="p in POLICIES" :key="p.value" class="policy-card" :class="{ on: policy === p.value }">
        <span class="policy-head">
          <input type="radio" :value="p.value" v-model="policy" name="void_policy" />
          <strong>{{ p.label }}</strong>
        </span>
        <small>{{ p.tip }}</small>
      </label>
    </div>
    <div class="row">
      <button type="button" @click="savePolicy">保存作废策略</button>
    </div>
    <p class="msg" v-if="msg">{{ msg }}</p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>
</template>
