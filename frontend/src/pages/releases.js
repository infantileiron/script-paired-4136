import {state} from '../stores/session.js';
import {esc} from '../utils/html.js';
import {badge} from '../components/common/status.js';
import {field,select} from '../components/common/fields.js';
import {table} from '../components/common/table.js';

const doneEvals=()=>state.evaluations.filter(e=>e.state==='done');
const stateLabel={pending:'待处理',downloadable:'可下载',failed:'失败'};

export function render(){
 const b=state.budget;
 const accounts=b.accounts||[];
 const lowOnBudget=accounts.filter(a=>a.remaining_epsilon<=0).map(a=>a.consultant_code);
 return `<div class="split">
  <section class="panel">
   <h2>匿名发布 · 差分隐私加噪均值 ${badge('epsilon 累计预算')}</h2>
   <p class="notice">对外只发布裁剪均值的拉普拉斯加噪结果与机制参数，不含顾问编号与原始得分；内部原报告仍保留在“效应评估”。每位顾问共享累计 ε 预算，跨组、跨评估发布统一扣账，超额则整次拒绝。</p>
   <h3>顾问隐私预算（上限 ${esc(b.total_epsilon_cap||'')} ε）</h3>
   ${table(['顾问编号','总额 ε','已用 ε','剩余 ε'],accounts.map(a=>[a.consultant_code,a.total_epsilon,Number(a.spent_epsilon).toFixed(4),Number(a.remaining_epsilon).toFixed(4)]))}
   ${lowOnBudget.length?`<p class="error">预算已用尽：${esc(lowOnBudget.join('、'))}，涉及这些顾问的新发布会被整次拒绝。</p>`:''}
   <h3>发布申请状态</h3>
   ${table(['#','名称','评估','状态','名单人数','ε','裁剪界','尝试','更新时间'],(b.releases||[]).map(r=>[
     r.id,r.name,r.evaluation_id,stateLabel[r.state]||r.state,r.roster_size,r.epsilon,
     '['+r.lower+', '+r.upper+']',r.attempts,(r.error?esc(r.error)+' · ':'')+(r.updated||'')
   ]))}
   <div class="release-actions">
    ${(b.releases||[]).map(r=>r.state==='downloadable'
      ?`<button class="primary" data-download="${r.id}">下载 #${r.id} 加噪 JSON</button>`
      :`<button data-retry="${r.id}">重试 #${r.id}（复用噪声不重扣）</button>`).join('')}
   </div>
  </section>
  <aside class="side">
   <h2>新建匿名发布</h2>
   <form id="release">
    ${select('目标评估（需已完成）','evaluation_id',doneEvals().map(e=>[e.id,'#'+e.id+' '+e.name]))}
    ${field('发布名称','name','text','value="对外匿名均值"')}
    ${field('裁剪下界 lower','lower','number','step="0.1" value="-20" required')}
    ${field('裁剪上界 upper','upper','number','step="0.1" value="20" required')}
    ${field('每位顾问 ε（本次）','epsilon','number','step="0.1" min="0.01" value="1" required')}
    <p>固定评估名单取评估冻结快照中的完整配对顾问；差值 d=后测−前测 先裁剪到 [lower, upper] 再求均值。敏感度=(upper−lower)/n，按替换一位顾问口径；噪声尺度 b=敏感度/ε。</p>
    <button class="primary">提交匿名发布</button>
   </form>
   <p><button id="refresh-budget">刷新预算与状态</button></p>
  </aside>
 </div>`;
}
