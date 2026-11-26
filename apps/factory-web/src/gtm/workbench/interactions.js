
const pageTitles={chat:'新建对话',daily:'每日重点工作','key-model':'重点产品表现','own-monitor':'我品价格巡检','rival-monitor':'竞品价格监控',launch:'竞品上新提醒',competitor:'竞品洞察分析',premium:'品牌溢价分析','todo-center':'待办任务中心',reports:'订阅报告',history:'历史记录',help:'帮助中心'};
/* ANALYSIS_NAV_JS_V1 */
let lastPage='daily';
function goPage(name,el,ev){if(ev)ev.stopPropagation();const cur=document.querySelector('.page.active');if(cur){var curId=cur.id.replace('page-','');if(curId!==name&&name==='help')lastPage=curId;}document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));const page=document.getElementById('page-'+name);if(page)page.classList.add('active');document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));const nav=document.querySelector('[data-page="'+name+'"]');if(nav)nav.classList.add('active');const parent=document.getElementById('analysisParent');if(parent)parent.classList.toggle('section-active',name==='competitor');document.getElementById('crumbTitle').textContent=pageTitles[name]||name;document.querySelector('.workspace').scrollTop=0;if(name==='daily'){setTimeout(function(){if(dmChart)dmChart.resize();if(dailyTrendChart)dailyTrendChart.resize();},50);}}
function goBackFromHelp(){goPage(lastPage);}
function scrollHelp(id){var el=document.getElementById(id);if(el){var ws=document.querySelector('.workspace');var top=el.offsetTop - 20;ws.scrollTo({top:top,behavior:'smooth'});}document.querySelectorAll('.help-nav-item').forEach(function(a){a.classList.toggle('active',a.getAttribute('href')==='#'+id);});return false;}
function togglePrice(el){el.classList.toggle('open');document.getElementById('priceSub').classList.toggle('open')}
function openCompetitor(el,ev){
 if(ev)ev.stopPropagation();document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));document.getElementById('page-competitor').classList.add('active');document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));(el||document.querySelector('[data-page=competitor]')).classList.add('active');
 document.querySelectorAll('#analysisTabs .tab').forEach(t=>t.classList.toggle('active',t.dataset.target==='product'));document.querySelectorAll('#page-competitor .tab-panel').forEach(x=>x.classList.remove('active'));document.getElementById('panel-product').classList.add('active');syncAnalysisScope('product');document.getElementById('crumbTitle').textContent='竞品分析';document.querySelector('.workspace').scrollTop=0;
}
function openPremium(el,ev){
 if(ev)ev.stopPropagation();document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));document.getElementById('page-competitor').classList.add('active');document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));(el||document.querySelector('[data-page=premium]')).classList.add('active');document.querySelectorAll('#page-competitor .tab-panel').forEach(x=>x.classList.remove('active'));document.getElementById('panel-premium').classList.add('active');syncAnalysisScope('premium');document.getElementById('crumbTitle').textContent='品牌溢价分析';document.querySelector('.workspace').scrollTop=0;
}
function syncAnalysisScope(target){
 const premium=target==='premium',productScope=document.getElementById('productScope'),brandScope=document.getElementById('brandScope'),tabs=document.getElementById('analysisTabs');
 if(productScope)productScope.style.display=premium?'none':'block';if(brandScope)brandScope.classList.toggle('show',premium);if(tabs)tabs.style.display=premium?'none':'flex';
 const title=document.getElementById('analysisTitle'),subtitle=document.getElementById('analysisSubtitle'),period=document.getElementById('analysisPeriod'),label=document.getElementById('generateBtnLabel');
 if(title)title.textContent=premium?'品牌溢价分析':'竞品分析';if(subtitle)subtitle.textContent=premium?'查看品牌整体分规格表现、VOC驱动因素及相对行业的溢价水平':'按型号比较产品、卖点和量价表现';if(period){period.style.display=premium?'none':'block';period.value='30d';if(document.getElementById('analysisDateRange'))document.getElementById('analysisDateRange').style.display='none'}if(label)label.textContent=analysisReportName(target);
}
function analysisReportName(target){return '生成分析报告';}
document.querySelectorAll('.tabs').forEach(group=>group.addEventListener('click',e=>{const tab=e.target.closest('.tab');if(!tab)return;group.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));tab.classList.add('active');document.querySelectorAll('.tab-panel').forEach(x=>x.classList.remove('active'));document.getElementById('panel-'+tab.dataset.target).classList.add('active');if(group.dataset.group==='analysis')syncAnalysisScope(tab.dataset.target)}));
document.querySelectorAll('.subtabs').forEach(group=>group.addEventListener('click',e=>{const tab=e.target.closest('.subtab');if(!tab)return;group.querySelectorAll('.subtab').forEach(x=>x.classList.remove('active'));tab.classList.add('active');const prefix=group.dataset.subgroup;document.querySelectorAll('#page-'+(prefix==='monitor'?'monitor':'reports')+' .subpanel').forEach(x=>x.classList.remove('active'));document.getElementById('sub-'+tab.dataset.subtarget).classList.add('active')}));
function toggleModel(el){el.classList.toggle('off')}
function openModal(id){document.getElementById(id).classList.add('show')}
function closeModal(id){document.getElementById(id).classList.remove('show')}
function toggleCustomCombobox(){var list=document.getElementById('customComboboxList');if(list.style.display==='block'){list.style.display='none'}else{filterCustomCombobox(document.getElementById('customModel').value)}}
function filterCustomCombobox(keyword){var list=document.getElementById('customComboboxList');var items=list.querySelectorAll('.custom-combobox-item');var kw=(keyword||'').trim().toLowerCase();var hasMatch=false;items.forEach(function(item){var val=item.getAttribute('data-value').toLowerCase();if(val.indexOf(kw)!==-1){item.style.display='block';hasMatch=true}else{item.style.display='none'}});if(!hasMatch){if(!list.querySelector('.custom-combobox-empty')){var empty=document.createElement('div');empty.className='custom-combobox-empty';empty.textContent='暂无匹配型号';list.appendChild(empty)}}else{var empty=list.querySelector('.custom-combobox-empty');if(empty)empty.remove()}
list.style.display='block'}
function selectCustomModel(item){var input=document.getElementById('customModel');input.value=item.getAttribute('data-value');document.getElementById('customComboboxList').style.display='none';input.focus()}
document.addEventListener('click',function(e){var combo=document.querySelector('.custom-combobox');if(combo&&!combo.contains(e.target)){document.getElementById('customComboboxList').style.display='none'}});
function addCompetitor(){const name=document.getElementById('customModel').value;if(!name.trim()){showToast('请输入型号');return;}const add=document.querySelector('.model-tag.add');const tag=document.createElement('span');tag.className='model-tag';tag.innerHTML=escapeSampleText(name)+' <b class="x">×</b>';tag.onclick=()=>toggleModel(tag);add.before(tag);closeModal('competitorModal');showToast('已添加 '+name)}
function simulateParamUpload(name){if(!name)return;document.getElementById('paramUploadedFileName').textContent=name;document.getElementById('paramUploadSection').style.display='none';document.getElementById('paramUploadedSection').style.display='block';showToast(name+' 上传成功')}
function removeUploadedParamFile(){document.getElementById('paramUploadedSection').style.display='none';document.getElementById('paramUploadSection').style.display='block';document.getElementById('paramFileInput').value='';showToast('已删除')}
function confirmParamUpload(){var uploaded=document.getElementById('paramUploadedSection').style.display==='block';var fileName=uploaded?document.getElementById('paramUploadedFileName').textContent:'我品参数.xlsx';document.getElementById('ownParamsFileName').textContent=fileName;document.getElementById('ownParamsFileTag').style.display='inline-flex';document.getElementById('ownParamsBtn').style.display='none';closeModal('ownParamsModal');showToast('参数已确认并同步至分析模型')}
function removeOwnParamsFile(e){e.stopPropagation();document.getElementById('ownParamsFileTag').style.display='none';document.getElementById('ownParamsBtn').style.display='inline-flex';document.getElementById('paramUploadSection')&&(document.getElementById('paramUploadSection').style.display='block');document.getElementById('paramUploadedSection')&&(document.getElementById('paramUploadedSection').style.display='none');showToast('已移除参数文件')}
function onAnalysisPeriodChange(val){document.getElementById('analysisDateRange').style.display = val==='custom'?'':'none'}
function refreshCompetitors(){showToast('AI已重新筛选3个高匹配竞品')}
function generateReport(){const b=document.getElementById('generateBtn'),l=document.getElementById('generateLoading');var name=(document.getElementById('generateBtnLabel').textContent||'生成竞品分析报告').replace(/^生成/,'');b.disabled=true;b.style.opacity='.6';l.classList.add('show');setTimeout(()=>{b.disabled=false;b.style.opacity='1';l.classList.remove('show');showToast(name+'已生成')},1100)}
let currentOwnEvidence={};
function showPriceLines(id, note) {
  const target = document.getElementById(id);
  const parts = (note || '').split(/\s*·\s*|\n/).map(part => part.trim()).filter(Boolean);
  target.replaceChildren();
  if (!parts.length) {
    target.textContent = '暂无价格明细';
    return;
  }
  const list = document.createElement('dl');
  for (const part of parts) {
    const match = part.match(/^(.+?)\s*([+-]?[¥￥]\s*[\d,.]+(?:元)?)$/);
    const row = document.createElement('div'), label = document.createElement('dt');
    label.textContent = match ? match[1].trim() : part;
    row.append(label);
    if (match) {
      const amount = document.createElement('dd');
      amount.textContent = match[2];
      row.append(amount);
    }
    list.append(row);
  }
  target.append(list);
}
function showSeverity(id, level) {
  const status = document.getElementById(id);
  status.textContent = level || '';
  status.dataset.level = level || '';
}
function openEvidence(model,channel,gap,shop,price,baseline,meta,level){
  var d;
  if(typeof model==='object' && model!==null){
    // 对象调用：首页/百科等 x.lv x.m x.ch x.cur x.base x.gap
    var x=model;
    d={model:x.m||'',channel:x.ch||'',gap:x.gap||'',shop:'',price:x.cur||'',baseline:x.base||'',meta:x.meta||'',level:x.lv||'严重',shot:x.shot||'',cl:x.cl||'当前到手价',bl:x.bl||'月度底价'};
  }else if(model===undefined){
    d={model:'65E55N',channel:'拼多多',gap:'-12.1%',shop:'品牌官方店',price:'¥2,899',baseline:'¥3,299',meta:'SKU链接已存档 · 抓取时间 2026-09-11 09:18:22',level:'严重',shot:'页面价¥3,299 · 百亿补贴-¥400 · 到手价¥2,899',cl:'当前到手价',bl:'月度底价'};
  }else{
    d={model:model||'',channel:channel||'',gap:gap||'',shop:shop||'',price:price||'',baseline:baseline||'',meta:meta||'',level:level||'严重',shot:'',cl:'当前到手价',bl:'月度底价'};
  }
  currentOwnEvidence=d;
  // 标题
  showSeverity('evidenceLevel', d.level);
  // 型号 + 渠道
  document.getElementById('evidenceProduct').textContent=d.model;
  document.getElementById('evidenceChannel').textContent=d.channel + (d.shop?' · '+d.shop:'');
  // 三个指标卡
  document.getElementById('evidenceCurrentLabel').textContent=d.cl;
  document.getElementById('evidenceBaselineLabel').textContent=d.bl;
  document.getElementById('evidenceCurrent').textContent=d.price;
  document.getElementById('evidenceBaseline').textContent=d.baseline;
  document.getElementById('evidenceGap').textContent=d.gap;
  // 异常幅度红色高亮
  var gapEl=document.getElementById('evidenceGap');
  if(gapEl){
    gapEl.style.color='';
    if(d.gap && d.gap.indexOf('-')>-1) gapEl.style.color='#E5484D';
  }
  // 页面与数据证据 meta
  var metaEl=document.getElementById('evidenceMeta');
  if(metaEl){
    if(d.meta) metaEl.textContent=d.meta;
    else metaEl.textContent=d.shop||d.channel||'';
  }
  // 存证区域
  showPriceLines('evidenceSnapshot',d.shot);
  openModal('evidenceModal');
}
function aiAskOwnPrice(){
  var d=currentOwnEvidence;
  if(!d||!d.model) return;
  closeModal('evidenceModal');
  var q='请分析'+d.model+'在'+d.channel+'渠道价格异常的原因及处理建议';
  askQ(q);
}
// ALERT_CENTER_RESTRUCTURE_V9
function ignoreAlert(btn){var row=btn.closest('tr'),state=row.querySelector('.alert-status-cell .pill');state.textContent='已忽略';state.className='pill gray';row.classList.add('alert-ignored');btn.disabled=true;showToast('该条预警已忽略，可在操作日志中恢复')}
function handleAlert(btn){btn.textContent='已处理';btn.className='btn sm';const row=btn.closest('tr');const state=row.cells[6].querySelector('.pill');state.textContent='已处理';state.className='pill green';showToast('预警已闭环并自动归档')}
function alertRowChecks(){return Array.from(document.querySelectorAll('.alert-row-check'))}
function updateAlertSelection(){const checks=alertRowChecks();const checked=checks.filter(c=>c.checked);const btn=document.getElementById('genNoticeBtn');if(checked.length>0){btn.disabled=false;btn.classList.add('success')}else{btn.disabled=true;btn.classList.remove('success')}const all=document.getElementById('alertCheckAll');if(all){all.checked=checked.length===checks.length&&checks.length>0;all.indeterminate=checked.length>0&&checked.length<checks.length}}
function toggleAllAlerts(box){alertRowChecks().forEach(c=>c.checked=box.checked);box.indeterminate=false;updateAlertSelection()}
const notifyCandidates=window.gtmRecords.notifyCandidates;
let notifySelected=[];
function openNotifyModal(){const n=alertRowChecks().filter(c=>c.checked).length;if(n===0){showToast('请先勾选需要下发的预警');return}document.getElementById('notifyAlertCount').textContent=n;notifySelected=[];document.getElementById('notifySearchInput').value='';renderNotifyPicked();document.getElementById('notifySuggest').classList.remove('show');openModal('notifyModal')}
function renderNotifyPicked(){const box=document.getElementById('notifyPicked');box.innerHTML=notifySelected.map(v=>'<span class="notify-tag">'+v+'<span class="tag-x" onclick="removeNotify(\''+v+'\')">×</span></span>').join('')}
function removeNotify(v){notifySelected=notifySelected.filter(x=>x!==v);renderNotifyPicked();const inp=document.getElementById('notifySearchInput');filterNotifyOptions(inp.value)}
function filterNotifyOptions(kw){const box=document.getElementById('notifySuggest');kw=(kw||'').trim().toLowerCase();const list=notifyCandidates.filter(c=>c.name.toLowerCase().includes(kw)||c.type.toLowerCase().includes(kw));if(list.length===0){box.innerHTML='<div class="notify-suggest-empty">无匹配的群组或人员</div>'}else{box.innerHTML=list.map(c=>{const on=notifySelected.includes(c.name);return'<div class="notify-suggest-item'+(on?' picked':'')+'" onclick="'+(on?'':'pickNotify(\''+c.name+'\')')+'">'+c.name+'<span class="si-type">'+c.type+(on?' · 已选':'')+'</span></div>'}).join('')}box.classList.add('show')}
function pickNotify(v){if(!notifySelected.includes(v))notifySelected.push(v);renderNotifyPicked();const inp=document.getElementById('notifySearchInput');inp.value='';filterNotifyOptions('');inp.focus()}
function sendNotice(){if(notifySelected.length===0){showToast('请至少选择一个群组或人员');return}const n=alertRowChecks().filter(c=>c.checked).length;closeModal('notifyModal');showToast('整改通知单已发送给 '+notifySelected.join('、')+'（'+n+'条预警）')}
let toastTimer;function showToast(msg){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('show'),2200)}

/* 待办任务操作 */
function markTodoDone(btn){
  var tr=btn.closest('tr');
  if(tr.dataset.done==='1')return;
  tr.dataset.done='1';
  var statusCell=tr.children[2];
  var pill=statusCell.querySelector('.pill');
  if(pill){pill.className='pill green';pill.textContent='已完成';}
  statusCell.style.color='';statusCell.style.fontWeight='';
  var deadlineCell=tr.children[3];
  if(deadlineCell.style.color)deadlineCell.style.color='';
  tr.style.opacity='.55';
  tr.style.transition='opacity .3s';
  btn.disabled=true;
  btn.style.opacity='.6';
  /* 更新统计卡片 */
  function decKpi(idx){var k=document.querySelectorAll('#page-todo-center .kpi')[idx];var v=k.querySelector('.value');var n=parseInt(v.textContent,10)||0;if(n>0){v.textContent=n-1;}}
  function incKpi(idx){var k=document.querySelectorAll('#page-todo-center .kpi')[idx];var v=k.querySelector('.value');var n=parseInt(v.textContent,10)||0;v.textContent=n+1;}
  var cur=pill?pill.textContent.trim():'';
  if(cur==='已完成'){
    if(tr.dataset.priority==='紧急')decKpi(0);
    decKpi(1);
    incKpi(2);
    /* 逾期任务处理则逾期数减1 */
    if(pill && pill.dataset.orig==='overdue')decKpi(3);
  }
  showToast('已标记为已处理');
}
function showTodoDetail(btn){
  var tr=btn.closest('tr');
  var title=tr.querySelector('b').textContent;
  var desc=tr.querySelector('b+div').textContent;
  var type=tr.children[1].textContent.trim();
  var priority=tr.dataset.priority||'';
  var status=tr.children[2].textContent.trim();
  var deadline=tr.children[3].textContent.trim();
  var owner=tr.children[4].textContent.trim();
  document.getElementById('todoDetailTitle').textContent=title;
  document.getElementById('todoDetailDesc').textContent=desc;
  document.getElementById('todoDetailType').textContent=type;
  document.getElementById('todoDetailPriority').textContent=priority;
  document.getElementById('todoDetailStatus').textContent=status;
  document.getElementById('todoDetailDeadline').textContent=deadline;
  document.getElementById('todoDetailOwner').textContent=owner;
  openModal('todoDetailModal');
}

/* 底价维护 JS */
let basePriceVersionSeq = 10;
function handleBasePriceFile(input){
  const file = input.files && input.files[0];
  if(!file) return;
  const ver = 'BP-2026-09-' + (++basePriceVersionSeq);
  const tbody = document.getElementById('basePriceTableBody');
  const tr = document.createElement('tr');
  tr.dataset.ver = ver;
  tr.dataset.status = 'active';
  tr.innerHTML = '<td><b>' + ver + '</b></td><td>电视</td><td>全系列电视型号</td><td>' + new Date().toISOString().slice(0,10) + '</td><td><span class="pill green">启用中</span></td><td><div class="bp-action"><span class="link-btn" onclick="toggleBasePriceStatus(this)">禁用</span><span class="link-btn" onclick="viewBasePrice(this)">查看</span><span class="link-btn danger" onclick="deleteBasePrice(this)">删除</span></div></td>';
  tbody.insertBefore(tr, tbody.firstChild);
  // 新上传的版本默认为启用，先禁用其他所有启用版本
  const rows = tbody.querySelectorAll('tr');
  rows.forEach(r => {
    if(r !== tr && r.dataset.status === 'active'){
      r.dataset.status = 'disabled';
      const pill = r.querySelector('.pill');
      pill.textContent = '已禁用';
      pill.className = 'pill gray';
      const firstBtn = r.querySelector('.bp-action .link-btn');
      firstBtn.textContent = '启用';
    }
  });
  showToast('上传成功，新版本 ' + ver + ' 已生效');
  input.value = ''; // 重置，允许重复选择同名文件
}
function toggleBasePriceStatus(btn){
  const tr = btn.closest('tr');
  const status = tr.dataset.status;
  const pill = tr.querySelector('.pill');
  if(status === 'active'){
    // 尝试禁用，检查是否还有其他启用版本
    const tbody = document.getElementById('basePriceTableBody');
    const activeCount = tbody.querySelectorAll('tr[data-status="active"]').length;
    if(activeCount <= 1){
      showToast('请至少保留一个版本启用');
      return;
    }
    tr.dataset.status = 'disabled';
    pill.textContent = '已禁用';
    pill.className = 'pill gray';
    btn.textContent = '启用';
    showToast('该底价版本已禁用');
  }else{
    // 尝试启用：先禁用其他所有启用版本，再启用当前，保证只有一个启用
    const tbody = document.getElementById('basePriceTableBody');
    tbody.querySelectorAll('tr[data-status="active"]').forEach(r => {
      r.dataset.status = 'disabled';
      const p = r.querySelector('.pill');
      p.textContent = '已禁用';
      p.className = 'pill gray';
      const firstBtn = r.querySelector('.bp-action .link-btn');
      firstBtn.textContent = '启用';
    });
    tr.dataset.status = 'active';
    pill.textContent = '启用中';
    pill.className = 'pill green';
    btn.textContent = '禁用';
    showToast('该底价版本已启用，巡检数据已同步刷新');
  }
}
function viewBasePrice(btn){
  const tr = btn.closest('tr');
  const ver = tr.dataset.ver;
  // 模拟下载
  showToast('已下载完成');
}
function deleteBasePrice(btn){
  const tr = btn.closest('tr');
  const ver = tr.dataset.ver;
  const status = tr.dataset.status;
  // 二次确认
  const confirmed = confirm('确定要删除底价版本 ' + ver + ' 吗？删除后不可恢复。');
  if(!confirmed) return;
  // 如果是启用版本且只有一个，不允许删除
  if(status === 'active'){
    const tbody = document.getElementById('basePriceTableBody');
    const activeCount = tbody.querySelectorAll('tr[data-status="active"]').length;
    if(activeCount <= 1){
      showToast('请至少保留一个版本启用');
      return;
    }
  }
  tr.remove();
  showToast('底价版本 ' + ver + ' 已删除');
}

/* 活动期间 JS */
function createActivity(){
  const name = document.getElementById('activityName').value.trim();
  if(!name){showToast('请输入活动名称');return}
  const sel = document.getElementById('activityFilter');
  const opt = document.createElement('option');
  opt.value = name;
  opt.textContent = name;
  sel.appendChild(opt);
  sel.value = name;
  closeModal('activityModal');
  document.getElementById('activityName').value = '';
  showToast('活动「' + name + '」创建成功');
}

/* 导出 JS */
function exportMonitorData(){showToast('导出成功，文件已下载')}

/* 竞品调价详情弹窗 */
function openRivalPriceDetail(brand,model,channel,price,base,change,shot,meta){
  document.getElementById('rivalPriceBaseLabel').textContent='原价';
  document.getElementById('rivalPriceProduct').textContent=brand+' '+model;
  document.getElementById('rivalPriceChannel').textContent=channel+' · 官方旗舰店';
  document.getElementById('rivalPriceCurrent').textContent=price;
  document.getElementById('rivalPriceBase').textContent=base;
  const changeEl=document.getElementById('rivalPriceChange');
  changeEl.textContent=change;
  if(change.startsWith('-')){changeEl.style.color='#e5484d'}else{changeEl.style.color='#1f9254'}
  showPriceLines('rivalPriceShot',shot);
  document.getElementById('rivalPriceMeta').textContent=meta;
  openModal('rivalPriceModal');
}

/* 竞品价格监控 - 价格明细弹窗（全局，确保内联onclick可访问） */
function openRivalPriceDetailMonitor(brand, model, channel, period){
  const modal = document.getElementById('rivalPriceDetailModal');
  const titleEl = document.getElementById('rivalDetailTitle');
  const wrap = document.getElementById('rivalPriceDetailTableWrap');
  if(!modal || !titleEl || !wrap) return;
  // 从全局变量读取基准数据
  const dataSrc = window._rivalMonitorData || [];
  let days, isIntraday = false;
  if(period==='month'){ days = 30; }
  else if(period==='today' || period==='yesterday'){ days = 8; isIntraday = true; }
  else { days = 7; }
  const end = new Date('2026-09-15');
  const baseDate = period==='yesterday' ? new Date(end.getTime()-86400000) : end;
  const start = isIntraday ? baseDate : new Date(end.getTime() - (days-1)*86400000);
  const fmt = d => (d.getFullYear()+'/'+String(d.getMonth()+1).padStart(2,'0')+'/'+String(d.getDate()).padStart(2,'0'));
  const seed = (brand+model+channel).split('').reduce((a,c)=>a+c.charCodeAt(0),0);
  let basePrice = 4999, origP = 5499;
  for(let g=0;g<dataSrc.length;g++){
    const group = dataSrc[g];
    if(!group || !group.rivals) continue;
    for(let j=0;j<group.rivals.length;j++){
      const r = group.rivals[j];
      if(r.brand===brand && r.model===model && r.channel===channel){
        basePrice = parseInt(String(r.curPrice).replace(/[^0-9]/g,'')) || basePrice;
        origP = parseInt(String(r.origPrice).replace(/[^0-9]/g,'')) || origP;
      }
    }
  }
  let rows = [];
  let prevPrice = basePrice + Math.round((seed%300)-150);
  const stepMs = isIntraday ? 3*3600*1000 : 86400000;
  for(let i=0;i<days;i++){
    const d = new Date(start.getTime() + i*stepMs);
    const offset = Math.round(Math.sin((seed+i)*0.7)*80) + ((seed+i)%40-20);
    const curP = Math.max(basePrice-200, Math.min(basePrice+200, prevPrice + offset));
    prevPrice = curP;
    const prevNum = rows[i-1]?rows[i-1]._num:basePrice;
    const change = i===0 ? 0 : (curP - prevNum) / prevNum * 100;
    const changeStr = (change>0?'+':'') + change.toFixed(1) + '%';
    const changeCls = change>0.5 ? 'danger-price' : (change<-0.5 ? 'success-price' : '');
    const hour = isIntraday ? (i*3+8)%24 : 8+(seed+i)%10;
    const timeStr = fmt(d) + ' ' + String(hour).padStart(2,'0') + ':' + String((seed*3+i*7)%60).padStart(2,'0');
    rows.push({
      curPrice: '¥'+curP.toLocaleString(),
      origPrice: '¥'+origP.toLocaleString(),
      change: changeStr,
      changeCls: changeCls,
      time: timeStr,
      _num: curP
    });
  }
  const thead = '<thead><tr><th>品牌</th><th>型号</th><th>渠道</th><th>到手价</th><th>原价</th><th>波动幅度</th><th>调价时间</th></tr></thead>';
  let tbody = '';
  for(let i=0;i<rows.length;i++){
    const r = rows[i];
    tbody += '<tr>'
      + '<td>'+brand+'</td>'
      + '<td><b>'+model+'</b></td>'
      + '<td>'+channel+'</td>'
      + '<td><b>'+r.curPrice+'</b></td>'
      + '<td><span style="color:var(--muted);font-size:12px">'+r.origPrice+'</span></td>'
      + '<td class="'+r.changeCls+'">'+r.change+'</td>'
      + '<td style="font-size:12px;color:var(--muted)">'+r.time+'</td>'
      + '</tr>';
  }
  const periodLabel = period==='today' ? '今日价格明细' : (period==='yesterday' ? '昨日价格明细' : (period==='month' ? '近30天价格明细' : (period==='custom' ? '自定义周期价格明细' : '近7天价格明细')));
  titleEl.textContent = brand+' '+model+' · '+periodLabel;
  wrap.innerHTML = '<table class="monitor-table rival-monitor-table" style="min-width:760px">'+thead+'<tbody>'+tbody+'</tbody></table>';
  modal.classList.add('show');
}
function closeRivalPriceDetailMonitor(){
  const m = document.getElementById('rivalPriceDetailModal');
  if(m) m.classList.remove('show');
}

/* 每日价格预警操作 */
function handleAlert(btn){
  const item=btn.closest('tr');
  const tag=item.querySelector('.status-tag');
  tag.textContent='处理中';
  tag.className='status-tag processing';
  showToast('已进入处理流程');
}
function ignoreAlertItem(btn){
  const item=btn.closest('tr');
  const tag=item.querySelector('.status-tag');
  if(tag){tag.className='status-tag ignored';tag.textContent='已忽略';}
  item.dataset.handled='ignored';
  btn.textContent='已忽略';
  btn.disabled=true;
  btn.style.opacity='.5';
  btn.style.cursor='not-allowed';
  const handleBtn=item.querySelector('.btn-handle');
  if(handleBtn){handleBtn.style.opacity='.5';handleBtn.disabled=true;handleBtn.style.cursor='not-allowed';}
  updateDailyAlertCount();
  showToast('该条预警已标记为已忽略');
}
function filterDailyAlertByStatus(status){
  const rows=document.querySelectorAll('#dailyAlertList tr');
  rows.forEach(tr=>{
    const tag=tr.querySelector('.status-tag');
    if(!tag){tr.style.display='';return;}
    let cur='pending';
    if(tag.classList.contains('processing'))cur='processing';
    else if(tag.classList.contains('done'))cur='done';
    else if(tag.classList.contains('ignored'))cur='ignored';
    tr.style.display=(status==='all'||status===cur)?'':'none';
  });
}
function updateDailyAlertCount(){
  const total=document.querySelectorAll('#dailyAlertList tr').length;
  const done=document.querySelectorAll('#dailyAlertList tr[data-handled="1"]').length;
  const pending=total-done;
  const sub=document.querySelector('.daily-alert-table-wrap').closest('.daily-section').querySelector('.ds-sub');
  if(sub){sub.textContent='严重等级预警明细 · 待处理 '+pending+' 条';}
}

/* 重点产品表现 JS */
const ALL_KEY_MODELS=window.gtmRecords.ALL_KEY_MODELS;
let keyModelDropdownTimer=null;
function openKeyProductModal(){
  openModal('keyModelModal');
  // 首次打开：初始化8款已选型号
  if(!window._keyModelInitialized){
      ['海信 75E8N Pro','海信 65E7Q','海信 55E5N','海信 85E8K','海信 75E7K','Vidda 65V5K','Vidda 55V5K','海信 100E8K'].forEach(name=>{
      const m=ALL_KEY_MODELS.find(x=>x.name===name);
      if(m) addSelectedItem(m.name,m.brand,m.coreType);
    });
    window._keyModelInitialized=true;
  }
  updateKeyModelCount();
  hideModelDropdown();
}
function openKeyModelModal(){openKeyProductModal()}
function updateKeyModelCount(){
  const count=document.querySelectorAll('#keyModelSelectedList .kpm-selected-item').length;
  document.getElementById('keyModelSelectedCount').textContent=count;
  const badge=document.getElementById('keyProductBadge');
  if(badge) badge.textContent=count;
  const navBadge=document.querySelector('[data-page="key-model"] .badge-count');
  if(navBadge) navBadge.textContent=count;
  const titleEl=document.querySelector('#page-key-model .section-head p');
  if(titleEl) titleEl.textContent='点击表头可排序 · 共 '+count+' 款重点产品';
}
function getSelectedModelNames(){
  return Array.from(document.querySelectorAll('#keyModelSelectedList .kpm-selected-item')).map(it=>it.dataset.name);
}
function showModelDropdown(kw){
  kw=(kw||'').trim().toLowerCase();
  const dropdown=document.getElementById('keyModelDropdown');
  const selected=getSelectedModelNames();
  const catSel=document.getElementById('kpmCategorySelect');
  const catVal=catSel?catSel.value:'all';
  const matched=ALL_KEY_MODELS.filter(m=>{
    if(selected.indexOf(m.name)>-1) return false;
    if(catVal!=='all' && m.cat!==catVal) return false;
    if(!kw) return true;
    return m.name.toLowerCase().indexOf(kw)>-1 || m.brand.toLowerCase().indexOf(kw)>-1 || m.coreType.toLowerCase().indexOf(kw)>-1;
  });
  if(matched.length===0){
    dropdown.innerHTML='<div class="km-dropdown-empty">未找到匹配型号</div>';
  }else{
    dropdown.innerHTML=matched.map(m=>{
      return '<div class="km-dropdown-item" onclick="addModelFromDropdown(\''+m.name+'\')">'
        +'<span class="kdd-name">'+m.name+'</span>'
        +'<span class="kdd-brand">'+m.brand+'</span>'
        +'<span class="kdd-category">'+m.coreType+'</span>'
        +'</div>';
    }).join('');
  }
  dropdown.style.display='block';
}
function filterKmModalByCategory(catVal){
  const input=document.getElementById('keyModelSearchInput');
  showModelDropdown(input.value);
}
function filterKpmByCategory(catVal){
  const input=document.getElementById('keyModelSearchInput');
  showModelDropdown(input.value);
}
function hideModelDropdown(){
  const dropdown=document.getElementById('keyModelDropdown');
  if(dropdown) dropdown.style.display='none';
}
function addModelFromDropdown(name){
  const m=ALL_KEY_MODELS.find(x=>x.name===name);
  if(!m) return;
  const currentCount=document.querySelectorAll('#keyModelSelectedList .kpm-selected-item').length;
  if(currentCount>=100){
    showToast('已超出最多维护产品数量（100款），请核查后再次添加。');
    return;
  }
  addSelectedItem(m.name,m.brand,m.coreType);
  updateKeyModelCount();
  // 添加后刷新下拉列表（移除已选项）
  const input=document.getElementById('keyModelSearchInput');
  showModelDropdown(input.value);
  showToast('已添加 '+m.name);
}
function addSelectedItem(name,brand,coreType){
  const list=document.getElementById('keyModelSelectedList');
  if(Array.from(list.querySelectorAll('.kpm-selected-item')).some(it=>it.dataset.name===name)) return;
  const item=document.createElement('div');
  item.className='kpm-selected-item';
  item.dataset.name=name;
  item.dataset.brand=brand;
  item.dataset.coretype=coreType;
  const m=ALL_KEY_MODELS.find(x=>x.name===name);
  const cat=m?.cat || '';
  let sizeText='';
  const tvSize=name.match(/(\d{2})\s*(?:E|Q|V|S|A|X|D|G|K)/);
  if(tvSize && cat==='电视'){sizeText='·'+tvSize[1]+'寸'}
  const fridgeSize=name.match(/(\d{3})/);
  if(fridgeSize && cat==='冰箱'){sizeText='·'+fridgeSize[1]+'L'}
  const catText=cat+sizeText;
  item.innerHTML='<span class="kpm-item-name">'+name+'</span>'
    +'<div class="kpm-item-tags">'
    +'<span class="kpm-tag">'+brand+'</span>'
    +'<span class="kpm-tag category-tag">'+catText+'</span>'
    +'<button class="kpm-delete-btn" onclick="removeSelectedItem(this)">删除</button>'
    +'</div>';
  list.appendChild(item);
}
function removeSelectedItem(nameOrBtn){
  let name=nameOrBtn;
  if(typeof nameOrBtn!=='string'){
    const item=nameOrBtn.closest('.kpm-selected-item');
    if(!item) return;
    name=item.dataset.name;
    item.remove();
  }else{
    const list=document.getElementById('keyModelSelectedList');
    const items=list.querySelectorAll('.kpm-selected-item');
    items.forEach(it=>{ if(it.dataset.name===name) it.remove(); });
  }
  updateKeyModelCount();
}
function confirmKeyProducts(){
  const count=document.querySelectorAll('#keyModelSelectedList .kpm-selected-item').length;
  hideModelDropdown();
  closeModal('keyModelModal');
  showToast('已保存 '+count+' 款重点产品');
  updateKeyModelCount();
}
function handleKpmBodyClick(e){
  const input=document.getElementById('keyModelSearchInput');
  const dropdown=document.getElementById('keyModelDropdown');
  if(!input || !dropdown) return;
  if(!input.contains(e.target) && !dropdown.contains(e.target)){
    hideModelDropdown();
  }
}
function handleModalBodyClick(e){
  // 点击搜索框及下拉以外的区域，关闭下拉
  const input=document.getElementById('keyModelSearchInput');
  const dropdown=document.getElementById('keyModelDropdown');
  if(!input || !dropdown) return;
  if(!input.contains(e.target) && !dropdown.contains(e.target)){
    hideModelDropdown();
  }
}
let keyModelSortCol=-1,keyModelSortAsc=true;
function sortKeyModelTable(col){
  const tbody=document.getElementById('keyModelTbody');
  const rows=Array.from(tbody.querySelectorAll('tr'));
  if(keyModelSortCol===col){keyModelSortAsc=!keyModelSortAsc}else{keyModelSortAsc=false;keyModelSortCol=col}
  rows.sort((a,b)=>{
    const av=parseSortValue(a.cells[col].textContent.trim());
    const bv=parseSortValue(b.cells[col].textContent.trim());
    if(av<bv) return keyModelSortAsc?-1:1;
    if(av>bv) return keyModelSortAsc?1:-1;
    return 0
  });
  rows.forEach(r=>tbody.appendChild(r))
}
function parseSortValue(s){
  if(s.indexOf('第')>-1){const m=s.match(/\d+/);return m?parseFloat(m[0]):0}
  if(s.indexOf('↑')>-1) return 999;
  if(s.indexOf('↓')>-1) return -999;
  if(s==='—') return 0
  const num=s.replace(/[^\d.-]/g,'');
  if(num===''||num==='-'||num==='.') return s.localeCompare?0:0;
  return parseFloat(num)||0
}
/* 每日重点工作 JS */
const dailyModels=window.gtmRecords.dailyModels;
let dailyCurrentModel=0;
function switchDailyModel(idx,el){
  dailyCurrentModel=idx;
  document.querySelectorAll('#dailyModelCards .daily-model-card').forEach(function(c,i){c.classList.toggle('active',i===idx)});
  var m=dailyModels[idx];
  var period=getDailyPeriod();
  var isToday=period==='today';
  document.getElementById('dailyModelTitle').textContent=m.name+' · 销售趋势';
  var unitsVal=isToday?m.units.today+' 台':m.units.week+' 台';
  var unitsTrend=isToday?m.units.unitsTrend.today:m.units.unitsTrend.week;
  var revenueVal=isToday?'¥'+m.revenue.today:'¥'+m.revenue.week;
  var revenueTrend=isToday?m.revenue.revTrend.today:m.revenue.revTrend.week;
  var priceVal=isToday?m.price.today:m.price.week;
  var priceTrend=isToday?m.price.priceTrend.today:m.price.priceTrend.week;
  document.getElementById('dailyMetricUnitsLabel').textContent='销量';
  document.getElementById('dailyMetricRevenueLabel').textContent='销额';
  document.getElementById('dailyMetricPriceLabel').textContent='均价';
  document.getElementById('dailyMetricUnits').textContent=unitsVal;
  document.getElementById('dailyMetricRevenue').textContent=revenueVal;
  document.getElementById('dailyMetricPrice').textContent=priceVal;
  var ut=document.getElementById('dailyMetricUnitsTrend');ut.textContent=(unitsTrend>=0?'+':'')+unitsTrend.toFixed(1)+'%';ut.style.color=unitsTrend>=0?'var(--success)':'var(--danger)';
  var rt=document.getElementById('dailyMetricRevenueTrend');rt.textContent=(revenueTrend>=0?'+':'')+revenueTrend.toFixed(1)+'%';rt.style.color=revenueTrend>=0?'var(--success)':'var(--danger)';
  var pt=document.getElementById('dailyMetricPriceTrend');pt.textContent=(priceTrend>=0?'+':'')+priceTrend.toFixed(1)+'%';pt.style.color=priceTrend>=0?'var(--success)':'var(--danger)';
  var chart=document.getElementById('dailyModelChart');
  if(chart){chart.classList.toggle('hidden',isToday);var sub=document.querySelector('.dm-detail-sub');if(sub)sub.textContent=isToday?'单日指标概览':'销量 / 均价走势';if(!isToday)renderDualAxisChart(idx)}
}
function getDailyPeriod(){var s=document.getElementById('dailyPeriodSelect');return s?s.value:'today'}
function switchDailyPeriod(val){
  const aiTime=document.querySelector('.daily-ai-overview .ai-time');
  const dateMap={today:'2026-09-10 09:30',yesterday:'2026-09-09 23:50',week7:'近7天 · 2026-09-04~09-10',month:'近30天 · 2026-08-11~09-10'};
  const periodText={today:'今日',yesterday:'昨日',week7:'近7天',month:'近30天'};
  if(aiTime && dateMap[val]){aiTime.textContent='基于当前筛选条件生成 · '+dateMap[val];}
  switchDailyModel(dailyCurrentModel,null);
  renderDailyTrendChart(val);
  renderRivalPriceAlertTable(val);
  showToast('已切换为'+(periodText[val]||val)+'数据');
}
function updateDailySubCategory(catKey){
  const opts=cascaderOptions[catKey]?.children||['平板电视'];
  const sel=document.getElementById('dailySubCategorySelect');
  sel.innerHTML='<option value="全部">全部</option>'+opts.map(o=>'<option value="'+o+'">'+o+'</option>').join('');
}
function updateKeyModelSubCategory(catKey){
  const opts=cascaderOptions[catKey]?.children||['平板电视'];
  const sel=document.getElementById('keyModelSubCategorySelect');
  sel.innerHTML='<option value="全部">全部</option>'+opts.map(o=>'<option value="'+o+'">'+o+'</option>').join('');
}
const coreTypeMap=window.gtmRecords.coreTypeMap;
function updateKeyModelCoreType(catKey){
  const cfg=coreTypeMap[catKey]||coreTypeMap.tv;
  const sel=document.getElementById('keyModelCoreTypeSelect');
  sel.innerHTML='<option value="all">全部</option>'+cfg.options.map(o=>'<option value="'+o+'">'+o+'</option>').join('');
}
function toggleKeyModelCustomDate(val){
  const show=val==='custom';
  document.getElementById('keyModelCustomDate').style.display=show?'flex':'none';
  document.getElementById('keyModelCustomDateEnd').style.display=show?'flex':'none';
}
function updateOwnSubCategory(catKey){
  const opts=cascaderOptions[catKey]?.children||['平板电视'];
  const sel=document.getElementById('ownSubCategorySelect');
  sel.innerHTML='<option value="全部">全部</option>'+opts.map(o=>'<option value="'+o+'">'+o+'</option>').join('');
}
function toggleOwnCustomDate(val){
  const show=val==='custom';
  document.getElementById('ownCustomDateStart').style.display=show?'flex':'none';
  document.getElementById('ownCustomDateEnd').style.display=show?'flex':'none';
}
let currentHandleRow=null;
function openHandleModal(btn){
  const tr=btn.closest('tr');
  currentHandleRow=tr;
  openModal('handlePriceModal');
}
function submitHandleTask(btn){
  const modal=btn.closest('.modal');
  const selects=modal.querySelectorAll('select');
  const textarea=modal.querySelector('textarea');
  if(!selects[0].value){showToast('请选择处理联系人');return;}
  if(!textarea.value.trim()){showToast('请填写处理意见');return;}
  closeModal('handlePriceModal');
  showToast('跟进任务已生成，已通知处理联系人');
  if(currentHandleRow){
    const statusCell=currentHandleRow.querySelector('td.status-cell,td:nth-child(9)');
    if(statusCell){statusCell.innerHTML='<span class="status-tag processing">处理中</span>';}
  }
}
function ignoreMonitorRow(btn){
  const tr=btn.closest('tr');
  // 处理状态列：第10列
  const statusCell=tr.querySelector('td:nth-child(10)');
  if(statusCell){statusCell.innerHTML='<span class="pill gray">已忽略</span>';}
  btn.style.display='none';
  const handleBtn=tr.querySelector('.btn-handle');
  if(handleBtn){handleBtn.style.display='none';}
  showToast('该条记录已标记为已忽略');
}
function filterOwnMonitorByHandleStatus(status){
  const table=document.querySelector('.own-monitor-table tbody');
  if(!table)return;
  const rows=table.querySelectorAll('tr');
  let visibleCount=0;
  rows.forEach(tr=>{
    // 处理状态列：第10列
    const cell=tr.querySelector('td:nth-child(10)');
    if(!cell){tr.style.display='';return;}
    const pill=cell.querySelector('.pill');
    let cur='pending';
    if(pill){
      const t=pill.textContent.trim();
      if(t==='待处理')cur='pending';
      else if(t==='处理中')cur='processing';
      else if(t==='已处理')cur='done';
      else if(t==='已忽略')cur='ignored';
    }
    const show=(status==='all'||status===cur);
    tr.style.display=show?'':'none';
    if(show)visibleCount++;
  });
  const totalEl=document.querySelector('#page-own-monitor .ep-total');
  if(totalEl){totalEl.textContent='共 '+visibleCount+' 条';}
  updateOwnMonitorSummary();
}
function updateOwnMonitorSummary(){
  const table=document.querySelector('.own-monitor-table tbody');
  if(!table)return;
  const rows=table.querySelectorAll('tr');
  let serious=0,urgent=0,normal=0,pending=0;
  rows.forEach(tr=>{
    if(tr.style.display==='none')return;
    // 第9列：预警等级
    const alertCell=tr.querySelector('td:nth-child(9)');
    const statusCell=tr.querySelector('td:nth-child(10)');
    if(!alertCell)return;
    const alertPill=alertCell.querySelector('.pill');
    const statusPill=statusCell?statusCell.querySelector('.pill'):null;
    if(alertPill){
      const t=alertPill.textContent.trim();
      if(t==='严重')serious++;
      else if(t==='紧急')urgent++;
      else if(t==='一般')normal++;
    }
    if(statusPill&&statusPill.textContent.trim()==='待处理')pending++;
  });
  const el=document.getElementById('ownMonitorSummary');
  if(!el)return;
  el.innerHTML='<span><i class="dot serious"></i>严重 '+serious+' 项</span><span><i class="dot urgent"></i>紧急 '+urgent+' 项</span><span><i class="dot normal"></i>一般 '+normal+' 项</span><span style="margin-left:6px;padding-left:10px;border-left:1px solid var(--border)"><i class="dot pending"></i>待处理 '+pending+' 项</span>';
}
function initOwnMonitorNormalStatus(){
  // 预警等级为"正常"时，处理状态列显示"--"
  const table=document.querySelector('.own-monitor-table tbody');
  if(!table)return;
  const rows=table.querySelectorAll('tr');
  rows.forEach(tr=>{
    const alertCell=tr.querySelector('td:nth-child(9)');
    const statusCell=tr.querySelector('td:nth-child(10)');
    if(!alertCell||!statusCell)return;
    const alertPill=alertCell.querySelector('.pill');
    if(alertPill&&alertPill.textContent.trim()==='正常'){
      statusCell.innerHTML='<span style="color:var(--muted-light)">--</span>';
    }
  });
}
function initOwnMonitorRowButtons(){
  const table=document.querySelector('.own-monitor-table tbody');
  if(!table)return;
  const rows=table.querySelectorAll('tr');
  rows.forEach(tr=>{
    const cell=tr.querySelector('td:nth-child(10)');
    if(!cell)return;
    const pill=cell.querySelector('.pill');
    if(!pill)return;
    const status=pill.textContent.trim();
    const ignoreBtn=tr.querySelector('.btn-ignore');
    const handleBtn=tr.querySelector('.btn-handle');
    if(!ignoreBtn||!handleBtn)return;
    // 重置所有按钮样式
    ignoreBtn.style.display='';
    ignoreBtn.disabled=false;
    ignoreBtn.style.opacity='';
    ignoreBtn.style.cursor='';
    ignoreBtn.style.background='';
    ignoreBtn.style.borderColor='';
    ignoreBtn.style.color='';
    ignoreBtn.textContent='忽略';
    handleBtn.style.display='';
    handleBtn.disabled=false;
    handleBtn.style.opacity='';
    handleBtn.style.cursor='';

    if(status==='待处理'){
      // 三按钮都展示，都可用
    }else if(status==='处理中'){
      // 仅展示详情按钮
      ignoreBtn.style.display='none';
      handleBtn.style.display='none';
    }else if(status==='已处理'){
      // 仅展示详情按钮
      ignoreBtn.style.display='none';
      handleBtn.style.display='none';
    }else if(status==='已忽略'){
      // 仅展示详情按钮
      ignoreBtn.style.display='none';
      handleBtn.style.display='none';
    }
  });
}
let currentRivalEvidence={};
function openRivalEvidence(level,product,shop,price,original,gap,shot,meta,avgPrice){
  currentRivalEvidence={level,product,shop,price,original,gap,shot,meta,avgPrice};
  showSeverity('rivalEvidenceLevel',level);
  document.getElementById('rivalEvidenceProduct').textContent=product;
  const ch=meta.split('·')[0]?.trim()||'';
  document.getElementById('rivalEvidenceChannel').textContent=ch;
  document.getElementById('rivalEvidencePrice').textContent=price;
  // 第二指标随时间筛选动态切换
  const period=document.getElementById('rivalPeriodSelect')?.value||'week7';
  const isShort=period==='today'||period==='yesterday';
  const labelEl=document.getElementById('rivalEvidenceSecondLabel');
  const valEl=document.getElementById('rivalEvidenceSecondValue');
  if(labelEl&&valEl){
    if(isShort){
      labelEl.textContent='原价';
      valEl.textContent=original;
    } else {
      labelEl.textContent='均价';
      valEl.textContent=avgPrice||'—';
    }
  }
  const gapEl=document.getElementById('rivalEvidenceGap');
  gapEl.textContent=gap;
  gapEl.dataset.level=level;
  showPriceLines('rivalEvidenceShot',shot);
  document.getElementById('rivalEvidenceMeta').textContent=meta;
  openModal('rivalEvidenceModal');
}
function aiAskRivalPrice(){
  var d=currentRivalEvidence;
  if(!d||!d.product)return;
  closeModal('rivalEvidenceModal');
  var ch=d.meta.split('·')[0]?.trim()||'';
  var q='请分析'+d.product+'在'+ch+'渠道价格异常的原因及应对建议';
  askQ(q);
}
function exportDailyReport(){showToast('日报导出成功，已下载「2026-09-04_GTM每日重点工作.pdf」')}
/* 品类细分级联选择器 */
const cascaderOptions=window.gtmRecords.cascaderOptions;
let currentCascaderLv1='tv';
let currentCascaderLv2='平板电视';
function toggleCascader(e){e.stopPropagation();var p=document.getElementById('cascaderPanel');p.classList.toggle('show')}
document.addEventListener('click',function(){var p=document.getElementById('cascaderPanel');if(p)p.classList.remove('show')});
function selectCascaderLv1(key,name,e){e.stopPropagation();currentCascaderLv1=key;
  var cols=document.querySelectorAll('#cascaderPanel .cascader-col:first-child .cascader-item');
  cols.forEach(function(el,i){el.classList.remove('active')});
  e.currentTarget.classList.add('active');
  var opts=cascaderOptions[key].children;
  currentCascaderLv2=opts[0];
  var col2=document.getElementById('cascaderCol2');
  col2.innerHTML=opts.map(function(o,i){return'<div class="cascader-item '+(i===0?'active':'')+'" onclick="selectCascaderLv2(\''+o+'\',event)">'+o+'</div>'}).join('');
  updateCascaderDisplay()}
function selectCascaderLv2(val,e){e.stopPropagation();currentCascaderLv2=val;
  var items=document.querySelectorAll('#cascaderCol2 .cascader-item');
  items.forEach(function(el){el.classList.remove('active');if(el.textContent===val)el.classList.add('active')});
  updateCascaderDisplay()}
function updateCascaderDisplay(){document.getElementById('cascaderDisplayText').textContent=cascaderOptions[currentCascaderLv1].name+' / '+currentCascaderLv2}
/* 竞品百科弹窗 */
var currentLaunchPeriod='30d';
var launchPeriodMeta=window.gtmRecords.launchPeriodMeta;
var currentLaunchProduct=null;
const brandColors={TCL:'#1a3fe8',美的:'#e5484d',小米:'#ff6700',华为:'#cf0a2c',创维:'#006cff',康佳:'#0091eb'}
function openLaunchEncyclopedia(brand,name,sub,sales,revenue,price,date,channel,category,position,points,impact){
  currentLaunchProduct={brand:brand,name:name,sub:sub,sales:sales,revenue:revenue,price:price,date:date,channel:channel,category:category,position:position,points:points,impact:impact};
  renderLaunchEncyclopedia();
  openModal('launchEncyclopediaModal')}
function renderLaunchEncyclopedia(){
  if(!currentLaunchProduct)return;
  var p=currentLaunchProduct,meta=launchPeriodMeta[currentLaunchPeriod]||launchPeriodMeta['30d'];
  var unitsNum=parseFloat(p.sales.replace(/[^\d.]/g,''));
  var revNum=parseFloat(p.revenue.replace(/[^\d.]/g,''));
  var priceNum=parseFloat(p.price.replace(/[^\d.]/g,''));
  var uVal=Math.max(1,Math.round(unitsNum*meta.unitsRatio)).toLocaleString('zh-CN')+' 台';
  var rVal='¥'+(revNum*meta.revenueRatio).toFixed(1)+' 万';
  var prVal='¥'+Math.round(priceNum*meta.priceRatio).toLocaleString('zh-CN');
  document.getElementById('launchModalTitle').textContent=p.brand+' '+p.name+' · 竞品百科';
  var logo=document.getElementById('launchModalLogo');logo.textContent=p.brand.charAt(0);
  logo.style.color=brandColors[p.brand]||'var(--primary)';
  document.getElementById('launchModalName').textContent=p.name;
  document.getElementById('launchModalSub').textContent=p.sub;
  document.getElementById('launchModalSalesLabel').textContent=meta.label+'销量';
  document.getElementById('launchModalRevenueLabel').textContent=meta.label+'销额';
  document.getElementById('launchModalPriceLabel').textContent=currentLaunchPeriod==='today'||currentLaunchPeriod==='yesterday'?meta.label+'均价':'当前均价';
  document.getElementById('launchModalSales').textContent=uVal;
  document.getElementById('launchModalRevenue').textContent=rVal;
  document.getElementById('launchModalPrice').textContent=prVal;
  document.getElementById('launchModalDate').textContent=p.date;
  document.getElementById('launchModalChannel').textContent=p.channel;
  document.getElementById('launchModalBrand').textContent=p.brand;
  document.getElementById('launchModalModel').textContent=p.name;
  document.getElementById('launchModalCategory').textContent=p.category;
  document.getElementById('launchModalPosition').textContent=p.position;
  document.getElementById('launchModalPoints').innerHTML=p.points.map(function(v){return'<span class="sell-point">'+v+'</span>'}).join('');
  document.getElementById('launchModalImpact').textContent=p.impact;
}
function askLaunchWiki(){
  if(!currentLaunchProduct)return;
  closeModal('launchEncyclopediaModal');
  askQ('请分析 '+currentLaunchProduct.brand+' '+currentLaunchProduct.name+' 这款竞品新品对我品的影响，包括销量冲击、价格带竞争和差异化建议');
}
/* 每日重点产品 销量&均价双轴趋势图 */
let dmChart=null;
function renderDualAxisChart(modelIdx){
  var wrap=document.getElementById('dmChartWrap');if(!wrap||typeof echarts==='undefined')return;
  var m=dailyModels[modelIdx],dates=m.trend.dates,units=m.trend.units,prices=m.trend.price;
  var xLabels=dates.map(function(d,i){
    if(d==='今日') return '今日';
    var base=new Date('2026-09-10');
    base.setDate(base.getDate()-(dates.length-1-i));
    return String(base.getMonth()+1).padStart(2,'0')+'/'+String(base.getDate()).padStart(2,'0');
  });
  if(!dmChart) dmChart=echarts.init(wrap);
  var option={
    grid:{left:60,right:64,top:20,bottom:32},
    tooltip:{trigger:'axis',backgroundColor:'#1f2937',borderColor:'transparent',textStyle:{color:'#fff',fontSize:11},extraCssText:'box-shadow:none',formatter:function(params){
      if(!params||!params.length)return '';
      var dIdx=params[0].dataIndex;
      var html='<b style="font-weight:600">'+(xLabels[dIdx]==='今日'?'2026/09/10 今日':xLabels[dIdx])+'</b><br/>';
      params.forEach(function(p){
        html+='<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:'+p.color+';margin-right:6px"></span>';
        html+=p.seriesName+'：<b style="font-weight:600">'+p.value.toLocaleString()+(p.seriesName==='均价'?'':' 台')+'</b><br/>';
      });
      html+='<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#5B7CFA;margin-right:6px"></span>';
      html+='销额：<b style="font-weight:600">¥'+m.trend.revenue[params[0].dataIndex]+'万</b>';
      return html;
    }},
    xAxis:{type:'category',data:xLabels,axisLine:{lineStyle:{color:'#e7e9ee'}},axisTick:{show:false},axisLabel:{color:'#8f99a8',fontSize:11}},
    yAxis:[
      {type:'value',name:'销量',nameTextStyle:{color:'#8f99a8',fontSize:10,padding:[0,4,0,4]},nameLocation:'end',nameGap:10,axisLine:{show:false},axisTick:{show:false},splitLine:{lineStyle:{color:'#eef0f3'}},axisLabel:{color:'#8f99a8',fontSize:10,formatter:function(v){return v>=1000?(v/1000).toFixed(1)+'k':v},margin:10}},
      {type:'value',name:'均价',nameTextStyle:{color:'#8f99a8',fontSize:10,padding:[0,4,0,4]},nameLocation:'end',nameGap:10,axisLine:{show:false},axisTick:{show:false},splitLine:{show:false},axisLabel:{color:'#8f99a8',fontSize:10,formatter:function(v){return '¥'+(v>=1000?(v/1000).toFixed(1)+'k':v)},margin:10}}
    ],
    series:[
      {name:'销量',type:'line',smooth:true,symbol:'circle',symbolSize:6,itemStyle:{color:'#0aa9a1',borderColor:'#fff',borderWidth:2},lineStyle:{color:'#0aa9a1',width:2.5},areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(10,169,161,0.2)'},{offset:1,color:'rgba(10,169,161,0.02)'}]}},data:units},
      {name:'均价',type:'line',yAxisIndex:1,smooth:true,symbol:'circle',symbolSize:5,itemStyle:{color:'#F59E0B',borderColor:'#fff',borderWidth:2},lineStyle:{color:'#F59E0B',width:2,type:'dashed'},data:prices}
    ]
  };
  dmChart.setOption(option,true);
}

/* 近7天价格违规趋势 ECharts */
let dailyTrendChart=null;
function renderDailyTrendChart(period){
  var wrap=document.getElementById('dailyTrendChartWrap');
  var empty=document.getElementById('dailyTrendEmpty');
  var chartEl=document.getElementById('dailyTrendChart');
  if(!wrap||!chartEl)return;
  if(period==='today'||period==='yesterday'){
    if(dailyTrendChart){dailyTrendChart.dispose();dailyTrendChart=null;}
    chartEl.style.display='none';
    empty.style.display='flex';
    return;
  }
  empty.style.display='none';
  chartEl.style.display='block';
  if(typeof echarts==='undefined')return;
  if(!dailyTrendChart) dailyTrendChart=echarts.init(chartEl);
  var xData=['09/04','09/05','09/06','09/07','09/08','09/09','今日'];
  var yData=[8,11,7,14,19,16,12];
  if(period==='month'){
    xData=[];yData=[];
    for(var i=29;i>=0;i--){
      var d=new Date('2026-09-10');d.setDate(d.getDate()-i);
      xData.push(String(d.getMonth()+1).padStart(2,'0')+'/'+String(d.getDate()).padStart(2,'0'));
      yData.push(Math.round(8+Math.random()*16));
    }
  }
  var option={
    grid:{left:40,right:20,top:20,bottom:28},
    tooltip:{trigger:'axis',backgroundColor:'#1f2937',borderColor:'transparent',textStyle:{color:'#fff',fontSize:11},formatter:function(p){return '<b>'+p[0].axisValue+'</b><br/>违规数量：<b style="color:#7ed8d5">'+p[0].value+'</b>'}},
    xAxis:{type:'category',data:xData,axisLine:{lineStyle:{color:'#e7e9ee'}},axisTick:{show:false},axisLabel:{color:'#8f99a8',fontSize:10,interval:period==='month'?4:0}},
    yAxis:{type:'value',axisLine:{show:false},axisTick:{show:false},splitLine:{lineStyle:{color:'#eef0f3'}},axisLabel:{color:'#8f99a8',fontSize:10,minInterval:1}},
    series:[{
      type:'line',
      smooth:true,
      symbol:'circle',
      symbolSize:5,
      itemStyle:{color:'#0064fa',borderColor:'#fff',borderWidth:2},
      lineStyle:{color:'#0064fa',width:2.5},
      areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(0,100,250,0.15)'},{offset:1,color:'rgba(0,100,250,0.02)'}]}},
      data:yData
    }]
  };
  dailyTrendChart.setOption(option,true);
}

/* 图表ResizeObserver 自适应 */
function initChartResizeObservers(){
  if(typeof ResizeObserver==='undefined'||typeof echarts==='undefined')return;
  function observe(id,chartGetter){
    var el=document.getElementById(id);
    if(!el)return;
    var ro=new ResizeObserver(function(){var c=chartGetter();if(c)c.resize();});
    ro.observe(el);
  }
  observe('dmChartWrap',function(){return dmChart;});
  observe('dailyTrendChart',function(){return dailyTrendChart;});
}
document.addEventListener('DOMContentLoaded',function(){initChartResizeObservers();initOwnMonitorNormalStatus();initOwnMonitorRowButtons();updateOwnMonitorSummary();updateLaunchTableTotal();if(typeof renderRivalMonitorTable==='function')renderRivalMonitorTable('week7')});

/* 竞品调价提醒 表格渲染 */
const rivalPriceAlertData=window.gtmRecords.rivalPriceAlertData;
function getPeriodRangeLabel(period){
  var today=new Date(2026,8,10);
  var days=period==='week7'?7:30;
  var end=new Date(today.getTime()-86400000);
  var start=new Date(end.getTime()-(days-1)*86400000);
  function fmt(d){return String(d.getMonth()+1).padStart(2,'0')+'/'+String(d.getDate()).padStart(2,'0')}
  return fmt(start)+'-'+fmt(end);
}
function filterByThreshold(list,threshold){return list.filter(function(r){return Math.abs(r.change)>threshold})}
function renderRivalPriceAlertTable(period){
  var table=document.getElementById('rivalPriceAlertTable'),countEl=document.getElementById('rivalPriceAlertCount');
  if(!table)return;
  var isShort=period==='today'||period==='yesterday';
  var allData=rivalPriceAlertData[period]||rivalPriceAlertData.today;
  var data=filterByThreshold(allData,5);
  var total=data.length;
  var showAll=false;
  if(window._rivalAlertShowAll && window._rivalAlertShowAll[period]){showAll=true}
  var displayData=showAll?data:data.slice(0,5);
  var downCount=data.filter(function(r){return r.change<0}).length;
  var upCount=data.length-downCount;
  var periodLabel={today:'今日',yesterday:'昨日',week7:'近7天',month:'近30天'};
  if(countEl)countEl.textContent=(periodLabel[period]||'今日')+'共 '+data.length+' 条';
  var pillBar=document.querySelector('#page-daily .daily-section:nth-child(4) .ds-actions');
  if(pillBar){pillBar.innerHTML='<span class="pill red">降价 '+downCount+'</span><span class="pill green">涨价 '+upCount+'</span><button class="btn sm" onclick="goPage(\'rival-monitor\',document.querySelector(\'[data-page=rival-monitor]\'))">查看全部 ›</button>'}
  var thead='',colgroup='';
  if(isShort){
    colgroup='<colgroup><col style="width:80px"><col style="width:23%"><col style="width:70px"><col style="width:95px"><col style="width:90px"><col style="width:95px"><col style="width:80px"><col style="width:80px"></colgroup>';
    thead='<thead><tr><th>品牌</th><th>型号</th><th>渠道</th><th>当前到手价</th><th>原价</th><th>波动幅度</th><th>调价时间</th><th style="text-align:right">操作</th></tr></thead>';
  }else{
    colgroup='<colgroup><col style="width:70px"><col style="width:18%"><col style="width:60px"><col style="width:85px"><col style="width:80px"><col style="width:75px"><col style="width:75px"><col style="width:80px"><col style="width:85px"><col style="width:80px"><col style="width:70px"></colgroup>';
    thead='<thead><tr><th>品牌</th><th>型号</th><th>渠道</th><th>当前到手价</th><th>原价</th><th>最高价</th><th>最低价</th><th>均价</th><th>波动幅度</th><th>调价周期</th><th style="text-align:right">操作</th></tr></thead>';
  }
  var tbody='<tbody>'+displayData.map(function(r){
    var cls=r.change<0?'down':'up';var arrow=r.change<0?'▼':'▲';var chg=(r.change>=0?'+':'')+r.change.toFixed(1)+'%';
    var level=Math.abs(r.change)>=10?'严重':Math.abs(r.change)>=7?'关注':'一般';
    var avgPrice=r.avg||r.base;
    var meta=r.shop.includes('·')?r.shop:r.channel+' · '+r.shop;
    var action='<button class="action-btn" onclick="openRivalEvidence(\''+level+'\',\''+r.brand+' '+r.model+'\',\''+r.shop+'\',\''+r.current+'\',\''+r.base+'\',\''+chg+'\',\''+r.detail+'\',\''+meta+'\',\''+avgPrice+'\')">查看详情</button>';
    if(isShort){
      return '<tr><td class="brand-cell">'+r.brand+'</td><td class="model-cell"><b>'+r.model+'</b><span>'+r.spec+'</span></td><td class="channel-cell">'+r.channel+'</td><td class="price-cell">'+r.current+'</td><td class="base-cell">'+r.base+'</td><td class="change-cell '+cls+'">'+arrow+' '+Math.abs(r.change).toFixed(1)+'%</td><td class="time-cell">'+r.time+'</td><td class="action-cell">'+action+'</td></tr>';
    }else{
      return '<tr><td class="brand-cell">'+r.brand+'</td><td class="model-cell"><b>'+r.model+'</b><span>'+r.spec+'</span></td><td class="channel-cell">'+r.channel+'</td><td class="price-cell">'+r.current+'</td><td class="base-cell">'+r.base+'</td><td class="base-cell">'+r.high+'</td><td class="base-cell">'+r.low+'</td><td class="base-cell">'+r.avg+'</td><td class="change-cell '+cls+'">'+arrow+' '+Math.abs(r.change).toFixed(1)+'%</td><td class="time-cell">'+getPeriodRangeLabel(period)+'</td><td class="action-cell">'+action+'</td></tr>';
    }
  }).join('')+'</tbody>';
  table.innerHTML=colgroup+thead+tbody;
  var footRow=table.querySelector('tfoot');
  if(footRow)footRow.remove();
  if(data.length>5){
    var tfoot=document.createElement('tfoot');
    var colSpan=isShort?8:11;
    tfoot.innerHTML='<tr><td colspan="'+colSpan+'" style="text-align:center;padding:10px;border-top:1px solid var(--line);background:#fafbfc"><span class="link-btn" style="color:var(--primary);cursor:pointer" onclick="toggleRivalAlertShowAll(\''+period+'\')">'+(showAll?'收起 ▲':'查看更多 ▼（共 '+data.length+' 条）')+'</span></td></tr>';
    table.appendChild(tfoot);
  }
}
function toggleRivalAlertShowAll(period){
  if(!window._rivalAlertShowAll)window._rivalAlertShowAll={};
  window._rivalAlertShowAll[period]=!window._rivalAlertShowAll[period];
  renderRivalPriceAlertTable(period);
}
/* 预警表格交互 */
function toggleAllAlerts(cb){var boxes=document.querySelectorAll('#dailyAlertTableBody .table-checkbox');boxes.forEach(function(b){b.checked=cb.checked})}
function ignoreAlert(el){if(confirm('确定忽略此预警？')){el.closest('tr').style.opacity='.4';el.closest('tr').style.pointerEvents='none';showToast('已忽略该预警')}}
/* 价格违规趋势图 hover */
const dailyTrendData=window.gtmRecords.dailyTrendData;
function initDailyTrendHover(){var svg=document.getElementById('dailyTrendSvg');var tip=document.getElementById('dailyTrendTooltip');var line=document.getElementById('dailyTrendHoverLine');if(!svg||!tip||!line)return;var wrap=svg.closest('.daily-trend-chart-wrap');var nodes=svg.querySelectorAll('.daily-trend-nodes circle');nodes.forEach(function(node,i){node.addEventListener('mousemove',function(e){e.stopPropagation();showDailyTrendTip(i,e)});node.addEventListener('mouseleave',function(e){e.stopPropagation();hideDailyTrendTip()})});svg.addEventListener('mousemove',function(e){var rect=svg.getBoundingClientRect();var relX=(e.clientX-rect.left)/rect.width*700;var closest=0,minDist=999;dailyTrendData.forEach(function(d,i){var dist=Math.abs(d.x-relX);if(dist<minDist){minDist=dist;closest=i}});showDailyTrendTip(closest,e)});svg.addEventListener('mouseleave',hideDailyTrendTip);function showDailyTrendTip(i,e){line.setAttribute('x1',dailyTrendData[i].x);line.setAttribute('x2',dailyTrendData[i].x);line.setAttribute('opacity','1');nodes.forEach(function(n,j){n.setAttribute('r',j===i?'6':'4')});document.getElementById('dailyTrendTipDate').textContent=dailyTrendData[i].date;document.getElementById('dailyTrendTipCount').textContent=dailyTrendData[i].count+' 项';var wrapRect=wrap.getBoundingClientRect();var tipX=(dailyTrendData[i].x/700)*wrapRect.width+14;if(tipX+130>wrapRect.width)tipX=(dailyTrendData[i].x/700)*wrapRect.width-100;tip.style.left=tipX+'px';tip.style.top='20px';tip.classList.add('show')}function hideDailyTrendTip(){line.setAttribute('opacity','0');tip.classList.remove('show');nodes.forEach(function(n){n.setAttribute('r','4')})}
}
/* 饼图 hover */
const pieData=window.gtmRecords.pieData;
function hoverPieSlice(idx){var legend=document.getElementById('dailyPieLegend');if(legend){legend.querySelectorAll('.pie-legend-item').forEach(function(el,i){el.classList.toggle('active',i===idx)})}showPieTooltip(null,idx)}
function unhoverPieSlice(){var legend=document.getElementById('dailyPieLegend');if(legend){legend.querySelectorAll('.pie-legend-item').forEach(function(el){el.classList.remove('active')})}hidePieTooltip()}
function showPieTooltip(e,idx){var tip=document.getElementById('dailyPieTooltip');if(!tip)return;if(idx===undefined){var pie=document.getElementById('dailyChannelPie');if(!pie)return;var rect=pie.getBoundingClientRect();var cx=rect.width/2,cy=rect.height/2;var angle=Math.atan2(e.offsetY-cy,e.offsetX-cx)*180/Math.PI;if(angle<0)angle+=360;var stops=[42,67,84,100];idx=0;for(var s=0;s<stops.length;s++){if(angle<stops[s]*3.6){idx=s;break}}}
  document.getElementById('dailyPieTipName').textContent=pieData[idx].name;
  document.getElementById('dailyPieTipCount').textContent=pieData[idx].count+' 项';
  document.getElementById('dailyPieTipPct').textContent=pieData[idx].pct;
  tip.classList.add('show')}
function hidePieTooltip(){var tip=document.getElementById('dailyPieTooltip');if(tip)tip.classList.remove('show')}
function initDailyTreemap(){
  var el=document.getElementById('dailyTreemap');
  if(!el||typeof echarts==='undefined')return;
  var chart=echarts.init(el);
  // 按违规数量降序排列
  var data=[
    {name:'55E5N',value:22,channels:[{name:'拼多多',value:7},{name:'京东',value:6},{name:'淘天',value:5},{name:'抖音',value:4}]},
    {name:'75E8N Pro',value:16,channels:[{name:'拼多多',value:5},{name:'京东',value:4},{name:'淘天',value:4},{name:'抖音',value:3}]},
    {name:'65E5N Pro',value:14,channels:[{name:'京东',value:5},{name:'拼多多',value:4},{name:'淘天',value:3},{name:'抖音',value:2}]},
    {name:'65WS8Q',value:10,channels:[{name:'京东',value:5},{name:'淘天',value:3},{name:'拼多多',value:2}]},
    {name:'85E8K',value:8,channels:[{name:'京东',value:4},{name:'拼多多',value:2},{name:'淘天',value:2}]}
  ].sort(function(a,b){return b.value-a.value});

  // 青绿色系纯色，从深到浅（违规数量越大颜色越深）
  var tealColors=[
    {bg:'#0D9488',text:'#FFFFFF'},
    {bg:'#14B8A6',text:'#FFFFFF'},
    {bg:'#2DD4BF',text:'#0F766E'},
    {bg:'#5EEAD4',text:'#0F766E'},
    {bg:'#99F6E4',text:'#0F766E'}
  ];

  function buildTreeData(items){
    return items.map(function(item,i){
      var c=tealColors[i%tealColors.length];
      return {
        name:item.name,
        value:item.value,
        itemStyle:{
          color:c.bg,
          borderColor:'#fff',
          borderWidth:2,
          gapWidth:8,
          borderRadius:10
        },
        label:{
          color:c.text,
          rich:{
            name:{color:c.text},
            val:{color:c.text},
            unit:{color:c.text}
          }
        }
      };
    });
  }
  chart.setOption({
    grid:{top:0,bottom:0,left:0,right:0},
    tooltip:{
      formatter:function(info){
        var modelName=info.name;
        var modelData=data.find(function(d){return d.name===modelName});
        if(!modelData) return '<b>'+modelName+'</b><br/>违规总数：'+info.value+' 个';
        var lines=['<b style="font-size:13px">'+modelName+'</b>'];
        modelData.channels.forEach(function(c){
          lines.push(c.name+'：'+c.value+' 条');
        });
        lines.push('<span style="opacity:.4">——————</span>');
        lines.push('<b>合计：'+modelData.value+' 个</b>');
        return lines.join('<br/>');
      }
    },
    series:[{
      type:'treemap',
      roam:false,
      nodeClick:false,
      breadcrumb:{show:false},
      top:0,
      left:0,
      right:0,
      bottom:0,
      width:'100%',
      height:'100%',
      label:{
        show:true,
        position:'insideTopLeft',
        distance:14,
        formatter:function(params){
          return '{name|'+params.name+'}\n{val|'+params.value+'}{unit|个}';
        },
        lineHeight:28,
        overflow:'none',
        rich:{
          name:{fontSize:14,fontWeight:600,padding:[0,0,4,0]},
          val:{fontSize:24,fontWeight:800,padding:[2,0,0,0]},
          unit:{fontSize:12,fontWeight:500,opacity:.85,padding:[2,0,0,4]}
        }
      },
      upperLabel:{show:false},
      itemStyle:{
        borderColor:'#fff',
        borderWidth:2,
        gapWidth:8,
        borderRadius:10
      },
      levels:[
        {
          itemStyle:{
            borderColor:'#fff',
            borderWidth:2,
            gapWidth:8,
            borderRadius:10
          }
        }
      ],
      // 调整宽高比，给小矩形更多横向空间，避免文字被截断
      squareRatio:0.8,
      data:buildTreeData(data)
    }]
  });
  // 自适应容器大小
  setTimeout(function(){chart.resize()},100);
  var ro=new ResizeObserver(function(){chart.resize()});
  ro.observe(el);
}
document.addEventListener('DOMContentLoaded',function(){renderRivalPriceAlertTable('today');initDailyTreemap();if(typeof renderDualAxisChart==='function')renderDualAxisChart(0);if(typeof renderDailyTrendChart==='function')renderDailyTrendChart('week7');if(typeof refreshRivalModelSelect==='function')refreshRivalModelSelect()});
function newChat(){openCompetitor(document.querySelector('[data-page=competitor]'));document.querySelector('.model-input').focus();document.querySelector('.model-input').select();showToast('请输入我品型号开始新的竞品分析')}
function openHistory(el){openCompetitor(document.querySelector('[data-page=competitor]'));showToast('已恢复历史分析：'+el.textContent.trim().slice(0,28))}
document.querySelectorAll('.modal-mask').forEach(m=>m.addEventListener('click',e=>{if(e.target===m)m.classList.remove('show')}));
document.addEventListener('click',e=>{const s=document.querySelector('.notify-search');const sug=document.getElementById('notifySuggest');if(sug&&s&&!s.contains(e.target))sug.classList.remove('show')});



// SMART_REPORT_CENTER_JS_V3
const smartReports=window.gtmRecords.smartReports;
let smartReportView='list',smartReportPage=1,smartReportStatFilter='',currentSmartReportId=1;
function smartReportStatusClass(status){if(status==='已发布')return 'published';if(status==='已归档')return 'archived';if(status==='数据更新待确认')return 'updated';return 'pending'}
function updateSmartReportStats(){document.getElementById('reportStatAll').textContent=smartReports.length;document.getElementById('reportStatWeek').textContent=smartReports.filter(function(r){return r.week}).length;document.getElementById('reportStatPending').textContent=smartReports.filter(function(r){return r.status.indexOf('确认')>-1}).length;document.getElementById('reportStatPublished').textContent=smartReports.filter(function(r){return r.status==='已发布'}).length}

// SMART_REPORT_CENTER_JS_PART2
function getFilteredSmartReports(){
 var q=document.getElementById('reportSearch').value.trim().toLowerCase(),type=document.getElementById('reportTypeFilter').value,cycle=document.getElementById('reportCycleFilter').value,category=document.getElementById('reportCategoryFilter').value,status=document.getElementById('reportStatusFilter').value,sort=document.getElementById('reportSort').value;
 var rows=smartReports.filter(function(r){var textOk=!q||(r.title+r.summary+r.category+r.channels).toLowerCase().indexOf(q)>-1;var statOk=!smartReportStatFilter||(smartReportStatFilter==='本周更新'?r.week:(smartReportStatFilter==='待人工确认'?r.status.indexOf('确认')>-1:r.status===smartReportStatFilter));return textOk&&statOk&&(!type||r.type===type)&&(!cycle||r.cycle===cycle)&&(!category||r.category===category)&&(!status||r.status===status)});
 if(sort==='title')rows.sort(function(a,b){return a.title.localeCompare(b.title,'zh-CN')});if(sort==='priority')rows.sort(function(a,b){return (b.status.indexOf('确认')>-1)-(a.status.indexOf('确认')>-1)});if(sort==='cycle')rows.sort(function(a,b){return a.cycle.localeCompare(b.cycle,'zh-CN')});return rows
}
function smartReportRowHtml(r){
 return '<article class="report-row-v3" onclick="openSmartReport('+r.id+')"><div class="report-doc-icon"><svg viewBox="0 0 24 24"><path d="M6 3h9l3 3v15H6z"/><path d="M15 3v4h4M9 11h6M9 15h6"/></svg></div><div class="report-main-v3"><h3>'+escapeSampleText(r.title)+'</h3><p>'+escapeSampleText(r.summary)+'</p><div class="report-tags-v3"><span class="report-tag-v3 type">'+r.type+'</span><span class="report-tag-v3 cycle">'+r.cycle+'</span><span class="report-tag-v3">'+r.category+'</span><span class="report-tag-v3">'+r.channels+'</span><span class="report-tag-v3">'+r.version+'</span></div></div><div class="report-schedule-v3"><b>数据周期：'+r.period+'</b><span>'+r.next+'</span></div><div><span class="report-status-v3 '+smartReportStatusClass(r.status)+'">'+r.status+'</span></div><div class="report-owner-v3"><b>'+r.owner+' · '+r.updated+'</b><span>负责人 / 更新时间</span></div><div class="report-actions-v3"><button class="btn sm" onclick="event.stopPropagation();openSmartReport('+r.id+')">查看</button></div></article>'
}
function renderSmartReports(){
 var rows=getFilteredSmartReports(),pageSize=smartReportView==='list'?5:4,totalPages=Math.max(1,Math.ceil(rows.length/pageSize));if(smartReportPage>totalPages)smartReportPage=totalPages;
 var shown=rows.slice((smartReportPage-1)*pageSize,smartReportPage*pageSize),container=document.getElementById('smartReportContainer');container.className=smartReportView==='grid'?'smart-report-grid':'smart-report-list';container.innerHTML=shown.length?shown.map(smartReportRowHtml).join(''):'<div class="report-empty">没有符合当前条件的报告，请调整筛选条件</div>';
 document.getElementById('reportResultCount').textContent=rows.length;document.getElementById('reportPageInfo').textContent='第 '+smartReportPage+' / '+totalPages+' 页 · 每页 '+pageSize+' 条';
 var controls='<button class="page-btn" onclick="changeSmartReportPage(-1)" '+(smartReportPage===1?'disabled':'')+'>‹</button>';for(var i=1;i<=totalPages;i++)controls+='<button class="page-btn '+(i===smartReportPage?'active':'')+'" onclick="goSmartReportPage('+i+')">'+i+'</button>';controls+='<button class="page-btn" onclick="changeSmartReportPage(1)" '+(smartReportPage===totalPages?'disabled':'')+'>›</button>';document.getElementById('reportPageControls').innerHTML=controls;
 var hints=[];if(smartReportStatFilter)hints.push(smartReportStatFilter);['reportTypeFilter','reportCycleFilter','reportCategoryFilter','reportStatusFilter'].forEach(function(id){if(document.getElementById(id).value)hints.push(document.getElementById(id).value)});document.getElementById('reportActiveHint').textContent=hints.length?' · 当前筛选：'+hints.join(' / '):'';updateSmartReportStats()
}
function applySmartReportFilters(){smartReportPage=1;renderSmartReports()}
function setSmartReportStatus(status,button){smartReportStatFilter=status;smartReportPage=1;document.querySelectorAll('.report-stat-v3').forEach(function(b){b.classList.toggle('active',b===button)});renderSmartReports()}
function setSmartReportView(view,button){smartReportView=view;smartReportPage=1;document.querySelectorAll('.report-view-btn').forEach(function(b){b.classList.toggle('active',b===button)});renderSmartReports()}
function changeSmartReportPage(delta){smartReportPage+=delta;renderSmartReports()}
function goSmartReportPage(page){smartReportPage=page;renderSmartReports()}
function resetSmartReportFilters(){smartReportStatFilter='';document.getElementById('reportSearch').value='';['reportTypeFilter','reportCycleFilter','reportCategoryFilter','reportStatusFilter'].forEach(function(id){document.getElementById(id).value=''});document.getElementById('reportSort').value='recent';document.querySelectorAll('.report-stat-v3').forEach(function(b){b.classList.toggle('active',b.dataset.stat==='')});smartReportPage=1;renderSmartReports()}

// SMART_REPORT_CENTER_JS_PART3
function openSmartReport(id){
 currentSmartReportId=id;var r=smartReports.find(function(x){return x.id===id});if(!r)return;
 document.getElementById('detailModalTitle').textContent=r.title;document.getElementById('detailModalSub').textContent=r.version+' · '+r.updated+'更新 · '+r.owner;document.getElementById('detailReportTitle').textContent=r.title;document.getElementById('detailReportMeta').textContent='数据周期 '+r.period+'　'+r.channels+' · '+r.category+'　报告版本 '+r.version;document.getElementById('detailReportSummary').textContent=r.summary;
 document.getElementById('detailKpiSku').textContent=r.sku;document.getElementById('detailKpiChange').textContent=r.change;document.getElementById('detailKpiAction').textContent=r.actions;document.getElementById('reportEditTitle').value=r.title;document.getElementById('reportEditOwner').value=r.owner;document.getElementById('reportEditTags').value=r.type+'、'+r.cycle+'、'+r.category+'、'+r.channels;document.getElementById('reportEditSummary').value=r.summary;document.getElementById('exportFileName').value=r.title.replace(/[（）\s]/g,'_')+'_'+r.version;document.getElementById('detailConfirmBtn').style.display=r.status.indexOf('确认')>-1?'inline-flex':'none';setReportDetailMode('view');openModal('reportDetailModal')
}
function setReportDetailMode(mode){var edit=mode==='edit';document.getElementById('reportPreviewSheet').style.display=edit?'none':'block';document.getElementById('reportEditPanel').classList.toggle('show',edit);document.getElementById('detailViewBtn').classList.toggle('active',!edit);document.getElementById('detailEditBtn').classList.toggle('active',edit);document.getElementById('detailSaveBtn').style.display=edit?'inline-flex':'none'}
function saveSmartReportEdit(){var r=smartReports.find(function(x){return x.id===currentSmartReportId});if(!r)return;r.title=document.getElementById('reportEditTitle').value.trim()||r.title;r.owner=document.getElementById('reportEditOwner').value.trim()||r.owner;r.summary=document.getElementById('reportEditSummary').value.trim()||r.summary;r.version='V'+(parseFloat(r.version.slice(1))+0.1).toFixed(1);r.updated='刚刚';r.status='待人工确认';renderSmartReports();openSmartReport(r.id);showToast('已保存为 '+r.version+'，进入待人工确认')}
function confirmSmartReportById(id){currentSmartReportId=id;confirmSmartReport()}
function confirmSmartReport(){var r=smartReports.find(function(x){return x.id===currentSmartReportId});if(!r)return;r.status='已发布';r.updated='刚刚';r.week=true;closeModal('reportDetailModal');renderSmartReports();showToast('报告已确认发布，并按订阅范围推送')}
function completeReportExport(){var fmtInput=document.querySelector('input[name=exportFormat]:checked');var format=fmtInput?fmtInput.value:'PDF';closeModal('exportReportModal');showToast(format+'报告生成中，完成后将自动下载')}
function openExportModal(pageName){var input=document.getElementById('exportFileName');if(input){var d=new Date();var y=d.getFullYear();var m=String(d.getMonth()+1).padStart(2,'0');var day=String(d.getDate()).padStart(2,'0');input.value=pageName+'_'+y+m+day;}var radios=document.querySelectorAll('input[name=exportFormat]');if(radios&&radios.length){radios[0].checked=true;}openModal('exportReportModal');}
function copyReportLink(){showToast('受控访问链接已复制')}
function completeReportShare(){var scope=document.getElementById('shareScope').value,expiry=document.getElementById('shareExpiry').value;closeModal('shareReportModal');showToast('已按“'+scope+' / '+expiry+'”发送到信鸿')}
function createReportSubscription(){closeModal('subscriptionModal');showToast('订阅报告任务已创建，首次生成后进入待人工确认')}
function initSmartReports(){renderSmartReports()}

// SUBSCRIPTION_REPORT_WORKSPACE_JS_V4
let reportAutoSaveTimer=null;
function openSmartReport(id){
 currentSmartReportId=id;var r=smartReports.find(function(x){return x.id===id});if(!r)return;
 document.getElementById('detailModalTitle').textContent=r.title;document.getElementById('detailModalSub').textContent=r.version+' · '+r.updated+'更新 · '+r.owner;document.getElementById('detailReportTitle').textContent=r.title;document.getElementById('detailReportMeta').textContent='数据周期 '+r.period+'　'+r.channels+' · '+r.category+'　报告版本 '+r.version;document.getElementById('detailReportSummary').textContent=r.summary;
 document.getElementById('detailKpiSku').textContent=r.sku;document.getElementById('detailKpiChange').textContent=r.change;document.getElementById('detailKpiAction').textContent=r.actions;document.getElementById('exportFileName').value=r.title.replace(/[（）\s]/g,'_')+'_'+r.version;document.getElementById('detailConfirmBtn').style.display=r.status.indexOf('确认')>-1?'inline-flex':'none';document.getElementById('reportSaveState').textContent='已自动保存';document.getElementById('reportSaveState').classList.remove('saving');
 document.getElementById('reportAiBody').innerHTML='<div class="report-ai-msg ai"><b>想怎么调整这份报告？</b>你可以直接修改左侧浅绿色区域，也可以告诉我需要精简、补充或重组的内容。</div>';document.getElementById('reportAssistantInput').value='';setReportDetailMode('view');openModal('reportDetailModal')
}
function setReportDetailMode(mode){
 var edit=mode==='edit',shell=document.getElementById('reportWorkspaceShell');shell.classList.toggle('edit',edit);shell.classList.toggle('view',!edit);document.getElementById('detailViewBtn').classList.toggle('active',!edit);document.getElementById('detailEditBtn').classList.toggle('active',edit);document.getElementById('detailSaveBtn').style.display=edit?'inline-flex':'none';
 document.querySelectorAll('#reportPreviewSheet [data-report-editable="true"]').forEach(function(el){el.contentEditable=edit?'true':'false'});if(edit)setTimeout(function(){document.getElementById('reportAssistantInput').focus()},80)
}
function queueReportAutoSave(){var state=document.getElementById('reportSaveState');state.textContent='正在自动保存…';state.classList.add('saving');clearTimeout(reportAutoSaveTimer);reportAutoSaveTimer=setTimeout(function(){state.textContent='已自动保存';state.classList.remove('saving')},450)}
function saveSmartReportEdit(){
 var r=smartReports.find(function(x){return x.id===currentSmartReportId});if(!r)return;r.title=document.getElementById('detailReportTitle').textContent.trim()||r.title;r.summary=document.getElementById('detailReportSummary').textContent.trim()||r.summary;r.version='V'+(parseFloat(r.version.slice(1))+0.1).toFixed(1);r.updated='刚刚';r.status='待人工确认';document.getElementById('detailModalTitle').textContent=r.title;document.getElementById('detailModalSub').textContent=r.version+' · 刚刚更新 · '+r.owner;document.getElementById('detailReportMeta').textContent='数据周期 '+r.period+'　'+r.channels+' · '+r.category+'　报告版本 '+r.version;
 var timeline=document.getElementById('detailVersionTimeline');timeline.insertAdjacentHTML('afterbegin','<div class="version-item"><b>'+r.version+'</b><span>人工编辑与AI协同修改，已保存为新版本</span><span>刚刚</span></div>');document.getElementById('detailConfirmBtn').style.display='inline-flex';setReportDetailMode('view');renderSmartReports();showToast('已保存为 '+r.version+'，进入待人工确认')
}
function appendReportAiMessage(role,html){var body=document.getElementById('reportAiBody');body.insertAdjacentHTML('beforeend','<div class="report-ai-msg '+role+'">'+(role==='user'?escapeSampleText(html):html)+'</div>');body.scrollTop=body.scrollHeight}
function sendReportAssistant(){var input=document.getElementById('reportAssistantInput'),q=input.value.trim();if(!q)return;input.value='';askReportAssistant(q)}
function askReportAssistant(q){
 appendReportAiMessage('user',q);var summary=document.getElementById('detailReportSummary'),reply='已根据你的要求更新左侧报告，并保留原版本。';
 if(q.indexOf('精简')>-1){var parts=summary.textContent.split('；');summary.textContent=parts.slice(0,2).join('；')+'。';reply='<b>已精简核心结论</b>保留行业变化、竞品动作和我品影响三项关键信息。'}
 else if(q.indexOf('价格风险')>-1){summary.textContent=summary.textContent.replace(/。$/,'')+'；需关注核心竞品持续降价对我品均价和毛利安全垫的双重压力。';reply='<b>已补充价格风险</b>新增竞品降价、均价承压和毛利安全垫提示。'}
 else if(q.indexOf('行动')>-1){var action=document.querySelector('#reportPreviewSheet .decision-action:nth-child(2) span');if(action)action.textContent='完成重点竞品价格弹性测算，明确跟价上限、毛利底线及触发条件';reply='<b>已强化行动建议</b>补充了执行边界、决策条件和业务责任。'}
 else if(q.indexOf('数据')>-1){var proof=document.querySelector('#reportPreviewSheet .report-data-proof');if(proof&&!proof.querySelector('[data-ai-proof]'))proof.insertAdjacentHTML('beforeend','<span class="proof-chip" data-ai-proof><b>竞品上新监测</b> 近7天新增3款</span>');reply='<b>已增加数据依据</b>补充竞品上新监测口径，并保留数据更新时间。'}
 else{summary.textContent=summary.textContent.replace(/。$/,'')+'；补充说明：'+q+'。';reply='<b>已同步修改</b>我把你的要求补充进核心结论，可继续直接编辑左侧文字。'}
 queueReportAutoSave();document.getElementById('reportPreviewSheet').animate([{boxShadow:'0 0 0 0 rgba(0,100,250,0)'},{boxShadow:'0 0 0 5px rgba(0,100,250,.18)'},{boxShadow:'0 4px 18px rgba(32,38,60,.08)'}],{duration:650});setTimeout(function(){appendReportAiMessage('ai',reply)},350)
}

// SUBSCRIPTION_REPORT_MODE_FIX_V4
function setReportDetailMode(mode){
 var edit=mode==='edit',shell=document.getElementById('reportWorkspaceShell');shell.classList.toggle('edit',edit);shell.classList.toggle('view',!edit);document.getElementById('detailViewBtn').classList.toggle('active',!edit);document.getElementById('detailEditBtn').classList.toggle('active',edit);document.getElementById('detailSaveBtn').style.display=edit?'inline-flex':'none';document.querySelectorAll('#reportPreviewSheet [data-report-editable="true"]').forEach(function(el){el.contentEditable=edit?'true':'false'});var canvas=document.querySelector('#reportDetailModal .report-canvas-v4');if(!edit&&canvas)canvas.scrollTop=0;if(edit)setTimeout(function(){document.getElementById('reportAssistantInput').focus({preventScroll:true})},80)
}
// HOME_INSIGHT_BOARD_JS_V1
const homeTrendCatalog=window.gtmRecords.homeTrendCatalog;
const homeTrendDates=window.gtmRecords.homeTrendDates;
const homeTrendWave=window.gtmRecords.homeTrendWave;
const homePriceWave=window.gtmRecords.homePriceWave;
let homeTrendCategory='空调',homeTrendModel=0;
function switchHomePanel(name,button){
  document.querySelectorAll('#page-chat .insight-tab').forEach(function(t){t.classList.toggle('active',t===button)});
  document.querySelectorAll('#page-chat .insight-panel').forEach(function(p){p.classList.toggle('active',p.id==='home-panel-'+name)});
}
function switchTrendCategory(category,button){
  homeTrendCategory=category;homeTrendModel=0;
  document.querySelectorAll('#page-chat .category-btn').forEach(function(b){b.classList.toggle('active',b===button)});
  renderHomeModelButtons();renderHomeTrend();
}
function selectTrendModel(index,button){
  homeTrendModel=index;
  document.querySelectorAll('#homeModelSwitch .model-btn').forEach(function(b){b.classList.toggle('active',b===button)});
  renderHomeTrend();
}
function renderHomeModelButtons(){
  var holder=document.getElementById('homeModelSwitch');if(!holder)return;
  holder.innerHTML=homeTrendCatalog[homeTrendCategory].map(function(m,i){return '<button class="model-btn '+(i===homeTrendModel?'active':'')+'" onclick="selectTrendModel('+i+',this)">'+m.name+'</button>'}).join('');
}
function homeTrendSeries(model){
  var units=[],price=[],revenue=[];
  for(var i=0;i<homeTrendDates.length;i++){
    var shifted=homeTrendWave[(i+model.seed)%homeTrendWave.length];
    var u=Math.round(model.units*(.88+shifted+(model.seed-2)*.008));
    var p=Math.round(model.price*(1+homePriceWave[(i+model.seed)%homePriceWave.length]));
    units.push(u);price.push(p);revenue.push(Math.round(u*p/1000)/10);
  }
  return {units:units,price:price,revenue:revenue};
}
function homeChange(values){
  var first=values.slice(0,6).reduce(function(a,b){return a+b},0);
  var last=values.slice(6).reduce(function(a,b){return a+b},0);
  return (last/first-1)*100;
}
function homeTrendLabel(value){
  var sign=value>=0?'▲ +':'▼ ';
  return sign+value.toFixed(1)+'%';
}
function renderHomeTrend(){
  var model=homeTrendCatalog[homeTrendCategory][homeTrendModel],series=homeTrendSeries(model);
  var totalUnits=series.units.reduce(function(a,b){return a+b},0);
  var totalRevenue=series.revenue.reduce(function(a,b){return a+b},0);
  var weightedPrice=Math.round(totalRevenue*10000/totalUnits);
  var tu=document.getElementById('trendUnits');if(tu)tu.textContent=totalUnits.toLocaleString()+' 台';
  var tr=document.getElementById('trendRevenue');if(tr)tr.textContent='¥'+totalRevenue.toFixed(1)+' 万';
  var tp=document.getElementById('trendPrice');if(tp)tp.textContent='¥'+weightedPrice.toLocaleString();
  var unitChange=homeChange(series.units),revChange=homeChange(series.revenue),priceChange=homeChange(series.price);
  [['trendUnitsChange',unitChange],['trendRevenueChange',revChange],['trendPriceChange',priceChange]].forEach(function(item){
    var el=document.getElementById(item[0]);if(!el)return;el.textContent=homeTrendLabel(item[1]);el.style.color=item[1]>=0?'var(--success)':'var(--danger)';
  });
  var tt=document.getElementById('trendChartTitle');if(tt)tt.textContent='海信 '+model.name+' · 销量 / 销额 / 均价趋势';
  drawHomeTrendChart(series);
}
function drawHomeTrendChart(series){
  var svg=document.getElementById('homeTrendChart');if(!svg)return;
  var width=980,height=270,left=48,right=20,top=24,bottom=38,plotW=width-left-right,plotH=height-top-bottom;
  function points(values){
    var min=Math.min.apply(null,values),max=Math.max.apply(null,values),span=max-min||1;
    return values.map(function(v,i){return {x:left+i*plotW/(values.length-1),y:top+(max-v)/span*plotH,value:v}});
  }
  var sets=[
    {key:'units',name:'销量',color:'#0064fa',suffix:' 台',points:points(series.units)},
    {key:'revenue',name:'销额',color:'#5B7CFA',suffix:' 万元',points:points(series.revenue)},
    {key:'price',name:'均价',color:'#F59E0B',suffix:' 元',points:points(series.price)}
  ];
  var out='<defs><linearGradient id="homeArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0064fa" stop-opacity=".15"/><stop offset="1" stop-color="#0064fa" stop-opacity="0"/></linearGradient></defs>';
  for(var g=0;g<5;g++){var gy=top+g*plotH/4;out+='<line x1="'+left+'" y1="'+gy+'" x2="'+(width-right)+'" y2="'+gy+'" stroke="#e9edf0" stroke-width="1"/>';}
  homeTrendDates.forEach(function(date,i){var x=left+i*plotW/(homeTrendDates.length-1);if(i%2===0||i===homeTrendDates.length-1)out+='<text x="'+x+'" y="'+(height-13)+'" text-anchor="middle" font-size="10" fill="#8f99a8">'+date+'</text>';});
  sets.forEach(function(set){
    var p=set.points.map(function(v){return v.x.toFixed(1)+','+v.y.toFixed(1)}).join(' ');
    out+='<polyline points="'+p+'" fill="none" stroke="'+set.color+'" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>';
    set.points.forEach(function(v,i){
      var display=set.key==='revenue'?v.value.toFixed(1):Math.round(v.value).toLocaleString();
      out+='<circle cx="'+v.x+'" cy="'+v.y+'" r="4" fill="#fff" stroke="'+set.color+'" stroke-width="2"><title>'+homeTrendDates[i]+' · '+set.name+'：'+display+set.suffix+'</title></circle>';
    });
  });
  out+='<text x="8" y="'+(top+5)+'" font-size="9" fill="#9aa3af">高</text><text x="8" y="'+(top+plotH)+'" font-size="9" fill="#9aa3af">低</text>';
  svg.innerHTML=out;
}
function initHomeTrend(){renderHomeModelButtons();renderHomeTrend();}
// HOME_LANDING_REDESIGN_V6_DATA_A
homeTrendCatalog['空调'].push({name:'1.5匹 S510-X1',units:306,price:3299,seed:5},{name:'3匹 X610-X1',units:152,price:7299,seed:6},{name:'2匹 E510-X2',units:219,price:5199,seed:7});
homeTrendCatalog['冰箱'].push({name:'508L WTDGV',units:264,price:5299,seed:5},{name:'452L WTDGVB',units:337,price:3699,seed:6},{name:'500L WFK1DPQ',units:202,price:6099,seed:7});
homeTrendCatalog['洗衣机'].push({name:'10kg 墨月 XQG100-M',units:315,price:2799,seed:5},{name:'12kg 热泵洗烘 XQG120-H',units:136,price:6299,seed:6},{name:'10kg 超声波 XQG100-U',units:198,price:4599,seed:7});
homeTrendCatalog['电视'].push({name:'55E7Q',units:465,price:2499,seed:5},{name:'98E7N Pro',units:84,price:11999,seed:6},{name:'75E7Q',units:228,price:4799,seed:7});
const homeLaunchCatalog=window.gtmRecords.homeLaunchCatalog;
// HOME_LANDING_REDESIGN_V6_DATA_B
const homeWarningCatalog=window.gtmRecords.homeWarningCatalog;
// HOME_LANDING_REDESIGN_V6_LOGIC
let homeTrendSlots=[0,1,2,3,4],homeTrendActiveSlot=0;
function switchHomeCategory(category){homeTrendCategory=category;homeTrendSlots=[0,1,2,3,4];homeTrendActiveSlot=0;var el=document.getElementById('homeTrendCategorySelect');if(el)el.value=category;renderHomeModelCards();renderHomeTrend();renderHomeLaunches();renderHomeWarnings();}
function switchTrendCategory(category){switchHomeCategory(category)}
function selectTrendSlot(slot,card){homeTrendActiveSlot=slot;document.querySelectorAll('#homeModelSwitch .model-slot-card').forEach(function(el){el.classList.toggle('active',el===card)});renderHomeTrend();}
function changeTrendSlot(slot,value){var next=Number(value),old=homeTrendSlots[slot],duplicate=homeTrendSlots.indexOf(next);if(duplicate>-1&&duplicate!==slot)homeTrendSlots[duplicate]=old;homeTrendSlots[slot]=next;homeTrendActiveSlot=slot;renderHomeModelCards();renderHomeTrend();}
function renderHomeModelCards(){var holder=document.getElementById('homeModelSwitch');if(!holder)return;var catalog=homeTrendCatalog[homeTrendCategory];holder.innerHTML=homeTrendSlots.map(function(modelIndex,slot){var options=catalog.map(function(item,i){var occupied=homeTrendSlots.indexOf(i)>-1&&i!==modelIndex;return '<option value="'+i+'" '+(i===modelIndex?'selected':'')+' '+(occupied?'disabled':'')+'>'+item.name+'</option>'}).join('');return '<div class="model-slot-card '+(slot===homeTrendActiveSlot?'active':'')+'" onclick="selectTrendSlot('+slot+',this)"><div class="model-card-select"><select aria-label="选择核心型号'+(slot+1)+'" onclick="event.stopPropagation();selectTrendSlot('+slot+',this.closest(&quot;.model-slot-card&quot;))" onchange="event.stopPropagation();changeTrendSlot('+slot+',this.value)">'+options+'</select><i>⌄</i></div></div>'}).join('');updateModelFilterLabel();}
// HOME_MODEL_FILTER_V20_LOGIC: 型号模糊多选（必须选满5个）
let modelFilterDraft=[];
function updateModelFilterLabel(){var el=document.getElementById('modelFilterLabel');if(el)el.textContent='已选 '+homeTrendSlots.length+' 个型号';}
function toggleModelFilter(e){if(e)e.stopPropagation();var box=document.getElementById('homeModelFilter');if(!box)return;if(box.classList.contains('open')){closeModelFilter();return;}modelFilterDraft=homeTrendSlots.slice();var s=document.getElementById('modelFilterSearch');if(s)s.value='';box.classList.add('open');renderModelFilterOptions();}
function closeModelFilter(){var box=document.getElementById('homeModelFilter');if(box)box.classList.remove('open');}
function toggleModelFilterOpt(i){var pos=modelFilterDraft.indexOf(i);if(pos>-1){modelFilterDraft.splice(pos,1);}else{if(modelFilterDraft.length>=5)return;modelFilterDraft.push(i);}renderModelFilterOptions();}
function renderModelFilterOptions(){
  var list=document.getElementById('modelFilterList');if(!list)return;
  var catalog=homeTrendCatalog[homeTrendCategory];
  var kw=(document.getElementById('modelFilterSearch').value||'').trim().toLowerCase();
  var full=modelFilterDraft.length>=5;
  var rows=catalog.map(function(item,i){return {item:item,i:i}}).filter(function(o){return !kw||o.item.name.toLowerCase().indexOf(kw)>-1;});
  if(!rows.length){list.innerHTML='<div class="model-filter-empty">未找到匹配「'+kw+'」的型号</div>';}
  else{list.innerHTML=rows.map(function(o){var checked=modelFilterDraft.indexOf(o.i)>-1;var disabled=!checked&&full;return '<div class="model-filter-opt '+(checked?'checked':'')+(disabled?' disabled':'')+'" onclick="'+(disabled?'':'toggleModelFilterOpt('+o.i+')')+'"><span class="box">'+(checked?'✓':'')+'</span><span class="m-name">'+o.item.name+'</span></div>'}).join('');}
  var full5=modelFilterDraft.length===5;
  var cnt=document.getElementById('modelFilterCount');if(cnt)cnt.textContent=modelFilterDraft.length+'/5';
  var hint=document.getElementById('modelFilterHint');if(hint){hint.textContent=full5?'已选满 5 个，可点击确定':'还需选择 '+(5-modelFilterDraft.length)+' 个型号';hint.classList.toggle('warn',!full5);}
  var apply=document.getElementById('modelFilterApply');if(apply)apply.disabled=!full5;
}
function applyModelFilter(){if(modelFilterDraft.length!==5)return;homeTrendSlots=modelFilterDraft.slice();homeTrendActiveSlot=0;closeModelFilter();renderHomeModelCards();renderHomeTrend();}
document.addEventListener('mousedown',function(e){var box=document.getElementById('homeModelFilter');if(box&&box.classList.contains('open')&&!e.target.closest('#homeModelFilter'))closeModelFilter();});
function renderHomeTrend(){var model=homeTrendCatalog[homeTrendCategory][homeTrendSlots[homeTrendActiveSlot]],series=homeTrendSeries(model),totalUnits=series.units.reduce(function(a,b){return a+b},0),totalRevenue=series.revenue.reduce(function(a,b){return a+b},0),weightedPrice=Math.round(totalRevenue*10000/totalUnits);var tu=document.getElementById('trendUnits');if(tu)tu.textContent=totalUnits.toLocaleString()+' 台';var tr=document.getElementById('trendRevenue');if(tr)tr.textContent='¥'+totalRevenue.toFixed(1)+' 万';var tp=document.getElementById('trendPrice');if(tp)tp.textContent='¥'+weightedPrice.toLocaleString();[['trendUnitsChange',homeChange(series.units)],['trendRevenueChange',homeChange(series.revenue)],['trendPriceChange',homeChange(series.price)]].forEach(function(item){var el=document.getElementById(item[0]);if(!el)return;el.textContent=homeTrendLabel(item[1]);el.style.color=item[1]>=0?'var(--success)':'var(--danger)'});var tt=document.getElementById('trendChartTitle');if(tt)tt.textContent='海信 '+model.name+' · 销量 / 销额 / 均价趋势';drawHomeTrendChart(series);}
function renderHomeLaunches(){var list=document.getElementById('homeLaunchList'),items=homeLaunchCatalog[homeTrendCategory];if(!list)return;list.innerHTML=items.map(function(x,i){return '<div class="home-table-row"><span><b>'+x.b+'</b></span><span class="model-name">'+x.m+'</span><span>'+x.d+'</span><span><b>'+x.p+'</b></span><button class="notice-action" onclick="openCompetitorWiki('+i+')">竞品百科</button></div>'}).join('');document.getElementById('homeLaunchBubble').textContent=items.length;}
function renderHomeWarnings(){var list=document.getElementById('homeWarningList'),items=homeWarningCatalog[homeTrendCategory],classes={严重:'red',紧急:'orange',一般:'gray'};if(!list)return;list.innerHTML=items.map(function(x,i){return '<div class="home-table-row"><span class="model-name">'+x.m+'</span><span>'+x.ch+'</span><span><i class="pill '+classes[x.lv]+'">'+x.lv+'</i></span><span class="desc">'+x.desc+'</span><span>'+x.t+'</span><button class="notice-action" onclick="openHomeEvidence('+i+')">查看证据</button></div>'}).join('');document.getElementById('homeWarningBubble').textContent=items.length;}
function openCompetitorWiki(index){var x=homeLaunchCatalog[homeTrendCategory][index];document.getElementById('wikiModalTitle').textContent=x.b+' '+x.m+' · 竞品百科';document.getElementById('wikiBrand').textContent=x.b.slice(0,2);document.getElementById('wikiModel').textContent=x.m;document.getElementById('wikiPosition').textContent=x.pos;document.getElementById('wikiStatus').textContent=x.st;document.getElementById('wikiUnits').textContent=x.u;document.getElementById('wikiRevenue').textContent=x.r;document.getElementById('wikiPrice').textContent=x.p;document.getElementById('wikiLaunchDate').textContent=x.d;document.getElementById('wikiSellingPoints').innerHTML=x.sell.map(function(v){return '<span>'+v+'</span>'}).join('');document.getElementById('wikiProductInfo').innerHTML='<dt>品牌</dt><dd>'+x.b+'</dd><dt>产品型号</dt><dd>'+x.sku+'</dd><dt>品类</dt><dd>'+homeTrendCategory+'</dd><dt>市场定位</dt><dd>'+x.pos+'</dd>';document.getElementById('wikiChannel').textContent=x.s;document.getElementById('wikiImpact').textContent=x.impact;openModal('competitorWikiModal');}
const homeDefaultEvidence=window.gtmRecords.homeDefaultEvidence;
function populateHomeEvidence(x){openEvidence(x);}
function openHomeEvidence(index){openEvidence(homeWarningCatalog[homeTrendCategory][index]);}
function initHomeTrend(){renderHomeModelCards();renderHomeTrend();renderHomeLaunches();renderHomeWarnings();}
// HOME_FLOW_TREND_V10_LOGIC
function makeHomeTrendDates(days){var end=new Date(),out=[];for(var i=days-1;i>=0;i--){var d=new Date(end);d.setDate(end.getDate()-i);out.push(String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'))}return out}
function makeHomeCustomDates(startText,endText){var start=new Date(startText+'T00:00:00'),end=new Date(endText+'T00:00:00'),span=Math.round((end-start)/86400000);if(!isFinite(span)||span<0)return[];var count=Math.min(span+1,31),out=[];for(var i=0;i<count;i++){var offset=count===1?0:Math.round(i*span/(count-1)),d=new Date(start);d.setDate(start.getDate()+offset);out.push(String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'))}return out}
let homeTrendViewDates=makeHomeTrendDates(7),homeTrendCurrentSeries=null;
function homeTrendSeries(model){var units=[],price=[],revenue=[];for(var i=0;i<homeTrendViewDates.length;i++){var shifted=homeTrendWave[(i+model.seed)%homeTrendWave.length],u=Math.round(model.units*(.88+shifted+(model.seed-2)*.008)),p=Math.round(model.price*(1+homePriceWave[(i+model.seed)%homePriceWave.length]));units.push(u);price.push(p);revenue.push(Math.round(u*p/1000)/10)}return {units:units,price:price,revenue:revenue}}
function homeChange(values){var mid=Math.max(1,Math.floor(values.length/2)),first=values.slice(0,mid).reduce(function(a,b){return a+b},0)/mid,lastPart=values.slice(mid),last=lastPart.reduce(function(a,b){return a+b},0)/(lastPart.length||1);return (last/first-1)*100}
function changeHomeTrendRange(value){var pop=document.getElementById('homeCustomDatePopover');if(value==='custom'){pop.classList.add('show');return}pop.classList.remove('show');homeTrendViewDates=makeHomeTrendDates(Number(value));updateHomeTrendCaption(value==='7'?'近7天每日趋势':'近30天每日趋势');renderHomeTrend()}
function applyHomeCustomRange(){var start=document.getElementById('homeTrendStartDate').value,end=document.getElementById('homeTrendEndDate').value,dates=makeHomeCustomDates(start,end);if(!start||!end){showToast('请选择开始和结束日期');return}if(!dates.length){showToast('结束日期不能早于开始日期');return}homeTrendViewDates=dates;document.getElementById('homeTrendDateRange').value='custom';document.getElementById('homeCustomDatePopover').classList.remove('show');updateHomeTrendCaption(start.replaceAll('-','.')+' 至 '+end.replaceAll('-','.')+(dates.length<Math.round((new Date(end)-new Date(start))/86400000)+1?' · 已抽样展示':' · 每日趋势'));renderHomeTrend()}
function updateHomeTrendCaption(text){var el=document.getElementById('trendDateCaption');if(el)el.textContent=text+' · 悬停节点查看当日三个指标'}
function homeSmoothPath(points){if(!points.length)return'';var d='M '+points[0].x.toFixed(1)+' '+points[0].y.toFixed(1);for(var i=1;i<points.length;i++){var p0=points[i-1],p1=points[i],mid=(p0.x+p1.x)/2;d+=' C '+mid.toFixed(1)+' '+p0.y.toFixed(1)+', '+mid.toFixed(1)+' '+p1.y.toFixed(1)+', '+p1.x.toFixed(1)+' '+p1.y.toFixed(1)}return d}
function drawHomeTrendChart(series){var svg=document.getElementById('homeTrendChart');if(!svg)return;homeTrendCurrentSeries=series;var dates=homeTrendViewDates,width=980,height=270,left=48,right=22,top=24,bottom=36,plotW=width-left-right,plotH=height-top-bottom;function points(values){var min=Math.min.apply(null,values),max=Math.max.apply(null,values),pad=(max-min)*.12||1,min2=min-pad,max2=max+pad,span=max2-min2;return values.map(function(v,i){return{x:left+(values.length===1?plotW/2:i*plotW/(values.length-1)),y:top+(max2-v)/span*plotH,value:v}})}var sets=[{key:'units',name:'销量',color:'#00A6A6',suffix:' 台',pts:points(series.units)},{key:'revenue',name:'销额',color:'#607FF5',suffix:' 万元',pts:points(series.revenue)},{key:'price',name:'均价',color:'#F2A12D',suffix:' 元',pts:points(series.price)}],out='<defs><linearGradient id="flowUnits" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#00A6A6" stop-opacity=".20"/><stop offset="1" stop-color="#00A6A6" stop-opacity="0"/></linearGradient><linearGradient id="flowRevenue" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#607FF5" stop-opacity=".11"/><stop offset="1" stop-color="#607FF5" stop-opacity="0"/></linearGradient><filter id="flowGlow"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>';for(var g=0;g<5;g++){var gy=top+g*plotH/4;out+='<line x1="'+left+'" y1="'+gy+'" x2="'+(width-right)+'" y2="'+gy+'" class="home-grid-line"/>'}var step=Math.max(1,Math.ceil(dates.length/6));dates.forEach(function(date,i){if(i%step===0||i===dates.length-1){var x=dates.length===1?left+plotW/2:left+i*plotW/(dates.length-1);out+='<text x="'+x+'" y="'+(height-12)+'" text-anchor="middle" class="home-date-label">'+date+'</text>'}});sets.forEach(function(set,index){var d=homeSmoothPath(set.pts),area=d+' L '+set.pts[set.pts.length-1].x.toFixed(1)+' '+(top+plotH)+' L '+set.pts[0].x.toFixed(1)+' '+(top+plotH)+' Z';if(index<2)out+='<path d="'+area+'" fill="url(#flow'+(index===0?'Units':'Revenue')+')"/>';out+='<path id="homePath'+set.key+'" d="'+d+'" class="home-flow-line" stroke="'+set.color+'"/>';set.pts.forEach(function(p,i){out+='<circle cx="'+p.x+'" cy="'+p.y+'" r="2.2" fill="#fff" stroke="'+set.color+'" stroke-width="1.5" class="home-node"/>'});});out+='<line id="homeTrendHoverLine" x1="0" y1="'+top+'" x2="0" y2="'+(top+plotH)+'" class="home-hover-line"/>';var zone=dates.length===1?plotW:plotW/Math.max(1,dates.length-1);dates.forEach(function(date,i){var x=dates.length===1?left+plotW/2:left+i*plotW/(dates.length-1),zx=Math.max(left,x-zone/2),zw=Math.min(zone,width-right-zx);out+='<rect class="home-hover-zone" x="'+zx+'" y="'+top+'" width="'+zw+'" height="'+plotH+'" onmousemove="showHomeTrendTooltip(event,'+i+')"/>'});svg.innerHTML=out}
function showHomeTrendTooltip(event,index){if(!homeTrendCurrentSeries)return;var svg=document.getElementById('homeTrendChart'),tip=document.getElementById('homeTrendTooltip'),visual=svg.parentElement,svgRect=svg.getBoundingClientRect(),visualRect=visual.getBoundingClientRect(),viewX=48+(homeTrendViewDates.length===1?455:index*910/(homeTrendViewDates.length-1)),line=svg.querySelector('#homeTrendHoverLine'),pixelX=(viewX/980)*svgRect.width+(svgRect.left-visualRect.left);line.setAttribute('x1',viewX);line.setAttribute('x2',viewX);line.classList.add('show');tip.innerHTML='<b>'+homeTrendViewDates[index]+'</b><span><i style="background:#00A6A6"></i>销量<strong>'+Math.round(homeTrendCurrentSeries.units[index]).toLocaleString()+' 台</strong></span><span><i style="background:#607FF5"></i>销额<strong>'+homeTrendCurrentSeries.revenue[index].toFixed(1)+' 万元</strong></span><span><i style="background:#F2A12D"></i>均价<strong>¥'+Math.round(homeTrendCurrentSeries.price[index]).toLocaleString()+'</strong></span>';tip.classList.add('show');var desired=pixelX+14,max=visual.clientWidth-170;tip.style.left=Math.max(8,Math.min(desired,max))+'px';tip.style.top='34px'}
function hideHomeTrendTooltip(){var tip=document.getElementById('homeTrendTooltip'),line=document.getElementById('homeTrendHoverLine');if(tip)tip.classList.remove('show');if(line)line.classList.remove('show')}
function initHomeTrend(){updateHomeTrendCaption('近7天每日趋势');renderHomeModelCards();renderHomeTrend();renderHomeLaunches();renderHomeWarnings()}
// CHAT_ENGINE_START: 完整新建对话交互
var selectedText='';
var qList=[];
document.addEventListener('mouseup',function(e){
  var sel=window.getSelection();var text=sel.toString().trim();var popup=document.getElementById('quotePopup');
  if(popup&&text.length>0&&e.target.closest&&e.target.closest('#page-chat .msg-ai')){selectedText=text;popup.style.display='block';popup.style.left=(e.clientX-20)+'px';popup.style.top=(e.clientY-36)+'px';}
  else if(popup){popup.style.display='none';selectedText='';}
});
document.addEventListener('mousedown',function(e){setTimeout(function(){var p=document.getElementById('quotePopup');if(p&&!e.target.closest('#quotePopup'))p.style.display='none';},200)});
function doQuote(){if(!selectedText)return;document.getElementById('chatBottom').style.display='block';var input=document.getElementById('bottomInput');input.value='关于「'+selectedText+'」，';input.focus();document.getElementById('quotePopup').style.display='none';selectedText='';window.getSelection().removeAllRanges();}
function newChat(){
  goPage('chat',null);
  var pc=document.getElementById('page-chat');if(pc)pc.classList.remove('chatting');
  var welcome=document.querySelector('.chat-welcome');if(welcome)welcome.style.display='flex';
  var cs=document.getElementById('chatScroll');if(cs){cs.style.display='none';cs.innerHTML=''}
  var cb=document.getElementById('chatBottom');if(cb)cb.style.display='none';
  var mi=document.getElementById('mainInput');if(mi)mi.value='';
  var bi=document.getElementById('bottomInput');if(bi)bi.value='';
  qList=[];
  var qi=document.querySelector('.q-index');if(qi){qi.classList.remove('show');qi.innerHTML=''}
  setTimeout(function(){var m=document.getElementById('mainInput');if(m)m.focus()},50);
}
// HOME_INPUT_ATTACH_V19: 首页输入框上传文件/图片
let mainAttachments=[];
function toggleAttachMenu(e){if(e)e.stopPropagation();var w=document.getElementById('attachWrap');if(w)w.classList.toggle('open');}
function closeAttachMenu(){var w=document.getElementById('attachWrap');if(w)w.classList.remove('open');}
function chooseAttach(type){closeAttachMenu();document.getElementById(type==='image'?'mainImageInput':'mainFileInput').click();}
document.addEventListener('mousedown',function(e){var w=document.getElementById('attachWrap');if(w&&w.classList.contains('open')&&!e.target.closest('#attachWrap'))closeAttachMenu();});
function handleMainFiles(files){
  if(!files)return;
  for(var i=0;i<files.length;i++){var f=files[i];var isImg=/^image\//.test(f.type)||/\.(png|jpe?g|gif|webp|bmp|svg|heic)$/i.test(f.name);mainAttachments.push({name:f.name,isImg:isImg});}
  renderMainAttachments();
  document.getElementById('mainFileInput').value='';document.getElementById('mainImageInput').value='';
}
function removeMainAttachment(idx){mainAttachments.splice(idx,1);renderMainAttachments();}
function renderMainAttachments(){
  var box=document.getElementById('mainAttachList');if(!box)return;
  var imgIcon='<svg class="a-icon" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>';
  var fileIcon='<svg class="a-icon" viewBox="0 0 24 24"><path d="M14 3H6v18h12V7z"/><path d="M14 3v4h4"/></svg>';
  box.innerHTML=mainAttachments.map(function(f,i){return '<span class="attach-item">'+(f.isImg?imgIcon:fileIcon)+'<span class="a-name">'+escapeSampleText(f.name)+'</span><span class="a-remove" onclick="removeMainAttachment('+i+')">×</span></span>'}).join('');
}
function sendMain(){var v=document.getElementById('mainInput').value.trim();var atts=mainAttachments.slice();if(v||atts.length){var q=v;if(atts.length){q=(v?v+'　':'')+'（已上传附件：'+atts.map(function(f){return f.name}).join('、')+'）';}askQ(q);}document.getElementById('mainInput').value='';mainAttachments=[];renderMainAttachments();}
function sendBottom(){var v=document.getElementById('bottomInput').value.trim();if(v)askQ(v);document.getElementById('bottomInput').value='';}
function askQ(q){
  goPage('chat',null);
  // 隐藏欢迎页，显示对话滚动区和底部输入区
  var welcome=document.querySelector('.chat-welcome');if(welcome)welcome.style.display='none';
  var pc=document.getElementById('page-chat');if(pc)pc.classList.add('chatting');
  var cs=document.getElementById('chatScroll');cs.style.display='block';
  document.getElementById('chatBottom').style.display='block';
  var now=new Date();var ts=now.getHours()+':'+('0'+now.getMinutes()).slice(-2);var qId='q'+qList.length;
  cs.innerHTML+='<div class="msg-user" id="'+qId+'"><div class="bubble">'+escapeSampleText(q)+'<div class="time">'+ts+'</div></div></div>';
  cs.innerHTML+=genReply(q);qList.push({id:qId,text:q});updateQIndex();addHistory(q);setTimeout(function(){cs.scrollTop=cs.scrollHeight},0);
}
function updateQIndex(){var idx=document.getElementById('qIndex');if(qList.length===0){idx.classList.remove('show');return;}idx.classList.add('show');var html='';for(var i=0;i<qList.length;i++){html+='<div class="q-dot'+(i===qList.length-1?' active':'')+'" onclick="scrollToQ('+i+')"><span class="q-tip">'+escapeSampleText(qList[i].text)+'</span></div>';}idx.innerHTML=html;}
function scrollToQ(i){var el=document.getElementById(qList[i].id);if(el)el.scrollIntoView({behavior:'smooth',block:'start'});document.querySelectorAll('#page-chat .q-dot').forEach(function(d,j){d.classList.toggle('active',j===i)});}
// 历史对话模拟数据
const historyConversations=window.gtmRecords.historyConversations;

function loadHistoryById(hid){
  var conv=historyConversations[hid];
  if(!conv){showToast('未找到该历史对话');return;}
  goPage('chat',null);
  var welcome=document.querySelector('.chat-welcome');if(welcome)welcome.style.display='none';
  var pc=document.getElementById('page-chat');if(pc)pc.classList.add('chatting');
  var cs=document.getElementById('chatScroll');cs.style.display='block';cs.innerHTML='';
  document.getElementById('chatBottom').style.display='block';
  qList=[];
  var msgs=conv.messages;
  for(var i=0;i<msgs.length;i++){
    var m=msgs[i];
    var qId='q'+qList.length;
    if(m.role==='user'){
      cs.innerHTML+='<div class="msg-user" id="'+qId+'"><div class="bubble">'+escapeSampleText(m.text)+'<div class="time">'+m.time+'</div></div></div>';
      qList.push({id:qId,text:m.text});
    }else if(m.role==='ai'){
      cs.innerHTML+=genReplyFromKey(m.replyKey,conv.messages[i-1]?conv.messages[i-1].text:'');
    }
  }
  updateQIndex();
  setTimeout(function(){cs.scrollTop=cs.scrollHeight},0);
  // 高亮侧栏当前对话
  var items=document.querySelectorAll('#sidebarHistory .history-item');
  items.forEach(function(it){it.classList.toggle('active',it.getAttribute('data-hid')===hid);});
}

// 按replyKey生成AI回复内容（与genReply中对应模块保持一致）
function genReplyFromKey(key,contextQ){
  var q=contextQ||'';
  var h='<div class="msg-ai"><div style="margin-bottom:12px"><span class="badge">已理解</span><span class="q">'+escapeSampleText(q)+'</span></div>';
  if(key==='competitor' || key==='selling_value'){
    // 直接调用genReply对应分支
    if(key==='competitor') return genReply('海信 65E7Q 的竞品是谁？');
    if(key==='selling_value') return genReply('海信 65E7Q 的用户卖点价值是什么？');
  }
  if(key==='price_gap_tcl'){
    h+='<h4 style="color:var(--purple)">海信 65E7Q vs TCL 65Q9L PRO 价格带差距</h4>';
    h+='<div class="insight"><b>结论：价差约 ¥427，海信处于溢价位</b><br>海信65E7Q 均价 ¥5,949，TCL 65Q9L PRO 均价 ¥5,522，价差 ¥427（7.7%）。销量上 65E7Q 周均 251台 vs TCL 194台，用户认可价值溢价。</div>';
    h+='<table><thead><tr><th>指标</th><th>海信 65E7Q</th><th>TCL 65Q9L PRO</th><th>差距</th></tr></thead><tbody>';
    h+='<tr><td>线上均价</td><td>¥5,949</td><td>¥5,522</td><td class="tag-ok">+¥427 (+7.7%)</td></tr>';
    h+='<tr><td>周均销量</td><td>251 台</td><td>194 台</td><td class="tag-ok">+57 台 (+29.4%)</td></tr>';
    h+='<tr><td>价值战场重合</td><td colspan="2">主战场（高端画质）完全重合</td><td class="tag-mid">强竞争</td></tr>';
    h+='<tr><td>核心差异卖点</td><td>XDR 5200nits+1920分区 · 6单元60W音响</td><td>QLED量子点 · 1152分区</td><td>画质路线不同</td></tr>';
    h+='</tbody></table>';
    h+=followupLine(q);
    h+='<div class="feedback"><span>有用</span><span>没用</span><span>复制</span><span>生成报告</span></div></div>';
    return h;
  }
  if(key==='bidding_suggestion'){
    h+='<h4 style="color:var(--purple)">海信 65E7Q 竞价调整建议</h4>';
    h+='<div class="insight"><b>建议：保持当前定价，强化「画质+音响」场景组合</b><br>4个核心价值点全部通过量价验证，当前 ¥5,949 定价有用户价值支撑。降价既损失利润又可能拉低高端定位，建议维持价格、加大场景化内容投入。</div>';
    h+='<h4>可选策略对比</h4>';
    h+='<table><thead><tr><th>策略</th><th>利润影响</th><th>销量预期</th><th>定位影响</th><th>推荐度</th></tr></thead><tbody>';
    h+='<tr><td><b>维持现价</b></td><td class="tag-ok">稳定</td><td>稳中有升</td><td class="tag-ok">高端定位稳固</td><td class="tag-ok">★★★★★</td></tr>';
    h+='<tr><td>降价 ¥200</td><td class="tag-mid">-¥50K/月</td><td>+12~15%</td><td class="tag-mid">定位下移风险</td><td class="tag-mid">★★☆</td></tr>';
    h+='<tr><td>加量不加价（赠音响礼包）</td><td class="tag-mid">-¥20K/月</td><td>+8~10%</td><td class="tag-ok">定位不变</td><td class="tag-ok">★★★★</td></tr>';
    h+='<tr><td>涨价 ¥100</td><td class="tag-ok">+¥25K/月</td><td>-3~5%</td><td class="tag-ok">高端定位强化</td><td>★★★</td></tr>';
    h+='</tbody></table>';
    h+='<h4>下一步优先动作</h4>';
    h+='<div style="display:grid;gap:8px;margin:10px 0">';
    h+='<div style="padding:10px 12px;background:#fff;border:1px solid var(--line);border-radius:8px"><div style="font-weight:650;font-size:12px;margin-bottom:3px">1. 主推「白天客厅画质」场景内容</div><div style="font-size:11px;color:var(--muted)">抖音/小红书投放实测对比视频，激活 XDR 亮度卖点感知</div></div>';
    h+='<div style="padding:10px 12px;background:#fff;border:1px solid var(--line);border-radius:8px"><div style="font-weight:650;font-size:12px;margin-bottom:3px">2. 上线「音响免配回音壁」话术</div><div style="font-size:11px;color:var(--muted)">详情页增加 6单元60W 与回音壁效果对比，强化音响价值锚点</div></div>';
    h+='<div style="padding:10px 12px;background:#fff;border:1px solid var(--line);border-radius:8px"><div style="font-weight:650;font-size:12px;margin-bottom:3px">3. 游戏卖点内容孵化</div><div style="font-size:11px;color:var(--muted)">170Hz + HDMI2.1 卖点当前未形成用户认知，先做内容验证再决定是否升级主推</div></div>';
    h+='</div>';
    h+=followupLine(q);
    h+='<div class="feedback"><span>有用</span><span>没用</span><span>复制</span><span>生成报告</span></div></div>';
    return h;
  }
  if(key==='premium_trend'){
    h+='<h4 style="color:var(--purple)">海信电视品牌溢价趋势（近3个月）</h4>';
    h+='<div class="insight"><b>结论：品牌溢价稳步提升，月均 +1.2%</b><br>近3个月海信电视均价相对行业均价溢价由 8.5% 上升至 10.9%，主要受高端 E 系列销量占比提升拉动。</div>';
    h+='<h4>品牌溢价指数走势</h4>';
    h+='<div style="background:var(--bg);border-radius:10px;padding:16px;margin:10px 0">';
    h+='<svg viewBox="0 0 600 160" style="width:100%;height:auto;font-family:inherit">';
    h+='<line x1="40" y1="20" x2="580" y2="20" stroke="#E5E6EB" stroke-width="0.5" stroke-dasharray="3"/>';
    h+='<line x1="40" y1="65" x2="580" y2="65" stroke="#E5E6EB" stroke-width="0.5" stroke-dasharray="3"/>';
    h+='<line x1="40" y1="110" x2="580" y2="110" stroke="#E5E6EB" stroke-width="0.5" stroke-dasharray="3"/>';
    h+='<line x1="40" y1="130" x2="580" y2="130" stroke="#E5E6EB" stroke-width="0.5"/>';
    h+='<text x="35" y="24" font-size="9" fill="#86909C" text-anchor="end">12%</text>';
    h+='<text x="35" y="69" font-size="9" fill="#86909C" text-anchor="end">10%</text>';
    h+='<text x="35" y="114" font-size="9" fill="#86909C" text-anchor="end">8%</text>';
    var pts='';
    var vals=[8.5,8.7,8.9,9.1,9.3,9.5,9.7,9.8,10.1,10.3,10.6,10.9];
    var xLabels=['6W1','6W2','6W3','6W4','7W1','7W2','7W3','7W4','8W1','8W2','8W3','8W4'];
    for(var i=0;i<vals.length;i++){var x=40+i*500/11;var y=130-(vals[i]-6)*55/6;pts+=(i===0?'':' ')+x+','+y;h+='<circle cx="'+x+'" cy="'+y+'" r="2.5" fill="#0064fa"/>';}
    h+='<polyline fill="none" stroke="#0064fa" stroke-width="2" stroke-linecap="round" points="'+pts+'"/>';
    var area=pts+' L 540,130 L 40,130 Z';
    h+='<polygon fill="rgba(0,100,250,.10)" points="'+pts+' L 540,130 L 40,130 Z"/>';
    for(var i=0;i<xLabels.length;i+=2){var x=40+i*500/11;h+='<text x="'+x+'" y="148" font-size="9" fill="#86909C" text-anchor="middle">'+xLabels[i]+'</text>';}
    h+='</svg></div>';
    h+='<h4>溢价驱动因素</h4>';
    h+='<table><thead><tr><th>驱动因素</th><th>贡献度</th><th>说明</th></tr></thead><tbody>';
    h+='<tr><td>高端 E 系列占比提升</td><td class="tag-ok">45%</td><td>E7Q/E8N 系列销量占比从 18% → 26%</td></tr>';
    h+='<tr><td>画质技术口碑积累</td><td class="tag-ok">28%</td><td>XDR/分区背光 用户提及率 +32%</td></tr>';
    h+='<tr><td>渠道结构优化</td><td>18%</td><td>京东自营/天猫官旗 占比提升 5pp</td></tr>';
    h+='<tr><td>新品上市溢价</td><td>9%</td><td>Q 系列新品上市定价高于上一代 8%</td></tr>';
    h+='</tbody></table>';
    h+=followupLine(q);
    h+='<div class="feedback"><span>有用</span><span>没用</span><span>复制</span><span>生成报告</span></div></div>';
    return h;
  }
  if(key==='premium_compare_tcl'){
    h+='<h4 style="color:var(--purple)">海信 vs TCL 品牌溢价对比</h4>';
    h+='<div class="insight"><b>结论：海信溢价高于 TCL 约 2.3pp，差距在扩大</b><br>当前海信电视整体均价 ¥4,128，TCL ¥3,695，溢价差 11.7%。近3个月差距扩大 0.8pp，主要来自海信高端线占比提升更快。</div>';
    h+='<table><thead><tr><th>品牌</th><th>均价</th><th>相对行业溢价</th><th>3个月变化</th><th>高端线占比</th></tr></thead><tbody>';
    h+='<tr style="background:var(--purple-light)"><td><b>海信</b></td><td>¥4,128</td><td class="tag-ok">+10.9%</td><td class="tag-ok">+2.4pp</td><td>26%</td></tr>';
    h+='<tr><td>TCL</td><td>¥3,695</td><td>+8.6%</td><td>+1.6pp</td><td>19%</td></tr>';
    h+='<tr><td>创维</td><td>¥3,512</td><td>+3.5%</td><td>+0.3pp</td><td>12%</td></tr>';
    h+='<tr><td>小米</td><td>¥2,486</td><td class="tag-mid">-33.2%</td><td>-0.5pp</td><td>7%</td></tr>';
    h+='</tbody></table>';
    h+=followupLine(q);
    h+='<div class="feedback"><span>有用</span><span>没用</span><span>复制</span><span>生成报告</span></div></div>';
    return h;
  }
  if(key==='tcl_pricecut_impact'){
    h+='<h4 style="color:var(--purple)">TCL 65Q9L PRO 降价影响评估</h4>';
    h+='<div class="insight"><b>结论：短期销量分流约 8~12%，中长期影响有限</b><br>TCL 65Q9L PRO 7月中旬降价 ¥200（从 ¥5,722 → ¥5,522）后，65E7Q 当周销量环比下降 9.3%，但2周后已恢复至降价前水平的 96%，说明用户对画质+音响价值有辨识度。</div>';
    h+='<h4>降价后销量变化趋势</h4>';
    h+='<div style="background:var(--bg);border-radius:10px;padding:16px;margin:10px 0">';
    h+='<svg viewBox="0 0 600 160" style="width:100%;height:auto;font-family:inherit">';
    h+='<line x1="40" y1="20" x2="580" y2="20" stroke="#E5E6EB" stroke-width="0.5"/>';
    h+='<line x1="40" y1="70" x2="580" y2="70" stroke="#E5E6EB" stroke-width="0.5" stroke-dasharray="3"/>';
    h+='<line x1="40" y1="120" x2="580" y2="120" stroke="#E5E6EB" stroke-width="0.5"/>';
    h+='<text x="35" y="24" font-size="9" fill="#86909C" text-anchor="end">300台</text>';
    h+='<text x="35" y="74" font-size="9" fill="#86909C" text-anchor="end">200台</text>';
    h+='<text x="35" y="124" font-size="9" fill="#86909C" text-anchor="end">100台</text>';
    var hv=[248,252,255,250,245,228,217,225,235,242,247,249];
    var tv=[180,185,182,190,210,235,248,240,230,220,210,205];
    var hp='',tp='';
    for(var i=0;i<hv.length;i++){var x=40+i*520/11;var hy=120-(hv[i]-100)*50/200;var ty=120-(tv[i]-100)*50/200;hp+=(i===0?'':' ')+x+','+hy;tp+=(i===0?'':' ')+x+','+ty;}
    h+='<polyline fill="none" stroke="#0064fa" stroke-width="2" points="'+hp+'"/>';
    h+='<polyline fill="none" stroke="#FF9A2E" stroke-width="2" points="'+tp+'"/>';
    h+='<line x1="240" y1="15" x2="240" y2="125" stroke="#E5484D" stroke-width="1" stroke-dasharray="4 2"/>';
    h+='<text x="244" y="22" font-size="9" fill="#E5484D">TCL降价</text>';
    var days=['W1','W2','W3','W4','W5','W6','W7','W8','W9','W10','W11','W12'];
    for(var i=0;i<days.length;i+=2){var x=40+i*520/11;h+='<text x="'+x+'" y="138" font-size="9" fill="#86909C" text-anchor="middle">'+days[i]+'</text>';}
    h+='</svg>';
    h+='<div style="display:flex;gap:16px;justify-content:center;margin-top:8px;font-size:11px">';
    h+='<span style="display:flex;align-items:center;gap:4px"><span style="width:14px;height:3px;background:#0064fa;border-radius:1px"></span>海信 65E7Q</span>';
    h+='<span style="display:flex;align-items:center;gap:4px"><span style="width:14px;height:3px;background:#FF9A2E;border-radius:1px"></span>TCL 65Q9L PRO</span>';
    h+='</div></div>';
    h+='<h4>影响评估与建议</h4>';
    h+='<table><thead><tr><th>维度</th><th>评估</th><th>建议</th></tr></thead><tbody>';
    h+='<tr><td>销量分流</td><td class="tag-mid">8~12% 短期</td><td>监控4周，确认是否持续</td></tr>';
    h+='<tr><td>利润影响</td><td class="tag-ok">约 -3.2%</td><td>影响可控，无需跟进降价</td></tr>';
    h+='<tr><td>用户认知</td><td class="tag-ok">价值锚点稳固</td><td>加大画质对比内容投放</td></tr>';
    h+='<tr><td>价格风险</td><td class="tag-mid">中等</td><td>若 TCL 继续降价 ≥¥300 则启动预案</td></tr>';
    h+='</tbody></table>';
    h+=followupLine(q);
    h+='<div class="feedback"><span>有用</span><span>没用</span><span>复制</span><span>生成报告</span></div></div>';
    return h;
  }
  if(key==='pdd_price_break'){
    h+='<h4 style="color:var(--purple)">拼多多渠道破价原因与处理方案</h4>';
    h+='<div class="insight"><b>结论：串货+经销商冲量导致破价，建议双轨处置</b><br>涉及型号 65E55N，拼多多到手价 ¥3,299（指导价 ¥3,799），破价幅度 -13.2%。根因为华东某经销商串货至拼多多店铺冲量，已确认3家店铺。</div>';
    h+='<h4>破价证据链</h4>';
    h+='<table><thead><tr><th>店铺</th><th>型号</th><th>到手价</th><th>价差</th><th>销量/月</th><th>状态</th></tr></thead><tbody>';
    h+='<tr><td>某优品电器专营店</td><td>65E55N</td><td>¥3,299</td><td class="tag-mid">-¥500</td><td>约 280台</td><td class="tag-mid">待处理</td></tr>';
    h+='<tr><td>某家电折扣店</td><td>65E55N</td><td>¥3,349</td><td class="tag-mid">-¥450</td><td>约 150台</td><td class="tag-mid">待处理</td></tr>';
    h+='<tr><td>某电器工厂店</td><td>55E55N</td><td>¥2,599</td><td class="tag-mid">-¥300</td><td>约 120台</td><td class="tag-mid">待处理</td></tr>';
    h+='</tbody></table>';
    h+='<h4>根因定位</h4>';
    h+='<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:10px 0">';
    h+='<div style="padding:12px;background:#FFF4E5;border:1px solid #FFE0B2;border-radius:8px"><div style="font-weight:650;font-size:12px;color:#B26A00;margin-bottom:6px">直接原因</div><div style="font-size:11px;color:#8A5500;line-height:1.7">· 华东经销商冲季度返利，低价串货拼多多<br>· 3家店铺均溯源至同一供货商<br>· 单台利润压缩至 ¥80，靠走量拿返利</div></div>';
    h+='<div style="padding:12px;background:#FFEBEB;border:1px solid #FFCDD2;border-radius:8px"><div style="font-weight:650;font-size:12px;color:#C62828;margin-bottom:6px">深层原因</div><div style="font-size:11px;color:#A82525;line-height:1.7">· 经销商考核中销量权重过高<br>· 拼多多渠道监管覆盖不足<br>· 串货检测响应周期过长（7天）</div></div>';
    h+='</div>';
    h+='<h4>处理方案（优先级排序）</h4>';
    h+='<div style="display:grid;gap:8px;margin:10px 0">';
    h+='<div style="padding:10px 12px;background:#fff;border:1px solid var(--line);border-radius:8px"><div style="display:flex;align-items:center;gap:8px;margin-bottom:4px"><span style="background:#E5484D;color:#fff;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:600">P0 立即</span><b style="font-size:12px">向涉事经销商发函+停货</b></div><div style="font-size:11px;color:var(--muted)">48小时内完成书面通知，暂停该经销商供货，直到价格恢复至指导价</div></div>';
    h+='<div style="padding:10px 12px;background:#fff;border:1px solid var(--line);border-radius:8px"><div style="display:flex;align-items:center;gap:8px;margin-bottom:4px"><span style="background:#F59E0B;color:#fff;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:600">P1 3天内</span><b style="font-size:12px">拼多多平台投诉+店铺取证</b></div><div style="font-size:11px;color:var(--muted)">联系拼多多知识产权/价格保护通道，提交品牌方价格管控函，要求下架违规链接</div></div>';
    h+='<div style="padding:10px 12px;background:#fff;border:1px solid var(--line);border-radius:8px"><div style="display:flex;align-items:center;gap:8px;margin-bottom:4px"><span style="background:#0064fa;color:#fff;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:600">P2 1周内</span><b style="font-size:12px">渠道价格巡检系统升级</b></div><div style="font-size:11px;color:var(--muted)">将拼多多纳入每日价格巡检，异常响应周期从7天缩短至24小时</div></div>';
    h+='<div style="padding:10px 12px;background:#fff;border:1px solid var(--line);border-radius:8px"><div style="display:flex;align-items:center;gap:8px;margin-bottom:4px"><span style="background:#8B5CF6;color:#fff;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:600">P3 2周内</span><b style="font-size:12px">经销商考核机制调整</b></div><div style="font-size:11px;color:var(--muted)">降低销量权重、增加价格合规权重，对串货行为设返利扣减条款</div></div>';
    h+='</div>';
    h+=followupLine(q);
    h+='<div class="feedback"><span>有用</span><span>没用</span><span>复制</span><span>生成报告</span></div></div>';
    return h;
  }
  // 默认回复
  h+='<p>正在为您分析中，请稍候...</p>';
  h+=followupLine(q);
  h+='<div class="feedback"><span>有用</span><span>没用</span><span>复制</span><span>生成报告</span></div></div>';
  return h;
}

function addHistory(q){var list=document.querySelector('.history');if(!list)return;var items=list.querySelectorAll('.history-item');for(var i=0;i<items.length;i++){if(items[i].getAttribute('data-q')===q)return;}var div=document.createElement('div');div.className='history-item';div.setAttribute('data-q',q);div.textContent=q.length>18?q.substring(0,18)+'...':q;div.onclick=function(){newChat();askQ(q)};var first=list.querySelector('.history-item');list.insertBefore(div,first);while(list.querySelectorAll('.history-item').length>10){var all=list.querySelectorAll('.history-item');all[all.length-1].remove();}}
function genReply(q){
var h='<div class="msg-ai"><div style="margin-bottom:12px"><span class="badge">已理解</span><span class="q">'+escapeSampleText(q)+'</span></div>';

// 精确匹配：海信 65E7Q 的用户卖点价值是什么？
if(q.indexOf('用户卖点价值')>=0 || q.indexOf('卖点价值')>=0){
  h+='<div class="chat-analysis-title"><div style="font-size:16px;font-weight:700;color:var(--t1);margin-bottom:4px">海信65E7Q用户卖点价值看板</div><div style="font-size:12px;color:var(--t3)">高端画质升级款 · 当前价格有价值支撑</div></div>';
  // 结论1
  h+='<div style="margin-bottom:14px"><div style="display:flex;align-items:center;gap:8px;margin-bottom:10px"><span style="background:var(--purple);color:#fff;padding:3px 10px;border-radius:5px;font-size:12px;font-weight:600">结论1</span><b style="font-size:13px">SKU形成了什么用户卖点价值</b></div>';
  h+='<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">';
  h+='<div style="padding:10px 12px;background:#fff;border:1px solid var(--line);border-radius:8px"><div style="font-size:11px;color:var(--purple);font-weight:650;margin-bottom:3px">01 画质价值</div><div style="font-size:12px;color:var(--t1)">白天客厅画面仍清楚，暗场层次更完整、光晕更少</div></div>';
  h+='<div style="padding:10px 12px;background:#fff;border:1px solid var(--line);border-radius:8px"><div style="font-size:11px;color:var(--purple);font-weight:650;margin-bottom:3px">02 大屏价值</div><div style="font-size:12px;color:var(--t1)">大屏观看更有临场感，客厅观影更沉浸</div></div>';
  h+='<div style="padding:10px 12px;background:#fff;border:1px solid var(--line);border-radius:8px"><div style="font-size:11px;color:var(--purple);font-weight:650;margin-bottom:3px">03 音响价值</div><div style="font-size:12px;color:var(--t1)">对白更清楚，声场和包围感带来更强影院沉浸</div></div>';
  h+='<div style="padding:10px 12px;background:#fff;border:1px solid var(--line);border-radius:8px"><div style="font-size:11px;color:var(--purple);font-weight:650;margin-bottom:3px">04 色彩价值</div><div style="font-size:12px;color:var(--t1)">色彩更自然准确，人物和画面还原更真实</div></div>';
  h+='</div></div>';
  // 结论2
  h+='<div style="margin-bottom:14px"><div style="display:flex;align-items:center;gap:8px;margin-bottom:10px"><span style="background:var(--purple);color:#fff;padding:3px 10px;border-radius:5px;font-size:12px;font-weight:600">结论2</span><b style="font-size:13px">这些价值是否支撑当前价格和销量</b></div>';
  h+='<div style="padding:12px 14px;background:#fff;border:1px solid var(--line);border-radius:8px;line-height:1.8;font-size:12px;color:var(--t1)">';
  h+='1. 4个用户卖点价值问题均形成了可用的量价对照<br>';
  h+='2. 相对各自参照组，本品价高262-427元，量高46-76台<br>';
  h+='3. 这些用户卖点价值在更高价格下仍获得更高销量，当前价格和销量均有用户价值支撑';
  h+='</div></div>';
  // 总体判断
  h+='<div class="insight"><b>总体判断</b>：支撑本品的高端画质升级定位。4个核心价值点全部通过量价验证，用户愿意为画质、音响、色彩、大屏体验升级支付溢价。</div>';
  // 卖点形成价值 - 3组
  h+='<h4>卖点形成价值（3组）</h4>';
  h+='<table><thead><tr><th>原始卖点</th><th>用户获得</th><th>分类</th></tr></thead><tbody>';
  h+='<tr><td>XDR Pro 5200nits + 1920分区</td><td>白天画面清楚 · 暗场无光晕</td><td class="tag-ok">核心主推</td></tr>';
  h+='<tr><td>6单元60W独立音响</td><td>对白清晰 · 声场包围感</td><td class="tag-ok">核心主推</td></tr>';
  h+='<tr><td>潘通+杜比双冠色彩认证 · 98% DCI-P3</td><td>色彩自然 · 画面真实还原</td><td class="tag-ok">核心主推</td></tr>';
  h+='</tbody></table>';
  // 用户卖点价值量化 - 4组
  h+='<h4>用户卖点价值量化（4组）</h4>';
  h+='<table><thead><tr><th>价值问题</th><th>价格差异</th><th>销量差异</th><th>判断</th></tr></thead><tbody>';
  h+='<tr><td>影音用户愿为画质升级付费</td><td class="tag-ok">高370元</td><td class="tag-ok">高46台</td><td class="tag-ok">价格和销量均获得支撑</td></tr>';
  h+='<tr><td>画质配置解释加价</td><td class="tag-ok">高427元</td><td class="tag-ok">高57台</td><td class="tag-ok">价格和销量均获得支撑</td></tr>';
  h+='<tr><td>同尺寸画质越级获得感</td><td class="tag-ok">高262元</td><td class="tag-ok">高76台</td><td class="tag-ok">价格和销量均获得支撑</td></tr>';
  h+='<tr><td>贵得值的体验升级</td><td class="tag-ok">高279元</td><td class="tag-ok">高62台</td><td class="tag-ok">价格和销量均获得支撑</td></tr>';
  h+='</tbody></table>';
  h+=followupLine(q);
  h+='<div class="feedback"><span>有用</span><span>没用</span><span>复制</span><span>生成报告</span></div></div>';
  return h;
}

// 精确匹配：海信 65E7Q 的竞品是谁？
if(q.indexOf('的竞品是谁')>=0 || q.indexOf('竞品是谁')>=0){
  h+='<div class="chat-analysis-title"><div style="font-size:16px;font-weight:700;color:var(--t1);margin-bottom:4px">海信65E7Q重点竞品看板</div><div style="font-size:12px;color:var(--t3)">当前可观测线上样本内的65寸、高价带目标SKU</div></div>';
  // 结论
  h+='<div class="insight"><b>结论：优先盯TCL 65Q9L PRO</b><br>TCL 65Q9L PRO与海信65E7Q在战场、任务和客群三层重合最完整，会形成价值替代压力；另外，华为VISION智慧屏5 PRO 65偏价格下探分流、创维65A7H PRO强配置对标。</div>';
  // 多维评分雷达图
  h+='<h4>多维评分雷达图</h4>';
  h+='<div style="background:var(--bg);border-radius:10px;padding:16px;margin:10px 0">';
  h+='<svg viewBox="0 0 380 300" style="width:100%;max-width:420px;display:block;margin:0 auto;font-family:inherit">';
  var axes=['购买实地','价值战场','用户任务','目标客群','价值锚点','市场验证'];
  var tclData=[92,95,78,95,93,100];
  var hwData=[85,93,81,100,95,93];
  var swData=[95,100,100,95,93,100];
  function radPt(cx,cy,r,ang){var a=(ang-90)*Math.PI/180;return{x:cx+r*Math.cos(a),y:cy+r*Math.sin(a)}}
  [110,82.5,55,27.5].forEach(function(r){var pts=[];for(var i=0;i<6;i++){var p=radPt(190,145,r,i*60);pts.push(p.x+','+p.y)}h+='<polygon points="'+pts.join(' ')+'" fill="none" stroke="#E5E6EB" stroke-width="0.6"/>';});
  for(var i=0;i<6;i++){var p=radPt(190,145,110,i*60);h+='<line x1="190" y1="145" x2="'+p.x+'" y2="'+p.y+'" stroke="#E5E6EB" stroke-width="0.5"/>';var lp=radPt(190,145,125,i*60);var anc='middle';if(i===1||i===2)anc='start';if(i===4||i===5)anc='end';h+='<text x="'+lp.x+'" y="'+(lp.y+4)+'" font-size="10" fill="#1d2129" text-anchor="'+anc+'" font-weight="600">'+axes[i]+'</text>';}
  function mkPoly(arr,fill,stroke,w,dash){var pts=[];for(var i=0;i<6;i++){var p=radPt(190,145,arr[i]*1.1,i*60);pts.push(p.x+','+p.y)}return'<polygon points="'+pts.join(' ')+'" fill="'+fill+'" stroke="'+stroke+'" stroke-width="'+w+'"'+(dash?' stroke-dasharray="'+dash+'"':'')+'/>'}
  h+=mkPoly(swData,'rgba(44,184,120,.1)','#2CB878','1.5','3 3');
  h+=mkPoly(hwData,'rgba(163,222,218,.12)','#85b6ff','1.5','5 3');
  h+=mkPoly(tclData,'rgba(0,100,250,.18)','#0064fa','2','');
  for(var i=0;i<6;i++){var p=radPt(190,145,tclData[i]*1.1,i*60);h+='<circle cx="'+p.x+'" cy="'+p.y+'" r="3" fill="#0064fa"/>';}
  h+='</svg>';
  h+='<div style="display:flex;gap:16px;justify-content:center;margin-top:10px;font-size:11px">';
  h+='<span style="display:flex;align-items:center;gap:5px"><span style="width:14px;height:3px;background:#0064fa;border-radius:1px"></span>TCL 65Q9L PRO</span>';
  h+='<span style="display:flex;align-items:center;gap:5px"><span style="width:14px;height:3px;background:#85b6ff;border-radius:1px;opacity:.7"></span>华为 VISION 智慧屏 5 PRO 65</span>';
  h+='<span style="display:flex;align-items:center;gap:5px"><span style="width:14px;height:3px;background:#2CB878;border-radius:1px"></span>创维 65A7H PRO</span>';
  h+='</div>';
  h+='</div>';
  // 价值战场重合结构
  h+='<h4>价值战场重合结构</h4>';
  h+='<div style="margin:10px 0">';
  h+='<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px"><span style="width:160px;font-size:11px;text-align:right">TCL 65Q9L PRO</span><div style="flex:1;height:22px;display:flex;border-radius:3px;overflow:hidden"><div style="width:35%;background:var(--purple);display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">主战场</div><div style="width:40%;background:#58BFBC;display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">辅战场</div><div style="width:25%;background:var(--orange);display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">机会战场</div></div></div>';
  h+='<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px"><span style="width:160px;font-size:11px;text-align:right">华为 VISION 智慧屏 5 PRO 65</span><div style="flex:1;height:22px;display:flex;border-radius:3px;overflow:hidden"><div style="width:30%;background:var(--purple);display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">主战场</div><div style="width:28%;background:#58BFBC;display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">辅战场</div><div style="width:20%;background:var(--orange);display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">机会战场</div><div style="width:22%;background:#E5E6EB;display:flex;align-items:center;justify-content:center;font-size:9px;color:var(--t2)">错位</div></div></div>';
  h+='<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px"><span style="width:160px;font-size:11px;text-align:right">创维 65A7H PRO</span><div style="flex:1;height:22px;display:flex;border-radius:3px;overflow:hidden"><div style="width:38%;background:var(--purple);display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">主战场</div><div style="width:35%;background:#58BFBC;display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">辅战场</div><div style="width:15%;background:var(--orange);display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">机会战场</div><div style="width:12%;background:#E5E6EB;display:flex;align-items:center;justify-content:center;font-size:9px;color:var(--t2)">错位</div></div></div>';
  h+='<div style="display:flex;gap:12px;font-size:10px;color:var(--t3);margin-top:6px;padding-left:168px"><span style="display:flex;align-items:center;gap:3px"><span style="width:8px;height:8px;background:var(--purple);border-radius:2px"></span>主战场重合（高端画质）</span><span style="display:flex;align-items:center;gap:3px"><span style="width:8px;height:8px;background:#58BFBC;border-radius:2px"></span>辅战场重合（游戏流畅、智能互联）</span><span style="display:flex;align-items:center;gap:3px"><span style="width:8px;height:8px;background:var(--orange);border-radius:2px"></span>机会战场（护眼舒适、客厅均衡）</span><span style="display:flex;align-items:center;gap:3px"><span style="width:8px;height:8px;background:#E5E6EB;border-radius:2px"></span>错位/缺口</span></div>';
  h+='</div>';
  // 竞品市场验证表格
  h+='<h4>竞品市场验证</h4>';
  h+='<table><thead><tr><th>序号</th><th>竞品/目标</th><th>定位</th><th>均价</th><th>周均销量</th></tr></thead><tbody>';
  h+='<tr style="background:var(--purple-light)"><td>目标</td><td><b>海信 65E7Q</b></td><td>被比较目标</td><td>5,949元</td><td>251台</td></tr>';
  h+='<tr><td>1</td><td>TCL 65Q9L PRO</td><td>首选直接 / 价值替代 / 强</td><td>5,522元</td><td>194台</td></tr>';
  h+='<tr><td>2</td><td>华为 VISION智慧屏 5 PRO 65</td><td>价格下探分流 / 价值替代 / 强</td><td>4,704元</td><td>231台</td></tr>';
  h+='<tr><td>3</td><td>创维 65A7H PRO</td><td>强配置对标 / 价值替代 / 强</td><td>5,637元</td><td>217台</td></tr>';
  h+='</tbody></table>';
  // 底部两个按钮
  h+='<div style="display:flex;gap:10px;margin-top:16px"><button class="btn" onclick="showToast(\'查看分析依据\')">查看分析依据</button><button class="btn primary" onclick="showToast(\'查看详细对比结果\')">查看详细对比结果</button></div>';
  h+=followupLine(q);
  h+='<div class="feedback"><span>有用</span><span>没用</span><span>复制</span><span>生成报告</span></div></div>';
  return h;
}

if(q.indexOf('竞品')>=0 && q.indexOf('品牌')<0 && q.indexOf('优势')<0){
h+='<h4 style="color:var(--purple)">海信 65E7Q 重点竞品看板</h4>';
h+='<p style="font-size:12px;color:var(--t3);margin-bottom:8px">当前可观测线上样本内的65寸、高价带目标 SKU。</p>';
h+='<div class="insight"><b>结论：优先盯 TCL 65Q9L PRO</b><br>TCL 65Q9L PRO与海信65E7Q在战场、任务和客群三层重合最完整，会形成价值替代压力；另外，华为VISION智慧屏 5 PRO 65偏价格下探分流，创维65A7H PRO偏强配置对标。</div>';

// 雷达图（SVG真实雷达）
h+='<h4>多维竞争力雷达图</h4>';
h+='<div style="background:var(--bg);border-radius:10px;padding:16px;margin:10px 0">';
h+='<svg viewBox="0 0 380 300" style="width:100%;max-width:420px;display:block;margin:0 auto;font-family:inherit">';
// 雷达网格 - 6轴，中心(190,145)，半径110
// 角度: 上=270°, 依次顺时针每60°
// 轴端点: 0:价值战场(上), 1:目标客群(右上), 2:价格带(右下), 3:市场验证(下), 4:价值锚点(左下), 5:用户任务(左上)
// 计算点: cx=190, cy=145, r=110
// 0°=上(190,35), 60°右上(285,90), 120°右下(285,200), 180°下(190,255), 240°左下(95,200), 300°左上(95,90)
// 网格层(100%,75%,50%,25%)
h+='<polygon points="190,35 285,90 285,200 190,255 95,200 95,90" fill="none" stroke="#E5E6EB" stroke-width="0.8"/>';
h+='<polygon points="190,62.5 261,104 261,186 190,227.5 119,186 119,104" fill="none" stroke="#E5E6EB" stroke-width="0.5"/>';
h+='<polygon points="190,90 237.5,117.5 237.5,172.5 190,200 142.5,172.5 142.5,117.5" fill="none" stroke="#E5E6EB" stroke-width="0.5"/>';
h+='<polygon points="190,117.5 213.75,131.25 213.75,158.75 190,172.5 166.25,158.75 166.25,131.25" fill="none" stroke="#E5E6EB" stroke-width="0.5"/>';
// 轴线
h+='<line x1="190" y1="145" x2="190" y2="35" stroke="#E5E6EB" stroke-width="0.5"/>';
h+='<line x1="190" y1="145" x2="285" y2="90" stroke="#E5E6EB" stroke-width="0.5"/>';
h+='<line x1="190" y1="145" x2="285" y2="200" stroke="#E5E6EB" stroke-width="0.5"/>';
h+='<line x1="190" y1="145" x2="190" y2="255" stroke="#E5E6EB" stroke-width="0.5"/>';
h+='<line x1="190" y1="145" x2="95" y2="200" stroke="#E5E6EB" stroke-width="0.5"/>';
h+='<line x1="190" y1="145" x2="95" y2="90" stroke="#E5E6EB" stroke-width="0.5"/>';
// TCL数据: 价值战场100, 客群95, 价格带87, 市场验证100, 价值锚点93, 用户任务78
// 归一化 * 110 从中心偏移
h+='<polygon points="190,35 280.5,92.75 272.8,195.3 190,255 96.7,193.9 115.8,102.1" fill="rgba(0,100,250,.15)" stroke="#0064fa" stroke-width="2"/>';
// 华为数据: 价值战场93, 客群100, 价格带77, 市场验证93, 价值锚点95, 用户任务81
h+='<polygon points="190,42.7 285,90 263.5,198.6 197.7,247.3 99.75,194.5 111.9,99.1" fill="rgba(163,222,218,.1)" stroke="#85b6ff" stroke-width="1.5" stroke-dasharray="4 2"/>';
// 创维数据: 价值战场100, 客群95, 价格带87, 市场验证100, 价值锚点93, 用户任务100
h+='<polygon points="190,35 280.5,92.75 272.8,195.3 190,255 96.7,193.9 95,90" fill="rgba(44,180,120,.08)" stroke="#2CB878" stroke-width="1.5" stroke-dasharray="2 2"/>';
// 数据点
h+='<circle cx="190" cy="35" r="3" fill="#0064fa"/><circle cx="280.5" cy="92.75" r="3" fill="#0064fa"/><circle cx="272.8" cy="195.3" r="3" fill="#0064fa"/><circle cx="190" cy="255" r="3" fill="#0064fa"/><circle cx="96.7" cy="193.9" r="3" fill="#0064fa"/><circle cx="115.8" cy="102.1" r="3" fill="#0064fa"/>';
// 轴标签
h+='<text x="190" y="22" font-size="10" fill="#1d2129" text-anchor="middle" font-weight="600">价值战场</text>';
h+='<text x="295" y="87" font-size="10" fill="#1d2129" text-anchor="start">目标客群</text>';
h+='<text x="295" y="207" font-size="10" fill="#1d2129" text-anchor="start">价格带</text>';
h+='<text x="190" y="272" font-size="10" fill="#1d2129" text-anchor="middle">市场验证</text>';
h+='<text x="82" y="207" font-size="10" fill="#1d2129" text-anchor="end">价值锚点</text>';
h+='<text x="82" y="87" font-size="10" fill="#1d2129" text-anchor="end">用户任务</text>';
// 分值标注
h+='<text x="190" y="30" font-size="8" fill="#0064fa" text-anchor="middle">100</text>';
h+='<text x="287" y="97" font-size="8" fill="#0064fa">95</text>';
h+='<text x="279" y="208" font-size="8" fill="#0064fa">87</text>';
h+='<text x="190" y="263" font-size="8" fill="#0064fa" text-anchor="middle">100</text>';
h+='<text x="90" y="200" font-size="8" fill="#0064fa" text-anchor="end">93</text>';
h+='<text x="110" y="108" font-size="8" fill="#0064fa" text-anchor="end">78</text>';
h+='</svg>';
// 图例
h+='<div style="display:flex;gap:16px;justify-content:center;margin-top:10px;font-size:11px">';
h+='<span style="display:flex;align-items:center;gap:5px"><span style="width:14px;height:3px;background:#0064fa;border-radius:1px"></span>TCL 65Q9L PRO</span>';
h+='<span style="display:flex;align-items:center;gap:5px"><span style="width:14px;height:3px;background:#85b6ff;border-radius:1px;opacity:.7"></span>华为 VISION 5 PRO</span>';
h+='<span style="display:flex;align-items:center;gap:5px"><span style="width:14px;height:3px;background:#2CB878;border-radius:1px"></span>创维 65A7H PRO</span>';
h+='</div>';
// 分数对比表
h+='<table style="margin-top:12px"><thead><tr><th>维度</th><th>TCL 65Q9L PRO</th><th>华为 VISION 5 PRO</th><th>创维 65A7H PRO</th></tr></thead><tbody>';
h+='<tr><td>价值战场</td><td class="tag-high"><b>100</b></td><td>93</td><td class="tag-high"><b>100</b></td></tr>';
h+='<tr><td>目标客群</td><td>95</td><td class="tag-high"><b>100</b></td><td>95</td></tr>';
h+='<tr><td>用户任务</td><td>78</td><td>81</td><td class="tag-high"><b>100</b></td></tr>';
h+='<tr><td>价格带</td><td><b>87</b></td><td>77</td><td><b>87</b></td></tr>';
h+='<tr><td>价值锚点</td><td>93</td><td class="tag-high"><b>95</b></td><td>93</td></tr>';
h+='<tr><td>市场验证</td><td class="tag-high"><b>100</b></td><td>93</td><td class="tag-high"><b>100</b></td></tr>';
h+='<tr style="background:var(--purple-light);font-weight:600"><td>综合评分</td><td class="tag-high">92.2</td><td>89.8</td><td class="tag-high">95.8</td></tr>';
h+='</tbody></table>';
h+='</div>';

// 价值战场重合结构（堆叠条）
h+='<h4>价值战场重合结构</h4>';
h+='<p style="font-size:11px;color:var(--t3);margin-bottom:10px">主战场：高端画质 | 辅战场：游戏流畅、智能互联 | 机会战场：护眼舒适、客厅均衡 | 错位/缺口</p>';
h+='<div style="margin:10px 0">';
// TCL
h+='<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px"><span style="width:130px;font-size:11px;text-align:right">TCL 65Q9L PRO</span><div style="flex:1;height:22px;display:flex;border-radius:3px;overflow:hidden"><div style="width:31.3%;background:var(--purple);display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">31.3</div><div style="width:46.9%;background:#58BFBC;display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">46.9</div><div style="width:21.9%;background:var(--orange);display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">21.9</div></div></div>';
// 华为
h+='<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px"><span style="width:130px;font-size:11px;text-align:right">华为 VISION 5 PRO</span><div style="flex:1;height:22px;display:flex;border-radius:3px;overflow:hidden"><div style="width:27.8%;background:var(--purple);display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">27.8</div><div style="width:30.6%;background:#58BFBC;display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">30.6</div><div style="width:19.4%;background:var(--orange);display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">19.4</div><div style="width:22.2%;background:#E5E6EB;display:flex;align-items:center;justify-content:center;font-size:9px;color:var(--t2)">22.2</div></div></div>';
// 创维
h+='<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px"><span style="width:130px;font-size:11px;text-align:right">创维 65A7H PRO</span><div style="flex:1;height:22px;display:flex;border-radius:3px;overflow:hidden"><div style="width:27.8%;background:var(--purple);display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">27.8</div><div style="width:30.6%;background:#58BFBC;display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">30.6</div><div style="width:19.4%;background:var(--orange);display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff">19.4</div><div style="width:22.2%;background:#E5E6EB;display:flex;align-items:center;justify-content:center;font-size:9px;color:var(--t2)">22.2</div></div></div>';
h+='<div style="display:flex;gap:12px;font-size:10px;color:var(--t3);margin-top:6px"><span style="display:flex;align-items:center;gap:3px"><span style="width:8px;height:8px;background:var(--purple);border-radius:2px"></span>主战场重合</span><span style="display:flex;align-items:center;gap:3px"><span style="width:8px;height:8px;background:#58BFBC;border-radius:2px"></span>辅战场重合</span><span style="display:flex;align-items:center;gap:3px"><span style="width:8px;height:8px;background:var(--orange);border-radius:2px"></span>机会战场</span><span style="display:flex;align-items:center;gap:3px"><span style="width:8px;height:8px;background:#E5E6EB;border-radius:2px"></span>错位/缺口</span></div>';
h+='</div>';

// 竞品市场验证表
h+='<h4>竞品市场验证</h4>';
h+='<table><thead><tr><th>序号</th><th>竞品/目标</th><th>定位</th><th>均价</th><th>周均销量</th></tr></thead><tbody>';
h+='<tr style="background:var(--purple-light)"><td>目标</td><td><b>海信 65E7Q</b></td><td>被比较目标</td><td>5,949元</td><td>251台</td></tr>';
h+='<tr><td>1</td><td>TCL 65Q9L PRO</td><td>首选直接/价值替代/强</td><td>5,522元</td><td>194台</td></tr>';
h+='<tr><td>2</td><td>华为 VISION智慧屏 5 PRO 65</td><td>价格下探分流/价值替代</td><td>4,704元</td><td>231台</td></tr>';
h+='<tr><td>3</td><td>创维 65A7H PRO</td><td>强配置对标/价值替代</td><td>5,637元</td><td>217台</td></tr></tbody></table>';
h+='<div class="insight"><b>建议：</b>1.TCL三层全覆盖替代压力最强，重点监控价格 2.华为以低价+智能互联分流，建议游戏差异化应对 3.强化"白天不拉帘也清楚"场景传播</div>';
} else if(q.indexOf('品牌')>=0){
h+='<h4 style="color:var(--purple)">品牌溢价对比：海信 vs 创维</h4>';
h+='<table><thead><tr><th>维度</th><th>海信</th><th>创维</th><th>判断</th></tr></thead><tbody>';
h+='<tr><td>价格指数（65寸）</td><td><b>1.25</b></td><td>1.08</td><td class="tag-ok">海信领先17pp</td></tr>';
h+='<tr><td>用户画质满意度</td><td>92%</td><td>71%</td><td class="tag-ok">海信领先</td></tr>';
h+='<tr><td>品牌信任评分</td><td>79/100</td><td>73/100</td><td class="tag-ok">海信略优</td></tr>';
h+='<tr><td>售后满意度</td><td>72%</td><td>79%</td><td class="tag-mid">创维略优</td></tr>';
h+='<tr><td>性价比感知</td><td>70%</td><td>85%</td><td class="tag-mid">创维领先</td></tr></tbody></table>';
h+='<div class="insight"><b>结论：</b>海信品牌力在画质技术和品牌信任上显著领先创维，但在性价比感知和售后服务上略弱。建议通过"技术领先+服务升级"双轮驱动巩固品牌溢价优势。</div>';
} else if(q.indexOf('优势')>=0){
h+='<h4 style="color:var(--purple)">海信65E7Q vs 创维65A7H PRO 优势对比</h4>';
h+='<table><thead><tr><th>维度</th><th>海信65E7Q</th><th>创维65A7H PRO</th><th>谁更优</th></tr></thead><tbody>';
h+='<tr><td>峰值亮度</td><td><b>XDR 5200nit</b></td><td>—</td><td class="tag-ok">海信碾压</td></tr>';
h+='<tr><td>背光分区</td><td><b>1920分区</b></td><td>无分区</td><td class="tag-ok">海信碾压</td></tr>';
h+='<tr><td>音响</td><td><b>6单元60W</b></td><td>2单元20W</td><td class="tag-ok">海信3倍</td></tr>';
h+='<tr><td>刷新率</td><td>170Hz</td><td>120Hz</td><td class="tag-ok">海信领先</td></tr>';
h+='<tr><td>外观轻薄</td><td>标准</td><td><b>1.3cm超薄</b></td><td class="tag-mid">创维领先</td></tr>';
h+='<tr><td>价格</td><td>¥5,949</td><td>¥5,637</td><td>海信贵¥312</td></tr></tbody></table>';
h+='<h4>卖点称重（用户愿意为什么付费）</h4>';
h+='<table><thead><tr><th>卖点</th><th>用户感知权重</th><th>海信优势?</th></tr></thead><tbody>';
h+='<tr><td>画面亮度/清晰</td><td><b>38%</b></td><td class="tag-ok">✓ 核心优势</td></tr>';
h+='<tr><td>音响效果</td><td>21%</td><td class="tag-ok">✓ 独有优势</td></tr>';
h+='<tr><td>色彩准确</td><td>18%</td><td class="tag-ok">✓ 认证领先</td></tr>';
h+='<tr><td>外观轻薄</td><td>12%</td><td class="tag-mid">✗ 创维领先</td></tr>';
h+='<tr><td>性价比</td><td>11%</td><td class="tag-mid">✗ 创维更低价</td></tr></tbody></table>';
h+='<div class="insight"><b>结论：</b>海信在用户权重最高的三个维度（亮度38%+音响21%+色彩18%=77%）全面领先创维，虽然贵¥312但核心价值支撑溢价。创维优势仅在轻薄（12%）和价格（11%）上，不构成主要购买决策因素。</div>';
} else if(q.indexOf('价格')>=0||q.indexOf('异常')>=0||q.indexOf('预警')>=0||q.indexOf('走势')>=0||q.indexOf('销量')>=0){
h+='<h4 style="color:var(--purple)">海信65E7Q vs 创维65A7Pro 近30天价格走势</h4>';
// SVG 折线图 - 价格
h+='<div style="background:var(--bg);border-radius:10px;padding:16px;margin:10px 0">';
h+='<div style="display:flex;align-items:center;gap:16px;margin-bottom:10px;font-size:11px">';
h+='<span style="display:flex;align-items:center;gap:4px"><span style="width:16px;height:3px;background:var(--purple);border-radius:1px"></span>海信65E7Q 价格</span>';
h+='<span style="display:flex;align-items:center;gap:4px"><span style="width:16px;height:3px;background:var(--orange);border-radius:1px"></span>创维65A7Pro 价格</span>';
h+='</div>';
h+='<svg viewBox="0 0 600 160" style="width:100%;height:auto;font-family:inherit">';
// 网格线
h+='<line x1="40" y1="10" x2="40" y2="130" stroke="#ECEDF0" stroke-width="0.5"/>';
h+='<line x1="40" y1="130" x2="580" y2="130" stroke="#ECEDF0" stroke-width="0.5"/>';
h+='<line x1="40" y1="70" x2="580" y2="70" stroke="#ECEDF0" stroke-width="0.5" stroke-dasharray="3"/>';
h+='<line x1="40" y1="10" x2="580" y2="10" stroke="#ECEDF0" stroke-width="0.5" stroke-dasharray="3"/>';
// Y 轴标签
h+='<text x="35" y="14" font-size="9" fill="#86909C" text-anchor="end">¥6,200</text>';
h+='<text x="35" y="74" font-size="9" fill="#86909C" text-anchor="end">¥5,800</text>';
h+='<text x="35" y="134" font-size="9" fill="#86909C" text-anchor="end">¥5,400</text>';
// X 轴标签
h+='<text x="40" y="148" font-size="9" fill="#86909C">6/18</text>';
h+='<text x="130" y="148" font-size="9" fill="#86909C">6/22</text>';
h+='<text x="220" y="148" font-size="9" fill="#86909C">6/26</text>';
h+='<text x="310" y="148" font-size="9" fill="#86909C">6/30</text>';
h+='<text x="400" y="148" font-size="9" fill="#86909C">7/4</text>';
h+='<text x="490" y="148" font-size="9" fill="#86909C">7/8</text>';
h+='<text x="560" y="148" font-size="9" fill="#86909C">7/12</text>';
// 海信价格线 (稳定在5949左右)
h+='<polyline fill="none" stroke="#0064fa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="40,42 58,42 76,42 94,42 112,42 130,42 148,42 166,42 184,42 202,42 220,42 238,42 256,42 274,42 292,42 310,42 328,42 346,42 364,42 382,42 400,42 418,42 436,42 454,42 472,42 490,42 508,42 526,42 544,42 562,42 580,42"/>';
// 创维价格线 (从5637开始有波动，后期降价)
h+='<polyline fill="none" stroke="#FF9A2E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="40,68 58,68 76,68 94,68 112,66 130,66 148,68 166,68 184,68 202,68 220,70 238,72 256,78 274,82 292,86 310,86 328,88 346,86 364,84 382,82 400,80 418,78 436,76 454,74 472,72 490,70 508,68 526,68 544,66 562,66 580,68"/>';
// 标注事件点
h+='<circle cx="256" cy="78" r="4" fill="#FF9A2E" stroke="#fff" stroke-width="1.5"/>';
h+='<text x="256" y="96" font-size="8" fill="#FF9A2E" text-anchor="middle">创维降价¥200</text>';
h+='</svg></div>';

// SVG 折线图 - 销量
h+='<h4>近30天销量走势</h4>';
h+='<div style="background:var(--bg);border-radius:10px;padding:16px;margin:10px 0">';
h+='<div style="display:flex;align-items:center;gap:16px;margin-bottom:10px;font-size:11px">';
h+='<span style="display:flex;align-items:center;gap:4px"><span style="width:16px;height:3px;background:var(--purple);border-radius:1px"></span>海信65E7Q 日销量</span>';
h+='<span style="display:flex;align-items:center;gap:4px"><span style="width:16px;height:3px;background:var(--orange);border-radius:1px"></span>创维65A7Pro 日销量</span>';
h+='</div>';
h+='<svg viewBox="0 0 600 160" style="width:100%;height:auto;font-family:inherit">';
h+='<line x1="40" y1="10" x2="40" y2="130" stroke="#ECEDF0" stroke-width="0.5"/>';
h+='<line x1="40" y1="130" x2="580" y2="130" stroke="#ECEDF0" stroke-width="0.5"/>';
h+='<line x1="40" y1="70" x2="580" y2="70" stroke="#ECEDF0" stroke-width="0.5" stroke-dasharray="3"/>';
h+='<line x1="40" y1="10" x2="580" y2="10" stroke="#ECEDF0" stroke-width="0.5" stroke-dasharray="3"/>';
h+='<text x="35" y="14" font-size="9" fill="#86909C" text-anchor="end">60台</text>';
h+='<text x="35" y="74" font-size="9" fill="#86909C" text-anchor="end">35台</text>';
h+='<text x="35" y="134" font-size="9" fill="#86909C" text-anchor="end">10台</text>';
h+='<text x="40" y="148" font-size="9" fill="#86909C">6/18</text>';
h+='<text x="130" y="148" font-size="9" fill="#86909C">6/22</text>';
h+='<text x="220" y="148" font-size="9" fill="#86909C">6/26</text>';
h+='<text x="310" y="148" font-size="9" fill="#86909C">6/30</text>';
h+='<text x="400" y="148" font-size="9" fill="#86909C">7/4</text>';
h+='<text x="490" y="148" font-size="9" fill="#86909C">7/8</text>';
h+='<text x="560" y="148" font-size="9" fill="#86909C">7/12</text>';
// 海信销量线 (日均35台左右，稳中有升)
h+='<polyline fill="none" stroke="#0064fa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="40,72 58,68 76,74 94,70 112,66 130,68 148,62 166,64 184,60 202,58 220,56 238,54 256,52 274,50 292,48 310,46 328,44 346,42 364,40 382,38 400,40 418,38 436,36 454,34 472,32 490,34 508,32 526,30 544,28 562,30 580,28"/>';
// 创维销量线 (日均30台，降价后有拉升)
h+='<polyline fill="none" stroke="#FF9A2E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="40,82 58,84 76,80 94,82 112,78 130,80 148,82 166,84 184,82 202,80 220,78 238,74 256,66 274,60 292,56 310,52 328,50 346,48 364,46 382,48 400,50 418,52 436,54 454,56 472,54 490,56 508,58 526,56 544,58 562,60 580,58"/>';
// 标注
h+='<circle cx="256" cy="66" r="4" fill="#FF9A2E" stroke="#fff" stroke-width="1.5"/>';
h+='<text x="256" y="60" font-size="8" fill="#FF9A2E" text-anchor="middle">降价后销量拉升</text>';
h+='</svg></div>';

// 数据汇总表
h+='<h4>30天关键数据对比</h4>';
h+='<table><thead><tr><th>指标</th><th>海信 65E7Q</th><th>创维 65A7Pro</th><th>差异</th></tr></thead><tbody>';
h+='<tr><td>当前到手价</td><td><b>¥5,949</b></td><td>¥5,637</td><td>海信高¥312</td></tr>';
h+='<tr><td>30天最低价</td><td>¥5,949</td><td>¥5,437</td><td>海信高¥512</td></tr>';
h+='<tr><td>30天均价</td><td>¥5,949</td><td>¥5,587</td><td>海信高¥362</td></tr>';
h+='<tr><td>日均销量</td><td class="tag-ok"><b>36台</b></td><td>31台</td><td class="tag-ok">海信高16%</td></tr>';
h+='<tr><td>30天总销量</td><td class="tag-ok"><b>1,080台</b></td><td>930台</td><td class="tag-ok">海信多150台</td></tr>';
h+='<tr><td>价格波动</td><td class="tag-ok">0%（价格稳定）</td><td class="tag-mid">-3.6%</td><td>创维有降价</td></tr>';
h+='</tbody></table>';
h+='<div class="insight"><b>结论：</b>海信65E7Q过去30天价格零波动，体现强价格管控力；创维65A7Pro于6/26降价¥200后日销从30台升至38台（+27%），但近期回落至31台，降价效果未持续。海信虽贵¥312但日均销量仍领先16%，验证了品牌溢价能力。<br><b>建议：</b>继续维持稳价策略，创维降价已趋于见底未形成持续冲击，无需跟价。</div>';
} else if(q.indexOf('卖点')>=0||q.indexOf('值多少')>=0){
h+='<h4 style="color:var(--purple)">用户卖点价值分析（海信 65E7Q）</h4>';
h+='<p style="font-size:12px;color:var(--t3);margin-bottom:12px">用户卖点价值 ≠ 产品参数，而是用户从产品中最终获得并认可的好处。基于 VOC 评论 + 量价验证得出。</p>';

// 核心价值卡片
h+='<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px">';
h+='<div class="chat-value-item"><div style="display:flex;align-items:center;gap:6px;margin-bottom:6px"><span class="chat-value-kind">核心价值</span><span style="font-size:10px;color:var(--green)">✓ 量价已验证</span></div><div style="font-size:12px;font-weight:600;color:var(--t1);margin-bottom:4px">白天客厅画面仍清楚，暗场层次更完整</div><div style="font-size:11px;color:var(--t3)">来源：XDR 5200nits + 1920分区</div><div style="display:flex;gap:8px;margin-top:6px"><span style="font-size:10px;padding:2px 6px;background:#E8F5E9;color:#2E7D32;border-radius:3px">价高¥370</span><span style="font-size:10px;padding:2px 6px;background:#E8F5E9;color:#2E7D32;border-radius:3px">量高46台/周</span></div></div>';
h+='<div class="chat-value-item"><div style="display:flex;align-items:center;gap:6px;margin-bottom:6px"><span class="chat-value-kind">核心价值</span><span style="font-size:10px;color:var(--green)">✓ 量价已验证</span></div><div style="font-size:12px;font-weight:600;color:var(--t1);margin-bottom:4px">对白更清楚，声场包围感带来影院沉浸</div><div style="font-size:11px;color:var(--t3)">来源：6单元60W独立音响系统</div><div style="display:flex;gap:8px;margin-top:6px"><span style="font-size:10px;padding:2px 6px;background:#E8F5E9;color:#2E7D32;border-radius:3px">价高¥427</span><span style="font-size:10px;padding:2px 6px;background:#E8F5E9;color:#2E7D32;border-radius:3px">量高57台/周</span></div></div>';
h+='<div class="chat-value-item"><div style="display:flex;align-items:center;gap:6px;margin-bottom:6px"><span class="chat-value-kind">核心价值</span><span style="font-size:10px;color:var(--green)">✓ 量价已验证</span></div><div style="font-size:12px;font-weight:600;color:var(--t1);margin-bottom:4px">色彩更自然准确，人物和画面还原更真实</div><div style="font-size:11px;color:var(--t3)">来源：潘通+杜比双冠色彩认证 · 98% DCI-P3</div><div style="display:flex;gap:8px;margin-top:6px"><span style="font-size:10px;padding:2px 6px;background:#E8F5E9;color:#2E7D32;border-radius:3px">价高¥262</span><span style="font-size:10px;padding:2px 6px;background:#E8F5E9;color:#2E7D32;border-radius:3px">量高76台/周</span></div></div>';
h+='<div class="chat-value-item"><div style="display:flex;align-items:center;gap:6px;margin-bottom:6px"><span class="chat-value-kind">核心价值</span><span style="font-size:10px;color:var(--green)">✓ 量价已验证</span></div><div style="font-size:12px;font-weight:600;color:var(--t1);margin-bottom:4px">大屏观看更有临场感，客厅观影更沉浸</div><div style="font-size:11px;color:var(--t3)">来源：65寸大屏 + 影院级视觉体验定位</div><div style="display:flex;gap:8px;margin-top:6px"><span style="font-size:10px;padding:2px 6px;background:#E8F5E9;color:#2E7D32;border-radius:3px">价高¥279</span><span style="font-size:10px;padding:2px 6px;background:#E8F5E9;color:#2E7D32;border-radius:3px">量高62台/周</span></div></div>';
h+='</div>';

// 卖点分类表
h+='<h4>核心卖点（主推）</h4>';
h+='<table><thead><tr><th>产品原始卖点</th><th>形成的用户价值</th><th>量价验证</th></tr></thead><tbody>';
h+='<tr><td>XDR Pro 5200nits + 1920分区</td><td>白天画面清楚 · 暗场无光晕</td><td class="tag-ok">价高¥370 量高46台</td></tr>';
h+='<tr><td>6单元60W独立音响</td><td>对白清晰 · 声场包围感</td><td class="tag-ok">价高¥427 量高57台</td></tr>';
h+='<tr><td>潘通+杜比双冠色彩认证</td><td>色彩自然 · 画面真实</td><td class="tag-ok">价高¥262 量高76台</td></tr>';
h+='<tr><td>65寸影院级沉浸体验</td><td>大屏临场感 · 观影沉浸</td><td class="tag-ok">价高¥279 量高62台</td></tr>';
h+='</tbody></table>';

h+='<h4>基础卖点（保留不主推）</h4>';
h+='<table><thead><tr><th>产品原始卖点</th><th>说明</th></tr></thead><tbody>';
h+='<tr><td>U+ MiniLED光晕控制</td><td>支撑"暗场层次完整"，不独立构成用户价值</td></tr>';
h+='<tr><td>10.7亿色 · 98% DCI-P3 · △E≈0.7</td><td>支撑"色彩准确"，作为技术背书</td></tr>';
h+='</tbody></table>';

h+='<h4>待激活卖点（用户未认知）</h4>';
h+='<table><thead><tr><th>产品原始卖点</th><th>当前状态</th><th>建议</th></tr></thead><tbody>';
h+='<tr><td>4K 170Hz + 四路HDMI2.1</td><td>用户未认知（游戏提及率极低）</td><td>通过游戏实测视频激活</td></tr>';
h+='<tr><td>智感调光 · 20000Hz无屏闪</td><td>待确认（未形成稳定感知）</td><td>暂不主推，观察评论趋势</td></tr>';
h+='</tbody></table>';

// 量价验证汇总
h+='<h4>用户价值量价验证</h4>';
h+='<table><thead><tr><th>价值问题</th><th>参照竞品</th><th>价格</th><th>销量</th><th>结论</th></tr></thead><tbody>';
h+='<tr><td>影音用户是否愿为画质升级付费</td><td>TCL 65Q9L PRO · 创维 65A7H PRO</td><td class="tag-ok">高¥370</td><td class="tag-ok">高46台/周</td><td class="tag-ok">成立</td></tr>';
h+='<tr><td>画质价值能否解释当前加价</td><td>TCL 65Q9L PRO</td><td class="tag-ok">高¥427</td><td class="tag-ok">高57台/周</td><td class="tag-ok">成立</td></tr>';
h+='<tr><td>同尺寸是否形成画质越级感</td><td>TCL · 小米 L65MC-SP</td><td class="tag-ok">高¥262</td><td class="tag-ok">高76台/周</td><td class="tag-ok">成立</td></tr>';
h+='<tr><td>整体升级是否让用户觉得贵得值</td><td>TCL · 小米 · 创维</td><td class="tag-ok">高¥279</td><td class="tag-ok">高62台/周</td><td class="tag-ok">成立</td></tr>';
h+='</tbody></table>';

h+='<div class="insight"><b>结论：</b>4个核心用户价值全部通过量价验证——海信65E7Q相对竞品价高¥262~427的同时量高46~76台/周，当前定价有坚实的用户价值支撑。<br><b>建议：</b>主推"白天不拉帘也清楚"+音响免配回音壁的场景组合；游戏卖点(170Hz)需通过内容激活后再考虑升级主推。</div>';
} else {
h+='<p>正在为您分析中，请稍候...</p>';
}
h+=followupLine(q);
h+='<div class="feedback"><span>有用</span><span>没用</span><span>复制</span><span>生成报告</span></div></div>';
return h;
}
// 在回答末尾生成引导性追问文案（可点击直接追问）
function followupLine(q){
  q=q||'';
  var text,chips;
  if(q.indexOf('竞品')>=0){
    text='以上是当前重点竞品的对比。需要我进一步拆解某个竞品的价格带差距、补充近30天销量趋势，或给出针对性的竞价调整建议吗？';
    chips=['对比 TCL 65Q9L PRO 的价格带差距','看近30天销量趋势','给出竞价调整建议'];
  }else if(q.indexOf('调整')>=0||q.indexOf('调价')>=0||q.indexOf('竞价')>=0||q.indexOf('策略')>=0){
    text='以上是调价方向的建议。需要我进一步测算利润影响、按回报对型号排序，或列出调价后要监控的风险指标吗？';
    chips=['测算利润影响','按回报排序型号','列出需监控的风险指标'];
  }else if(q.indexOf('异常')>=0||q.indexOf('预警')>=0||q.indexOf('紧急')>=0){
    text='以上是异常的初步定位。需要我进一步给出根因证据链、梳理受影响的型号与渠道，或提供可立即执行的处置动作吗？';
    chips=['给出根因证据链','梳理受影响型号与渠道','提供可执行的处置动作'];
  }else if(q.indexOf('新品')>=0||q.indexOf('上市')>=0){
    text='以上是竞品新品的概览。需要我进一步分析新品与我品的战场重合、拆解其定价与配置亮点，或给出应对建议吗？';
    chips=['分析战场重合','拆解定价与配置亮点','给出应对建议'];
  }else{
    text='以上是本次分析结果。需要我结合数据进一步展开、说明对经营决策的影响，或给出下一步优先动作吗？';
    chips=['结合数据进一步展开','说明对经营决策的影响','给出下一步优先动作'];
  }
  var s='<div class="followup-line"><p>'+text+'</p><div class="followup-chips">';
  for(var i=0;i<chips.length;i++){
    var safe=chips[i].replace(/'/g,"\\'");
    s+='<span class="followup-chip" onclick="askQ(\''+safe+'\')">'+chips[i]+'</span>';
  }
  s+='</div></div>';
  return s;
}
// COMPETITOR_PRODUCT_COMPARE_V12_LOGIC
const competitorWeekTrend=window.gtmRecords.competitorWeekTrend;
competitorWeekTrend.models.forEach(function(m){m.revenue=m.units.map(function(v,i){return Number((v*m.price[i]/10000).toFixed(1))})});
let competitorTrendMetric='units',compTrendPlotXs=[];
const competitorMetricMeta=window.gtmRecords.competitorMetricMeta;
function switchCompetitorMetric(metric,btn){
  competitorTrendMetric=metric;
  document.querySelectorAll('.comp-metric-tab').forEach(function(x){x.classList.toggle('active',x===btn)});
  renderCompetitorTrend();
}
function toggleCompetitorTrend(){
  var body=document.getElementById('compTrendBody'),head=document.getElementById('compTrendHead'),fold=document.getElementById('compTrendFoldText');
  var hidden=body.classList.toggle('hidden');
  head.classList.toggle('collapsed',hidden);
  fold.textContent=hidden?'点击展开':'点击收起';
}
function toggleSellingPoints(){
  var section=document.getElementById('sellingPointSection'),btn=document.getElementById('sellingPointExpandBtn');
  var expanded=section.classList.toggle('expanded');
  btn.textContent=expanded?'收起扩展卖点':'展开查看更多卖点';
}
function compSmoothPath(points){
  if(!points.length)return'';
  var d='M'+points[0].x.toFixed(1)+','+points[0].y.toFixed(1);
  for(var i=0;i<points.length-1;i++){
    var p0=points[i-1]||points[i],p1=points[i],p2=points[i+1],p3=points[i+2]||p2;
    var c1x=p1.x+(p2.x-p0.x)/6,c1y=p1.y+(p2.y-p0.y)/6;
    var c2x=p2.x-(p3.x-p1.x)/6,c2y=p2.y-(p3.y-p1.y)/6;
    d+=' C'+c1x.toFixed(1)+','+c1y.toFixed(1)+' '+c2x.toFixed(1)+','+c2y.toFixed(1)+' '+p2.x.toFixed(1)+','+p2.y.toFixed(1);
  }
  return d;
}
function compFormatValue(value,metric){
  if(metric==='price')return'¥'+Math.round(value).toLocaleString('zh-CN');
  if(metric==='revenue')return Number(value).toFixed(1)+'万元';
  return Math.round(value).toLocaleString('zh-CN')+'台';
}
function renderCompetitorTrend(){
  var host=document.getElementById('competitorTrendChart');
  if(!host)return;
  var metric=competitorTrendMetric,meta=competitorMetricMeta[metric],models=competitorWeekTrend.models,weeks=competitorWeekTrend.weeks;
  var width=1120,height=300,left=58,right=20,top=22,bottom=42,plotW=width-left-right,plotH=height-top-bottom;
  var maxValue=Math.max.apply(null,models.reduce(function(a,m){return a.concat(m[metric])},[]));
  var step=metric==='units'?200:(metric==='revenue'?100:1000),yMax=Math.max(step,Math.ceil(maxValue/step)*step);
  compTrendPlotXs=weeks.map(function(_,i){return left+(plotW*i/(weeks.length-1))});
  document.getElementById('compAxisTitle').textContent=meta.title;
  document.getElementById('compTrendLegend').innerHTML=models.map(function(m,i){return'<span><i style="background:'+m.color+'"></i>'+m.name+(i===0?' · 我品':'')+'</span>'}).join('');
  var svg='<svg viewBox="0 0 '+width+' '+height+'" role="img" aria-label="'+meta.label+'年周趋势对比"><defs><linearGradient id="compOwnArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#0aa9a1" stop-opacity=".18"/><stop offset="100%" stop-color="#0aa9a1" stop-opacity=".02"/></linearGradient></defs>';
  for(var g=0;g<=5;g++){
    var gy=top+plotH*g/5,gv=Math.round(yMax*(1-g/5));
    svg+='<line class="grid-line" x1="'+left+'" y1="'+gy+'" x2="'+(width-right)+'" y2="'+gy+'"/><text class="axis-label" x="'+(left-10)+'" y="'+(gy+4)+'" text-anchor="end">'+(metric==='price'?'¥':'')+gv.toLocaleString('zh-CN')+'</text>';
  }
  weeks.forEach(function(w,i){svg+='<text class="week-label" x="'+compTrendPlotXs[i]+'" y="'+(height-16)+'" text-anchor="middle">'+w+'</text>'});
  models.forEach(function(m,mi){
    var pts=m[metric].map(function(v,i){return{x:compTrendPlotXs[i],y:top+plotH*(1-v/yMax)}});
    var path=compSmoothPath(pts);
    if(m.own)svg+='<path d="'+path+' L'+pts[pts.length-1].x+','+(top+plotH)+' L'+pts[0].x+','+(top+plotH)+' Z" fill="url(#compOwnArea)"/>';
    svg+='<path class="series-line" d="'+path+'" stroke="'+m.color+'" stroke-width="'+(m.own?4:2.5)+'" '+(m.own?'':'stroke-dasharray="8 6"')+'/>';
    pts.forEach(function(p){svg+='<circle cx="'+p.x+'" cy="'+p.y+'" r="'+(m.own?3.3:2.7)+'" fill="#fff" stroke="'+m.color+'" stroke-width="2"/>'});
  });
  svg+='<line id="compFocusLine" class="comp-focus-line" x1="'+left+'" y1="'+top+'" x2="'+left+'" y2="'+(top+plotH)+'"/>';
  weeks.forEach(function(_,i){var zone=plotW/(weeks.length-1),zx=i===0?left-zone/2:compTrendPlotXs[i]-zone/2;svg+='<rect class="comp-trend-hit" x="'+zx+'" y="'+top+'" width="'+zone+'" height="'+plotH+'" onmouseenter="showCompTrendTooltip('+i+',event)" onmousemove="moveCompTrendTooltip(event)" onmouseleave="hideCompTrendTooltip()"/>'});
  svg+='</svg>';
  host.innerHTML=svg;
}
function showCompTrendTooltip(index,event){
  var tip=document.getElementById('compTrendTooltip'),metric=competitorTrendMetric;
  tip.innerHTML='<b>'+competitorWeekTrend.weeks[index]+' · '+competitorMetricMeta[metric].label+'</b>'+competitorWeekTrend.models.map(function(m){return'<div class="comp-tooltip-row"><i style="background:'+m.color+'"></i><span>'+m.name+'</span><strong>'+compFormatValue(m[metric][index],metric)+'</strong></div>'}).join('');
  tip.classList.add('show');
  var line=document.getElementById('compFocusLine');if(line){line.style.display='block';line.setAttribute('x1',compTrendPlotXs[index]);line.setAttribute('x2',compTrendPlotXs[index])}
  moveCompTrendTooltip(event);
}
function moveCompTrendTooltip(event){
  var tip=document.getElementById('compTrendTooltip'),card=tip.parentElement,box=card.getBoundingClientRect();
  var x=event.clientX-box.left+12,y=event.clientY-box.top-tip.offsetHeight-12;
  if(x+tip.offsetWidth>box.width-8)x=event.clientX-box.left-tip.offsetWidth-12;
  if(y<6)y=event.clientY-box.top+14;
  tip.style.left=x+'px';tip.style.top=y+'px';
}
function hideCompTrendTooltip(){
  var tip=document.getElementById('compTrendTooltip'),line=document.getElementById('compFocusLine');
  if(tip)tip.classList.remove('show');if(line)line.style.display='none';
}
renderCompetitorTrend();
// ANALYSIS_REDESIGN_V14_LOGIC_A
const sellingPointWeightData=window.gtmRecords.sellingPointWeightData;
function selectedCompetitorModelNames(){
 return Array.from(document.querySelectorAll('#modelTags .model-tag:not(.own):not(.add):not(.off)')).map(function(x){return x.childNodes[0].textContent.trim()});
}
function renderSellingPointWeight(){
 var select=document.getElementById('weightPointSelect');if(!select)return;
 var d=sellingPointWeightData[select.value],selected=selectedCompetitorModelNames();
 var players=d.players.filter(function(p){return p.name==='海信 65E7Q'||p.name==='行业平均'||selected.indexOf(p.name)>-1});
 var wov=document.getElementById('weightOwnValue');if(wov)wov.textContent='¥'+d.ownValue;
 var wbi=document.getElementById('weightBrandIndex');if(wbi)wbi.textContent=d.brandIndex.toFixed(2);
 var wsl=document.getElementById('weightSalesLift');if(wsl)wsl.textContent=d.salesLift;
 var wcf=document.getElementById('weightConfidence');if(wcf)wcf.textContent=d.confidence;
 var pill=document.getElementById('weightTypePill');if(pill){pill.textContent=d.type;pill.className='pill '+(d.type==='高价值卖点'?'purple':'green')}
 var wvh=document.getElementById('weightValueHint');if(wvh)wvh.textContent=d.name+' · 相对行业同类配置';
 var tbl=document.getElementById('weightCompareTable');if(!tbl)return;
 var header='<thead><tr><th>对比项</th>'+players.map(function(p,i){return'<th class="'+(i===0?'own-col':'')+'">'+p.name+'</th>'}).join('')+'</tr></thead>';
 function row(label,key,format){return'<tr><td>'+label+'</td>'+players.map(function(p,i){return'<td class="'+(i===0?'own-col':'')+'">'+(format?format(p[key],p):p[key])+'</td>'}).join('')+'</tr>'}
 var diff=d.ownValue;
 var body='<tbody>'+row('同类参数','param')+row('卖点分类','name',function(){return d.type})+row('估算卖点价值','value',function(v){return'¥'+v})+row('代表型号周销量','sales')+row('品牌溢价指数','index')+row('相对我品价值差','value',function(v,p){var n=v-diff;return n===0?'基准':(n>0?'+':'')+'¥'+n})+'</tbody>';
 tbl.innerHTML=header+body;
}
const premiumBrandData=window.gtmRecords.premiumBrandData;
function getPremiumSelectedBrands(){
 var own=document.getElementById('premiumOwnBrand').value;
 var comps=Array.from(document.querySelectorAll('#premiumBrandMenu input:checked:not(:disabled)')).map(function(x){return x.value});
 return{own:own,comps:comps};
}
function syncPremiumBrandOptions(){
 var own=document.getElementById('premiumOwnBrand').value;
 document.querySelectorAll('#premiumBrandMenu label').forEach(function(label){var cb=label.querySelector('input'),same=cb.value===own;if(same)cb.checked=false;cb.disabled=same;label.classList.toggle('disabled',same)});
 updatePremiumBrandTrigger();
}
function updatePremiumBrandTrigger(){
 var comps=getPremiumSelectedBrands().comps,trigger=document.getElementById('premiumMultiTrigger');
 trigger.innerHTML=(comps.length?comps.join('、'):'请选择竞争品牌')+' <span>⌄</span>';
}
function togglePremiumBrandMenu(event){event.stopPropagation();document.getElementById('premiumBrandMenu').classList.toggle('show')}
function updatePremiumBrandSelection(){updatePremiumBrandTrigger();markPremiumDirty()}
function markPremiumDirty(){var s=document.getElementById('premiumScopeStatus');if(s){s.textContent='筛选已修改，请点击生成品牌溢价分析报告';s.classList.add('dirty')}}
function runPremiumAnalysis(){
 var sel=getPremiumSelectedBrands();if(!sel.comps.length){showToast('请至少选择一个竞争品牌');return}
 var btn=document.getElementById('premiumRunBtn');btn.disabled=true;btn.textContent='报告生成中…';
 setTimeout(function(){renderPremiumAnalysis();btn.disabled=false;btn.textContent='生成品牌溢价分析报告';showToast('品牌溢价分析报告已生成')},520);
}
function renderPremiumAnalysis(){
 var sel=getPremiumSelectedBrands(),brands=[sel.own].concat(sel.comps),own=premiumBrandData[sel.own],comps=sel.comps.map(function(n){return premiumBrandData[n]});
 var avgPremium=comps.reduce(function(a,b){return a+b.premium},0)/comps.length,avgPrice=comps.reduce(function(a,b){return a+b.price},0)/comps.length;
 var lead=own.premium-avgPremium;
 var pas=document.getElementById('premiumAiSummary');if(pas)pas.innerHTML=sel.own+'品牌溢价指数为 <b>'+own.premium.toFixed(2)+'</b>，较所选竞争品牌均值领先 <b>'+lead.toFixed(2)+'</b>。其中价格指数贡献'+(own.price*.7).toFixed(2)+'，VOC品牌认同贡献'+(own.vocIndex*.3).toFixed(2)+'；建议保持优势价格带，并针对竞品VOC强项补齐用户体验。';
  var pic=document.getElementById('premiumIndexCompare');if(pic)pic.innerHTML=brands.map(function(n,i){var d=premiumBrandData[n];return'<article class="premium-index-item '+(i===0?'own':'')+'"><div class="brand"><span>'+n+(i===0?' · 我方':'')+'</span><i style="width:9px;height:9px;border-radius:50%;background:'+d.color+'"></i></div><div class="score">'+d.premium.toFixed(2)+'</div><div class="parts"><span>价格指数 '+d.price.toFixed(2)+'</span><span>VOC指数 '+d.vocIndex.toFixed(2)+'</span></div></article>'}).join('');
  var ratio=(own.price/avgPrice-1)*100,avgSegments=[0,1,2,3,4].map(function(i){return comps.reduce(function(a,b){return a+b.segments[i]},0)/comps.length}),adv=own.segments.filter(function(v,i){return v>avgSegments[i]}).length;
 var pkr=document.getElementById('premiumKpiRatio');if(pkr)pkr.textContent=(ratio>=0?'+':'')+ratio.toFixed(1)+'%';
 var pka=document.getElementById('premiumKpiAmount');if(pka)pka.textContent=(own.amount>=0?'+':'-')+'¥'+Math.abs(own.amount).toLocaleString('zh-CN');
 var pks=document.getElementById('premiumKpiSegments');if(pks)pks.textContent=adv+' / 5';
 var pksh=document.getElementById('premiumKpiShare');if(pksh)pksh.textContent=own.share.toFixed(1)+'%';
 renderPremiumPriceChart(brands);
 var sizes=['<32寸','32-40寸','51-60寸','60-70寸','≥70寸'];
 var pst=document.getElementById('premiumSegmentTable');if(pst)pst.innerHTML='<thead><tr><th>尺寸段</th><th>'+sel.own+'</th><th>竞品均值</th><th>判断</th></tr></thead><tbody>'+sizes.map(function(s,i){var a=own.segments[i],b=avgSegments[i],ok=a>b;return'<tr><td>'+s+'</td><td class="'+(ok?'best':'')+'">'+(a>=0?'+':'')+a.toFixed(1)+'%</td><td>'+(b>=0?'+':'')+b.toFixed(1)+'%</td><td><span class="pill '+(ok?'green':'orange')+'">'+(ok?'领先':'承压')+'</span></td></tr>'}).join('')+'</tbody>';
 var pdt=document.getElementById('premiumDetailTable');if(pdt)pdt.innerHTML='<thead><tr><th>尺寸区间</th><th>行业基准</th>'+brands.map(function(n,i){return'<th class="'+(i===0?'own-col':'')+'">'+n+'价格指数</th>'}).join('')+'</tr></thead><tbody>'+sizes.map(function(s,i){return'<tr><td>'+s+'</td><td>1.00</td>'+brands.map(function(n,j){return'<td class="'+(j===0?'own-col':'')+'">'+premiumBrandData[n].size[i].toFixed(2)+'</td>'}).join('')+'</tr>'}).join('')+'</tbody>';
  var status=document.getElementById('premiumScopeStatus');if(status){status.textContent='当前：'+sel.own+' vs '+sel.comps.join('、');status.classList.remove('dirty')}
  renderPremiumVocTop5(brands);
 }
function renderPremiumPriceChart(brands){
 var host=document.getElementById('premiumPriceIndexChart');if(!host)return;var weeks=['26W18','26W19','26W20','26W21','26W22','26W23','26W24','26W25'];
 var w=620,h=220,l=40,r=12,t=24,b=30,pw=w-l-r,ph=h-t-b,min=.85,max=1.35;
 var xs=weeks.map(function(_,i){return l+pw*i/(weeks.length-1)});
 var svg='<div class="legend">'+brands.map(function(n){return'<span><i style="background:'+premiumBrandData[n].color+'"></i>'+n+'</span>'}).join('')+'</div><svg viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none" class="pz-chart-svg">';
 [1.3,1.2,1.1,1.0,.9].forEach(function(v){var y=t+ph*(max-v)/(max-min);svg+='<line class="grid-line" x1="'+l+'" y1="'+y+'" x2="'+(w-r)+'" y2="'+y+'"/><text x="'+(l-6)+'" y="'+(y+3)+'" text-anchor="end">'+v.toFixed(2)+'</text>'});
 weeks.forEach(function(x,i){svg+='<text x="'+xs[i]+'" y="'+(h-8)+'" text-anchor="middle">'+x+'</text>'});
 brands.forEach(function(n,i){var d=premiumBrandData[n],pts=d.trend.map(function(v,j){return{x:xs[j],y:t+ph*(max-v)/(max-min)}});svg+='<path class="brand-line" d="'+compSmoothPath(pts)+'" stroke="'+d.color+'" stroke-width="'+(i===0?3.5:2.2)+'" '+(i===0?'':'stroke-dasharray="7 5"')+'/>';svg+='<g class="pz-dot-group" data-brand="'+n+'">'+pts.map(function(p,j){return'<circle class="pz-dot" cx="'+p.x+'" cy="'+p.y+'" r="'+(i===0?4:3)+'" fill="'+d.color+'" stroke="#fff" stroke-width="2" style="opacity:0" data-week="'+j+'"/>'}).join('')+'</g>'});
 svg+='<g class="pz-hover-vline" style="opacity:0"><line x1="0" y1="'+t+'" x2="0" y2="'+(h-b)+'" stroke="#B0B6C0" stroke-width="1" stroke-dasharray="4 3"/></g>';
 svg+='</svg><div class="pz-tooltip" id="pzTooltip"></div>';
 svg+='<div class="pz-hover-zone" id="pzHoverZone"></div>';
 host.innerHTML=svg;
 var zone=document.getElementById('pzHoverZone'),tip=document.getElementById('pzTooltip'),vline=host.querySelector('.pz-hover-vline line');
 var vlineG=host.querySelector('.pz-hover-vline');
 zone.style.cssText='position:absolute;top:'+t+'px;left:'+l+'px;right:'+r+'px;bottom:'+b+'px;cursor:crosshair';
 host.style.position='relative';
 function showTooltip(idx,clientX){var html='<div class="pz-tip-title">'+weeks[idx]+'</div>';brands.forEach(function(n,i){var d=premiumBrandData[n];html+='<div class="pz-tip-row"><span class="pz-tip-dot" style="background:'+d.color+'"></span><span class="pz-tip-name">'+n+(i===0?' · 我品':'')+'</span><span class="pz-tip-val">'+d.trend[idx].toFixed(2)+'</span></div>'});tip.innerHTML=html;tip.style.display='block';var rect=host.getBoundingClientRect();var tipW=tip.offsetWidth,tipH=tip.offsetHeight;var left=clientX-rect.left+12;if(left+tipW>rect.width-8)left=clientX-rect.left-tipW-12;tip.style.left=left+'px';var top=20;if(top+tipH>h-b)top=h-b-tipH;tip.style.top=top+'px';vline.setAttribute('x1',xs[idx]);vline.setAttribute('x2',xs[idx]);vlineG.style.opacity='1';host.querySelectorAll('.pz-dot-group .pz-dot').forEach(function(dot){if(+dot.dataset.week===idx){dot.style.opacity='1'}else{dot.style.opacity='0'}})}
 function hideTooltip(){tip.style.display='none';vlineG.style.opacity='0';host.querySelectorAll('.pz-dot').forEach(function(d){d.style.opacity='0'})}
 zone.addEventListener('mousemove',function(e){var rect=zone.getBoundingClientRect();var relX=e.clientX-rect.left;var idx=0,minDist=Infinity;xs.forEach(function(x,i){var dist=Math.abs(x-l-relX);if(dist<minDist){minDist=dist;idx=i}});showTooltip(idx,e.clientX)});
 zone.addEventListener('mouseleave',hideTooltip);
}
document.addEventListener('click',function(e){var menu=document.getElementById('premiumBrandMenu');if(menu&&!e.target.closest('.premium-competitor-filter'))menu.classList.remove('show')});

/* 品牌溢价分析-子Tab切换 */
function switchPremiumSubTab(el,ev){
  if(ev)ev.stopPropagation();
  var target=el.dataset.target;
  document.querySelectorAll('[data-group=premium-sub] .tab').forEach(function(t){t.classList.toggle('active',t===el)});
  document.querySelectorAll('.premium-sub-panel').forEach(function(p){p.classList.toggle('active',p.id==='panel-'+target)});
}

/* 品牌VOC TOP5 三卡片渲染 */
var premiumVocTop5Data=window.gtmRecords.premiumVocTop5Data;
function renderPremiumVocTop5(brands){
  var host=document.getElementById('premiumVocCompare');if(!host)return;
  var parent=host.closest('.premium-voc-grid');
  if(parent)parent.style.setProperty('--premium-brand-count',brands.length);
  host.style.setProperty('--premium-brand-count',brands.length);
  host.innerHTML=brands.map(function(n,i){
    var items=premiumVocTop5Data[n]||premiumVocTop5Data['海信'];
    var d=premiumBrandData[n];
    return '<article class="premium-voc-card '+(i===0?'own':'')+'">'+
      '<h3>'+n+(i===0?' · 我方':'')+' VOC TOP5</h3>'+
      items.map(function(v,j){
        return '<div class="premium-voc-item"><i>'+(j+1)+'</i><span>'+v[0]+'</span><b>'+v[1]+'</b></div>';
      }).join('')+
      '</article>';
  }).join('');
}
function toggleSellingPoints(){var s=document.getElementById('sellingPointSection'),b=document.getElementById('sellingPointExpandBtn'),x=s.classList.toggle('expanded');b.textContent=x?'收起其余卖点':'展开其余卖点'}
function toggleModel(el){el.classList.toggle('off');renderSellingPointWeight();renderPriceVolumeCombined();renderActualPVCombined()}
function syncAnalysisScope(target){
 var premium=target==='premium',productScope=document.getElementById('productScope'),brandScope=document.getElementById('brandScope'),tabs=document.getElementById('analysisTabs');
 if(productScope)productScope.style.display=premium?'none':'block';if(brandScope)brandScope.classList.toggle('show',premium);if(tabs)tabs.style.display=premium?'none':'flex';
 var title=document.getElementById('analysisTitle'),subtitle=document.getElementById('analysisSubtitle'),period=document.getElementById('analysisPeriod'),label=document.getElementById('generateBtnLabel'),generate=document.getElementById('generateBtn'),exportBtn=document.getElementById('analysisExportBtn');
 if(title)title.textContent=premium?'品牌溢价分析':'竞品分析';if(subtitle)subtitle.textContent=premium?'对比我方与竞争品牌的价格指数、VOC认同及综合品牌溢价指数':'按型号比较产品、卖点和量价表现';if(period){period.style.display=premium?'none':'block';period.value='30d';var dr=document.getElementById('analysisDateRange');if(dr)dr.style.display='none'}if(label)label.textContent=analysisReportName(target);if(generate)generate.style.display=premium?'none':'inline-flex';if(exportBtn)exportBtn.style.display=premium?'none':'inline-flex';
}
syncPremiumBrandOptions();
renderSellingPointWeight();
renderPremiumAnalysis();
// ANALYSIS_REDESIGN_V14_LOGIC_B
let priceVolumeHighlight=null,priceVolumePlotXs=[];
function priceVolumeModels(){
 var selected=['海信 65E7Q'].concat(selectedCompetitorModelNames());
 return competitorWeekTrend.models.filter(function(m){return selected.indexOf(m.name)>-1});
}
function togglePriceVolumeHighlight(name){
 priceVolumeHighlight=priceVolumeHighlight===name?null:name;
 renderPriceVolumeCombined();
}
function pvMetricValue(v,metric){
 if(metric==='price')return'¥'+Math.round(v).toLocaleString('zh-CN');
 if(metric==='units')return Math.round(v).toLocaleString('zh-CN')+'台';
 return Number(v).toFixed(1)+'万元';
}
function renderPriceVolumeCombined(){
 var host=document.getElementById('priceVolumeCombinedChart'),legend=document.getElementById('priceVolumeProductLegend');if(!host||!legend)return;
 var models=priceVolumeModels();if(priceVolumeHighlight&&!models.some(function(m){return m.name===priceVolumeHighlight}))priceVolumeHighlight=null;
 legend.innerHTML=models.map(function(m){var active=priceVolumeHighlight===m.name,muted=priceVolumeHighlight&& !active;return'<button class="pv-product-chip '+(active?'active ':'')+(muted?'muted':'')+'" onclick="togglePriceVolumeHighlight(\''+m.name+'\')"><i style="background:'+m.color+'"></i>'+m.name+(m.own?' · 我品':'')+'</button>'}).join('');
 var weeks=competitorWeekTrend.weeks,w=1120,h=500,l=68,r=22,top=18,bandH=125,gap=25,pw=w-l-r;
 priceVolumePlotXs=weeks.map(function(_,i){return l+pw*i/(weeks.length-1)});
 var metrics=[{key:'price',label:'均价',unit:'元',dash:''},{key:'units',label:'销量',unit:'台',dash:'8 5'},{key:'revenue',label:'销额',unit:'万元',dash:'2 5'}];
 var svg='<svg viewBox="0 0 '+w+' '+h+'" role="img" aria-label="我品及竞品均价销量销额组合趋势">';
 metrics.forEach(function(meta,mi){
  var y0=top+mi*(bandH+gap),vals=models.reduce(function(a,m){return a.concat(m[meta.key])},[]),rawMin=Math.min.apply(null,vals),rawMax=Math.max.apply(null,vals);
  var min=meta.key==='price'?Math.floor(rawMin*.94/100)*100:0,max=meta.key==='price'?Math.ceil(rawMax*1.04/100)*100:Math.ceil(rawMax/(meta.key==='units'?200:100))*(meta.key==='units'?200:100);
  if(max<=min)max=min+1;
  svg+='<rect class="band-bg" x="'+l+'" y="'+y0+'" width="'+pw+'" height="'+bandH+'" rx="6"/><text x="10" y="'+(y0+16)+'" style="font-size:11px;font-weight:700;fill:#3f4855">'+meta.label+'</text><text x="10" y="'+(y0+31)+'">'+meta.unit+'</text>';
  for(var g=0;g<=2;g++){var y=y0+bandH*g/2,v=max-(max-min)*g/2;svg+='<line class="grid-line" x1="'+l+'" y1="'+y+'" x2="'+(w-r)+'" y2="'+y+'"/><text x="'+(l-7)+'" y="'+(y+3)+'" text-anchor="end">'+(meta.key==='price'?'¥':'')+Math.round(v).toLocaleString('zh-CN')+'</text>'}
  models.forEach(function(m){
   var focus=!priceVolumeHighlight||priceVolumeHighlight===m.name,pts=m[meta.key].map(function(v,i){return{x:priceVolumePlotXs[i],y:y0+bandH*(1-(v-min)/(max-min))}});
   svg+='<path class="pv-series" d="'+compSmoothPath(pts)+'" stroke="'+(focus?m.color:'#bfc5cc')+'" stroke-width="'+(focus?(priceVolumeHighlight?4:2.6):1.6)+'" opacity="'+(focus?1:.35)+'" '+(meta.dash?'stroke-dasharray="'+meta.dash+'"':'')+'/>';
   pts.forEach(function(p){svg+='<circle class="pv-point" cx="'+p.x+'" cy="'+p.y+'" r="'+(focus?2.5:1.8)+'" fill="#fff" stroke="'+(focus?m.color:'#bfc5cc')+'" stroke-width="1.6" opacity="'+(focus?1:.35)+'"/>'});
  });
 });
 weeks.forEach(function(x,i){svg+='<text x="'+priceVolumePlotXs[i]+'" y="'+(h-8)+'" text-anchor="middle">'+x+'</text>'});
 var zone=pw/(weeks.length-1);
 weeks.forEach(function(_,i){var x=i===0?l-zone/2:priceVolumePlotXs[i]-zone/2;svg+='<rect class="pv-hit" x="'+x+'" y="'+top+'" width="'+zone+'" height="'+(3*bandH+2*gap)+'" onmouseenter="showPriceVolumeTooltip('+i+',event)" onmousemove="movePriceVolumeTooltip(event)" onmouseleave="hidePriceVolumeTooltip()"/>'});
 svg+='</svg>';host.innerHTML=svg;
}
function showPriceVolumeTooltip(index,event){
 var tip=document.getElementById('priceVolumeTooltip'),models=priceVolumeModels();
 var visible=priceVolumeHighlight?models.filter(function(m){return m.name===priceVolumeHighlight}):models;
 tip.innerHTML='<b>'+competitorWeekTrend.weeks[index]+' · 实际量价额</b>'+visible.map(function(m){return'<div style="border-top:1px solid rgba(255,255,255,.14);padding-top:5px;margin-top:5px"><div class="comp-tooltip-row"><i style="background:'+m.color+'"></i><span>'+m.name+'</span></div><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:5px;font-size:9px"><span>均价<br><strong>'+pvMetricValue(m.price[index],'price')+'</strong></span><span>销量<br><strong>'+pvMetricValue(m.units[index],'units')+'</strong></span><span>销额<br><strong>'+pvMetricValue(m.revenue[index],'revenue')+'</strong></span></div></div>'}).join('');
 tip.classList.add('show');movePriceVolumeTooltip(event);
}
function movePriceVolumeTooltip(event){
 var tip=document.getElementById('priceVolumeTooltip'),card=tip.parentElement,box=card.getBoundingClientRect();
 var x=event.clientX-box.left+12,y=event.clientY-box.top-tip.offsetHeight-12;
 if(x+tip.offsetWidth>box.width-8)x=event.clientX-box.left-tip.offsetWidth-12;if(y<6)y=event.clientY-box.top+14;
 tip.style.left=x+'px';tip.style.top=y+'px';
}
function hidePriceVolumeTooltip(){var tip=document.getElementById('priceVolumeTooltip');if(tip)tip.classList.remove('show')}
let actualPVHighlight=null;
function toggleActualPVHighlight(name){actualPVHighlight=actualPVHighlight===name?null:name;renderActualPVCombined()}
function renderActualPVCombined(){
 var host=document.getElementById('actualPVCombinedChart'),legend=document.getElementById('actualPVProductLegend');if(!host||!legend)return;
 var models=priceVolumeModels();if(actualPVHighlight&&!models.some(function(m){return m.name===actualPVHighlight}))actualPVHighlight=null;
 legend.innerHTML=models.map(function(m){var active=actualPVHighlight===m.name,muted=actualPVHighlight&& !active;return'<button class="pv-product-chip '+(active?'active ':'')+(muted?'muted':'')+'" onclick="toggleActualPVHighlight(\''+m.name+'\')"><i style="background:'+m.color+'"></i>'+m.name+(m.own?' · 我品':'')+'</button>'}).join('');
 var weeks=competitorWeekTrend.weeks,w=1120,h=500,l=68,r=22,top=18,bandH=125,gap=25,pw=w-l-r;
 var xs=weeks.map(function(_,i){return l+pw*i/(weeks.length-1)});
 var metrics=[{key:'price',label:'均价',unit:'元',dash:''},{key:'units',label:'销量',unit:'台',dash:'8 5'},{key:'revenue',label:'销额',unit:'万元',dash:'2 5'}];
 var svg='<svg viewBox="0 0 '+w+' '+h+'" role="img" aria-label="实际均价销量销额组合趋势">';
 metrics.forEach(function(meta,mi){
  var y0=top+mi*(bandH+gap),vals=models.reduce(function(a,m){return a.concat(m[meta.key])},[]),rawMin=Math.min.apply(null,vals),rawMax=Math.max.apply(null,vals);
  var min=meta.key==='price'?Math.floor(rawMin*.94/100)*100:0,max=meta.key==='price'?Math.ceil(rawMax*1.04/100)*100:Math.ceil(rawMax/(meta.key==='units'?200:100))*(meta.key==='units'?200:100);
  if(max<=min)max=min+1;
  svg+='<rect class="band-bg" x="'+l+'" y="'+y0+'" width="'+pw+'" height="'+bandH+'" rx="6"/><text x="10" y="'+(y0+16)+'" style="font-size:11px;font-weight:700;fill:#3f4855">'+meta.label+'</text><text x="10" y="'+(y0+31)+'">'+meta.unit+'</text>';
  for(var g=0;g<=2;g++){var y=y0+bandH*g/2,v=max-(max-min)*g/2;svg+='<line class="grid-line" x1="'+l+'" y1="'+y+'" x2="'+(w-r)+'" y2="'+y+'"/><text x="'+(l-7)+'" y="'+(y+3)+'" text-anchor="end">'+(meta.key==='price'?'¥':'')+Math.round(v).toLocaleString('zh-CN')+'</text>'}
  models.forEach(function(m){
   var focus=!actualPVHighlight||actualPVHighlight===m.name,pts=m[meta.key].map(function(v,i){return{x:xs[i],y:y0+bandH*(1-(v-min)/(max-min))}});
   svg+='<path class="pv-series" d="'+compSmoothPath(pts)+'" stroke="'+(focus?m.color:'#bfc5cc')+'" stroke-width="'+(focus?(actualPVHighlight?4:2.6):1.6)+'" opacity="'+(focus?1:.35)+'" '+(meta.dash?'stroke-dasharray="'+meta.dash+'"':'')+'/>';
   pts.forEach(function(p){svg+='<circle class="pv-point" cx="'+p.x+'" cy="'+p.y+'" r="'+(focus?2.5:1.8)+'" fill="#fff" stroke="'+(focus?m.color:'#bfc5cc')+'" stroke-width="1.6" opacity="'+(focus?1:.35)+'"/>'});
  });
 });
 weeks.forEach(function(x,i){svg+='<text x="'+xs[i]+'" y="'+(h-8)+'" text-anchor="middle">'+x+'</text>'});
 var zone=pw/(weeks.length-1);
 weeks.forEach(function(_,i){var x=i===0?l-zone/2:xs[i]-zone/2;svg+='<rect class="pv-hit" x="'+x+'" y="'+top+'" width="'+zone+'" height="'+(3*bandH+2*gap)+'" onmouseenter="showActualPVTooltip('+i+',event)" onmousemove="moveActualPVTooltip(event)" onmouseleave="hideActualPVTooltip()"/>'});
 svg+='</svg>';host.innerHTML=svg;
}
function showActualPVTooltip(index,event){
 var tip=document.getElementById('actualPVTooltip');if(!tip)return;
 var models=priceVolumeModels();
 var visible=actualPVHighlight?models.filter(function(m){return m.name===actualPVHighlight}):models;
 tip.innerHTML='<b>'+competitorWeekTrend.weeks[index]+' · 实际量价额</b>'+visible.map(function(m){return'<div style="border-top:1px solid rgba(255,255,255,.14);padding-top:5px;margin-top:5px"><div class="comp-tooltip-row"><i style="background:'+m.color+'"></i><span>'+m.name+'</span></div><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:5px;font-size:9px"><span>均价<br><strong>'+pvMetricValue(m.price[index],'price')+'</strong></span><span>销量<br><strong>'+pvMetricValue(m.units[index],'units')+'</strong></span><span>销额<br><strong>'+pvMetricValue(m.revenue[index],'revenue')+'</strong></span></div></div>'}).join('');
 tip.classList.add('show');moveActualPVTooltip(event);
}
function moveActualPVTooltip(event){
 var tip=document.getElementById('actualPVTooltip');if(!tip)return;
 var card=tip.parentElement,box=card.getBoundingClientRect();
 var x=event.clientX-box.left+12,y=event.clientY-box.top-tip.offsetHeight-12;
 if(x+tip.offsetWidth>box.width-8)x=event.clientX-box.left-tip.offsetWidth-12;if(y<6)y=event.clientY-box.top+14;
 tip.style.left=x+'px';tip.style.top=y+'px';
}
function hideActualPVTooltip(){var tip=document.getElementById('actualPVTooltip');if(tip)tip.classList.remove('show')}
renderPriceVolumeCombined();
renderActualPVCombined();
// CHAT_ENGINE_END
const demoParams=new URLSearchParams(location.search);
initHomeTrend();
initSmartReports();
if(demoParams.get('q'))askQ(demoParams.get('q'));
else if(demoParams.get('view')&&demoParams.get('view')!=='chat')goPage(demoParams.get('view'),document.querySelector('[data-page="'+demoParams.get('view')+'"]'));
else goPage('daily',document.querySelector('[data-page="daily"]'));


    // 竞品价格追踪：切换重点机型
    function switchRivalModel(el, model) {
      document.querySelectorAll('.monitor-subtab').forEach(t => t.classList.remove('active'));
      el.classList.add('active');
      document.querySelectorAll('.rival-model-panel').forEach(p => p.style.display = 'none');
      const panelId = 'rival-' + model.replace(/\s+/g, '-');
      const panel = document.getElementById(panelId);
      if (panel) panel.style.display = 'block';
    }

    // 竞品价格追踪：型号模糊搜索
    const rivalModelList = window.gtmRecords.rivalModelList;

    function filterRivalByCategory() {
      const category = document.getElementById('rival-category-filter').value;
      showToast('已按品类筛选：' + category);
    }

    // 品类→细分品类→型号 联动数据
    const rivalCategoryTree = window.gtmRecords.rivalCategoryTree;

    function onRivalCategoryChange(cat) {
      const subSel = document.getElementById('rival-subcategory-filter');
      subSel.innerHTML = '<option value="全部">全部</option>';
      if (cat !== '全部' && rivalCategoryTree[cat]) {
        rivalCategoryTree[cat].sub.forEach(s => {
          subSel.innerHTML += '<option value="'+s+'">'+s+'</option>';
        });
      }
      // 切换大类时刷新我品型号下拉
      refreshRivalModelSelect();
      showToast('已切换品类：' + cat);
    }
    function onRivalSubcategoryChange(sub) {
      refreshRivalModelSelect();
    }
    function refreshRivalModelSelect() {
      const data = singleSelectData.rivalOwnModelSelect;
      if (!data) return;
      data.allOptions = getRivalModelOptions();
      data.filtered = null;
      if (data.selected && data.allOptions.indexOf(data.selected) === -1) {
        data.selected = '';
        data.tempSelected = '';
      }
      renderSingleSelectTags('rivalOwnModelSelect');
      updateSingleSelectCount('rivalOwnModelSelect');
    }
    function getRivalModelOptions() {
      const cat = document.getElementById('rival-category-filter').value;
      const sub = document.getElementById('rival-subcategory-filter').value;
      if (cat === '全部') {
        // 全部品类下汇总所有型号
        const all = [];
        Object.values(rivalCategoryTree).forEach(v => {
          Object.values(v.models).forEach(arr => all.push(...arr));
        });
        return all;
      }
      if (!rivalCategoryTree[cat]) return [];
      if (sub === '全部') {
        const all = [];
        Object.values(rivalCategoryTree[cat].models).forEach(arr => all.push(...arr));
        return all;
      }
      return rivalCategoryTree[cat].models[sub] || [];
    }

    // 多选搜索框核心逻辑
    const multiSelectData = {
      rivalCompModelMultiSelect: {
        selected: [],
        tempSelected: [],
        maxSelect: 5,
        allOptions: ['TCL 65Q9L PRO','TCL 75Q9K','小米 S Pro 65','小米 S Pro 75','创维 65A7H PRO','创维 75A7H','华为 VISION 5 PRO 65','华为 VISION 5 PRO 75','康佳 65G7','长虹 65D7'],
        filtered: null
      }
    };
    function toggleMultiSelectDropdown(id,e){
      if(e) e.stopPropagation();
      const el = document.getElementById(id);
      const all = document.querySelectorAll('.multi-select.open');
      all.forEach(m => { if(m.id !== id) m.classList.remove('open'); });
      el.classList.toggle('open');
      if(el.classList.contains('open')){
        const input = el.querySelector('.ms-search input');
        if(input) input.value = '';
        const data = multiSelectData[id];
        if(data) { data.filtered = null; data.tempSelected = [...data.selected]; }
        renderMultiSelectOptions(id,'');
        updateMultiSelectCount(id);
      }
    }
    document.addEventListener('click',()=>{
      document.querySelectorAll('.multi-select.open').forEach(m=>m.classList.remove('open'));
    });
    function filterMultiSelectOptions(id,keyword){
      const data = multiSelectData[id];
      if(!data) return;
      data.filtered = keyword.trim()
        ? data.allOptions.filter(o=>o.toLowerCase().includes(keyword.toLowerCase()))
        : null;
      renderMultiSelectOptions(id,keyword);
    }
    function renderMultiSelectOptions(id,keyword){
      const data = multiSelectData[id];
      const optionsEl = document.getElementById(id + 'Options');
      if(!data || !optionsEl) return;
      const list = data.filtered !== null ? data.filtered : data.allOptions;
      if(list.length===0){
        optionsEl.innerHTML = '<div class="ms-empty">未找到匹配型号</div>';
        return;
      }
      optionsEl.innerHTML = list.map(opt=>{
        const sel = data.tempSelected.includes(opt);
        const disabled = !sel && data.maxSelect && data.tempSelected.length >= data.maxSelect;
        return '<div class="ms-option '+(sel?'selected':'')+(disabled?' disabled':'')+'" onclick="toggleMultiSelectOption(\''+id+'\',\''+opt+'\')">'
          + '<span class="ms-check"><svg viewBox="0 0 24 24" width="10" height="10"><path d="M5 12l5 5L20 7" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></span>'
          + '<span>'+opt+'</span></div>';
      }).join('');
    }
    function toggleMultiSelectOption(id,opt){
      const data = multiSelectData[id];
      if(!data) return;
      const idx = data.tempSelected.indexOf(opt);
      if(idx>-1) { data.tempSelected.splice(idx,1); }
      else {
        if(data.maxSelect && data.tempSelected.length >= data.maxSelect) { showToast('最多只能选择'+data.maxSelect+'个'); return; }
        data.tempSelected.push(opt);
      }
      renderMultiSelectOptions(id, document.querySelector('#'+id+' .ms-search input')?.value||'');
      updateMultiSelectCount(id);
    }
    function updateMultiSelectCount(id){
      const data = multiSelectData[id];
      if(!data) return;
      const countEl = document.getElementById(id+'Count');
      const tipEl = document.getElementById(id+'FooterTip');
      const total = data.allOptions.length;
      const sel = data.tempSelected.length;
      if(countEl) countEl.textContent = sel + '/' + total;
      if(tipEl){
        if(data.maxSelect && sel >= data.maxSelect){ tipEl.textContent = '已选满'+data.maxSelect+'个，可点击确定'; tipEl.style.color = 'var(--primary)'; }
        else { tipEl.textContent = '已选'+sel+'个，最多可选'+data.maxSelect+'个'; tipEl.style.color = '#909399'; }
      }
    }
    function confirmMultiSelect(id){
      const data = multiSelectData[id];
      if(!data) return;
      data.selected = [...data.tempSelected];
      renderMultiSelectTags(id);
      const el = document.getElementById(id);
      if(el) el.classList.remove('open');
    }
    function cancelMultiSelect(id){
      const data = multiSelectData[id];
      if(!data) return;
      data.tempSelected = [...data.selected];
      const el = document.getElementById(id);
      if(el) el.classList.remove('open');
    }
    function renderMultiSelectTags(id){
      const data = multiSelectData[id];
      const tagsEl = document.getElementById(id.replace('MultiSelect','')+'Tags') || document.getElementById(id+'Tags');
      if(!data || !tagsEl) return;
      if(data.selected.length===0){
        tagsEl.innerHTML = '<span class="ms-placeholder">请选择竞品型号</span>';
        return;
      }
      // 标签形式展示，可单个删除
      tagsEl.innerHTML = data.selected.map(opt=>{
        const safeOpt = opt.replace(/'/g, "\\'");
        return '<span class="ms-tag"><span class="ms-tag-text">'+opt+'</span><span class="ms-tag-close" onclick="event.stopPropagation();removeMultiSelectTag(\''+id+'\',\''+safeOpt+'\')">×</span></span>';
      }).join('');
    }
    function removeMultiSelectTag(id,opt){
      const data = multiSelectData[id];
      if(!data) return;
      const idx = data.selected.indexOf(opt);
      if(idx>-1){ data.selected.splice(idx,1); }
      const tidx = data.tempSelected.indexOf(opt);
      if(tidx>-1){ data.tempSelected.splice(tidx,1); }
      renderMultiSelectTags(id);
      // 如果下拉打开着，同步刷新选项
      const el = document.getElementById(id);
      if(el && el.classList.contains('open')){
        renderMultiSelectOptions(id, document.querySelector('#'+id+' .ms-search input')?.value||'');
        updateMultiSelectCount(id);
      }
    }
    function toggleRivalCustomDate(val){
      const show = val === 'custom';
      document.getElementById('rivalCustomDateStart').style.display=show?'flex':'none';
      document.getElementById('rivalCustomDateEnd').style.display=show?'flex':'none';
      renderRivalMonitorTable(val);
    }

    // 竞品价格监控明细数据
    const rivalMonitorData = [
      { ownModel: '65E7Q', ownPrice: '¥5,305', rivals: [
        { brand:'TCL', model:'65Q9L PRO', channel:'京东', curPrice:'¥5,522', origPrice:'¥6,299', highPrice:'¥6,299', lowPrice:'¥5,522', avgPrice:'¥5,720', change:'-12.3%', changeCls:'danger-price', changeTime:'2026-09-15 08:53', period:'近7天', spark:'down', sales:'986 台', revenue:'¥544.5 万', advice:'关注竞品降价，暂缓跟降', adviceCls:'red', level:'严重', shop:'京东自营旗舰店', promo:'页面价¥6,299 · 限时直降¥777 · 叠加平台券¥0' },
        { brand:'创维', model:'65A7H PRO', channel:'京东', curPrice:'¥4,939', origPrice:'¥5,299', highPrice:'¥5,050', lowPrice:'¥4,890', avgPrice:'¥4,939', change:'-6.8%', changeCls:'danger-price', changeTime:'2026-09-15 08:47', period:'近7天', spark:'flat', sales:'756 台', revenue:'¥373.4 万', advice:'观察价差与销量分流', adviceCls:'orange', level:'关注', shop:'创维京东自营旗舰店', promo:'页面价¥5,299 · 满减¥300 · 店铺券¥60' },
        { brand:'小米', model:'S Pro 65', channel:'拼多多', curPrice:'¥4,199', origPrice:'¥4,599', highPrice:'¥4,299', lowPrice:'¥4,199', avgPrice:'¥4,220', change:'-8.7%', changeCls:'danger-price', changeTime:'2026-09-15 09:02', period:'近7天', spark:'flat', sales:'1,523 台', revenue:'¥639.5 万', advice:'价格带不同，无需调整', adviceCls:'gray', level:'关注', shop:'小米电视官方旗舰店', promo:'页面价¥4,599 · 百亿补贴¥400' },
        { brand:'华为', model:'VISION 5 PRO', channel:'京东', curPrice:'¥4,704', origPrice:'¥5,199', highPrice:'¥4,999', lowPrice:'¥4,704', avgPrice:'¥4,820', change:'-9.5%', changeCls:'danger-price', changeTime:'2026-09-15 08:28', period:'近7天', spark:'down', sales:'623 台', revenue:'¥293.1 万', advice:'观察价差与销量分流', adviceCls:'orange', level:'关注', shop:'华为京东自营旗舰店', promo:'页面价¥5,199 · 满减¥300 · 以旧换新¥195' },
        { brand:'康佳', model:'65D6S', channel:'天猫', curPrice:'¥5,637', origPrice:'¥5,637', highPrice:'¥5,637', lowPrice:'¥5,637', avgPrice:'¥5,637', change:'+0%', changeCls:'', changeTime:'2026-09-15 08:15', period:'近7天', spark:'flat', sales:'412 台', revenue:'¥232.2 万', advice:'我品价格占优，维持策略', adviceCls:'green', level:'正常', shop:'康佳官方旗舰店', promo:'页面价¥5,637 · 无促销活动' }
      ]},
      { ownModel: '75E8N Pro', ownPrice: '¥7,050', rivals: [
        { brand:'TCL', model:'75Q9L PRO', channel:'京东', curPrice:'¥7,299', origPrice:'¥7,999', highPrice:'¥7,899', lowPrice:'¥7,299', avgPrice:'¥7,580', change:'-8.8%', changeCls:'danger-price', changeTime:'2026-09-15 08:33', period:'近7天', spark:'down', sales:'523 台', revenue:'¥381.7 万', advice:'关注竞品降价，暂缓跟降', adviceCls:'red', level:'严重', shop:'TCL京东自营旗舰店', promo:'页面价¥7,999 · 限时直降¥700' },
        { brand:'创维', model:'75A7H PRO', channel:'天猫', curPrice:'¥6,899', origPrice:'¥7,299', highPrice:'¥7,050', lowPrice:'¥6,899', avgPrice:'¥6,980', change:'-5.5%', changeCls:'danger-price', changeTime:'2026-09-15 08:41', period:'近7天', spark:'flat', sales:'386 台', revenue:'¥266.3 万', advice:'观察价差与销量分流', adviceCls:'orange', level:'关注', shop:'创维官方旗舰店', promo:'页面价¥7,299 · 满减¥400' },
        { brand:'小米', model:'S Pro 75', channel:'拼多多', curPrice:'¥5,999', origPrice:'¥6,499', highPrice:'¥6,199', lowPrice:'¥5,999', avgPrice:'¥6,080', change:'-7.7%', changeCls:'danger-price', changeTime:'2026-09-15 08:55', period:'近7天', spark:'up', sales:'892 台', revenue:'¥535.1 万', advice:'价格带不同，无需调整', adviceCls:'gray', level:'关注', shop:'小米电视官方旗舰店', promo:'页面价¥6,499 · 百亿补贴¥500' },
        { brand:'华为', model:'VISION 5 PRO 75', channel:'京东', curPrice:'¥6,599', origPrice:'¥7,299', highPrice:'¥6,999', lowPrice:'¥6,599', avgPrice:'¥6,780', change:'-9.6%', changeCls:'danger-price', changeTime:'2026-09-15 08:22', period:'近7天', spark:'down', sales:'312 台', revenue:'¥205.9 万', advice:'观察价差与销量分流', adviceCls:'orange', level:'关注', shop:'华为京东自营旗舰店', promo:'页面价¥7,299 · 满减¥500 · 以旧换新¥200' }
      ]},
      { ownModel: '55E5N', ownPrice: '¥2,650', rivals: [
        { brand:'TCL', model:'55Q9L', channel:'天猫', curPrice:'¥2,799', origPrice:'¥2,999', highPrice:'¥2,899', lowPrice:'¥2,799', avgPrice:'¥2,850', change:'-6.7%', changeCls:'danger-price', changeTime:'2026-09-15 08:38', period:'近7天', spark:'flat', sales:'1,256 台', revenue:'¥351.5 万', advice:'我品价格占优，维持策略', adviceCls:'green', level:'正常', shop:'TCL官方旗舰店', promo:'页面价¥2,999 · 满减¥200' },
        { brand:'创维', model:'55A7H', channel:'拼多多', curPrice:'¥2,599', origPrice:'¥2,799', highPrice:'¥2,699', lowPrice:'¥2,599', avgPrice:'¥2,640', change:'-7.1%', changeCls:'danger-price', changeTime:'2026-09-15 08:45', period:'近7天', spark:'down', sales:'986 台', revenue:'¥256.3 万', advice:'观察价差与销量分流', adviceCls:'orange', level:'关注', shop:'创维官方旗舰店', promo:'页面价¥2,799 · 百亿补贴¥200' },
        { brand:'小米', model:'EA55 2026', channel:'京东', curPrice:'¥2,199', origPrice:'¥2,399', highPrice:'¥2,249', lowPrice:'¥2,199', avgPrice:'¥2,220', change:'-8.3%', changeCls:'danger-price', changeTime:'2026-09-15 09:01', period:'近7天', spark:'flat', sales:'2,156 台', revenue:'¥474.1 万', advice:'价格带不同，无需调整', adviceCls:'gray', level:'关注', shop:'小米京东自营旗舰店', promo:'页面价¥2,399 · 满减¥200' },
        { brand:'华为', model:'SE55 MEMC', channel:'京东', curPrice:'¥2,499', origPrice:'¥2,799', highPrice:'¥2,649', lowPrice:'¥2,499', avgPrice:'¥2,580', change:'-10.7%', changeCls:'danger-price', changeTime:'2026-09-15 08:31', period:'近7天', spark:'down', sales:'756 台', revenue:'¥188.9 万', advice:'观察价差与销量分流', adviceCls:'orange', level:'关注', shop:'华为京东自营旗舰店', promo:'页面价¥2,799 · 满减¥200 · 优惠券¥100' }
      ]}
    ];

    function sparkSvg(type){
      const paths = {
        down: 'M2 5 L20 7 L38 6 L56 13 L74 12 L92 20 L114 23',
        flat: 'M2 14 L20 13 L38 14 L56 12 L74 11 L92 10 L114 9',
        up:   'M2 18 L20 17 L38 16 L56 15 L74 13 L92 11 L114 9'
      };
      const cls = type==='down'?'spark-down':(type==='up'?'spark-up':'spark-flat');
      return '<div class="price-spark"><svg viewBox="0 0 116 28" preserveAspectRatio="none"><path class="spark-grid" d="M1 23H115"/><path class="'+cls+'" d="'+(paths[type]||paths.flat)+'"/></svg></div>';
    }

    function renderRivalMonitorTable(period){
      const wrap = document.getElementById('rivalMonitorTableWrap');
      if(!wrap) return;
      const isShort = period === 'today' || period === 'yesterday';
      let thead, tbody = '', total = 0;

      if(isShort){
        // 今日/昨日：8列
        thead = '<thead><tr><th>品牌</th><th>型号</th><th>渠道</th><th>当前到手价</th><th>原价</th><th>波动幅度</th><th>调价时间</th><th>操作</th></tr></thead>';
        rivalMonitorData.forEach(group=>{
          group.rivals.forEach((r,i)=>{
            total++;
            tbody += '<tr>'
              + '<td>'+r.brand+'</td>'
              + '<td><b>'+r.model+'</b></td>'
              + '<td>'+r.channel+'</td>'
              + '<td><b>'+r.curPrice+'</b></td>'
              + '<td><span style="color:var(--muted);font-size:11px">'+r.origPrice+'</span></td>'
              + '<td class="'+r.changeCls+'">'+r.change+'</td>'
              + '<td style="font-size:11px;color:var(--muted)">'+r.changeTime+'</td>'
              + '<td><div style="display:flex;gap:6px"><button class="btn sm" onclick="openRivalEvidence(\''+r.level+'\',\''+r.brand+' '+r.model+'\',\''+r.shop+'\',\''+r.curPrice+'\',\''+r.origPrice+'\',\''+r.change+'\',\''+r.promo+'\',\''+r.channel+' · '+r.changeTime+'\',\''+r.avgPrice+'\')">查看详情</button><button class="btn sm" style="border:1px solid var(--line);color:var(--text)" onclick="openRivalPriceDetailMonitor(\''+r.brand+'\',\''+r.model+'\',\''+r.channel+'\',\''+period+'\')">价格明细</button></div></td>'
              + '</tr>';
          });
        });
        wrap.innerHTML = '<table class="monitor-table rival-monitor-table" style="min-width:980px">'+thead+'<tbody>'+tbody+'</tbody></table>';
      } else {
        // 近7天/近30天：11列，调价时间列改为时间周期，操作列增加价格明细按钮
        const pDays = period==='month'?30:7;
        const end = new Date('2026-09-15');
        const start = new Date(end.getTime() - (pDays-1)*86400000);
        const fmt = d => (d.getFullYear()+'/'+String(d.getMonth()+1).padStart(2,'0')+'/'+String(d.getDate()).padStart(2,'0'));
        const periodText = fmt(start)+'-'+fmt(end);
        thead = '<thead><tr><th>品牌</th><th>型号</th><th>渠道</th><th>当前到手价</th><th>原价</th><th>最高价</th><th>最低价</th><th>均价</th><th>波动幅度</th><th>时间周期</th><th>操作</th></tr></thead>';
        rivalMonitorData.forEach(group=>{
          group.rivals.forEach((r,i)=>{
            total++;
            const ridx = group.ownModel + '|' + r.model + '|' + r.channel;
            tbody += '<tr>'
              + '<td>'+r.brand+'</td>'
              + '<td><b>'+r.model+'</b></td>'
              + '<td>'+r.channel+'</td>'
              + '<td><b>'+r.curPrice+'</b></td>'
              + '<td><span style="color:var(--muted);font-size:11px">'+r.origPrice+'</span></td>'
              + '<td>'+r.highPrice+'</td>'
              + '<td>'+r.lowPrice+'</td>'
              + '<td><b>'+r.avgPrice+'</b></td>'
              + '<td class="'+r.changeCls+'">'+r.change+'</td>'
              + '<td style="font-size:11px;color:var(--muted)">'+periodText+'</td>'
              + '<td><div style="display:flex;gap:6px"><button class="btn sm" onclick="openRivalEvidence(\''+r.level+'\',\''+r.brand+' '+r.model+'\',\''+r.shop+'\',\''+r.curPrice+'\',\''+r.origPrice+'\',\''+r.change+'\',\''+r.promo+'\',\''+r.channel+' · '+r.changeTime+'\',\''+r.avgPrice+'\')">查看详情</button><button class="btn sm" style="border:1px solid var(--line);color:var(--text)" onclick="openRivalPriceDetailMonitor(\''+r.brand+'\',\''+r.model+'\',\''+r.channel+'\',\''+period+'\')">价格明细</button></div></td>'
              + '</tr>';
          });
        });
        wrap.innerHTML = '<table class="monitor-table rival-monitor-table" style="min-width:1400px">'+thead+'<tbody>'+tbody+'</tbody></table>';
      }
      // 同步分页条数
      const pageTotal=document.querySelector('#page-rival-monitor .ep-total');
      if(pageTotal){pageTotal.textContent='共 '+total+' 条';}
      // 同步数据来源周期文案
      const ds=document.querySelector('#page-rival-monitor .data-source-footer span b');
      // 更新周期提示
      const footer=document.querySelector('#page-rival-monitor .data-source-footer span');
      if(footer){
        const pText = period==='today'?'今日':(period==='yesterday'?'昨日':(period==='month'?'近30天':'近7天'));
        footer.innerHTML = '<b>数据来源：</b>京东/淘天/抖音等电商平台竞品价格抓取数据　·　每2小时自动追踪更新　·　统计周期：'+pText;
      }
    }
    // 暴露竞品价格监控数据到全局，供价格明细弹窗使用
    window._rivalMonitorData = rivalMonitorData;
    function openRivalPriceDetail(brand, model, channel, period){
      let days, isIntraday = false;
      if(period==='month'){ days = 30; }
      else if(period==='today' || period==='yesterday'){ days = 8; isIntraday = true; }
      else { days = 7; }
      const end = new Date('2026-09-15');
      const baseDate = period==='yesterday' ? new Date(end.getTime()-86400000) : end;
      const start = isIntraday ? baseDate : new Date(end.getTime() - (days-1)*86400000);
      const fmt = d => (d.getFullYear()+'/'+String(d.getMonth()+1).padStart(2,'0')+'/'+String(d.getDate()).padStart(2,'0'));
      // 基于型号+渠道+品牌生成稳定的日价格序列
      const seed = (brand+model+channel).split('').reduce((a,c)=>a+c.charCodeAt(0),0);
      const baseCur = parseInt((rivalMonitorData[0].rivals[0].curPrice).replace(/[^0-9]/g,''));
      // 找到对应竞品的基准价
      let basePrice = 4999, origP = 5499;
      for(const g of rivalMonitorData){
        for(const r of g.rivals){
          if(r.brand===brand && r.model===model && r.channel===channel){
            basePrice = parseInt(r.curPrice.replace(/[^0-9]/g,''));
            origP = parseInt(r.origPrice.replace(/[^0-9]/g,''));
          }
        }
      }
      let rows = [];
      let prevPrice = basePrice + Math.round((seed%300)-150);
      const stepMs = isIntraday ? 3*3600*1000 : 86400000;
      for(let i=0;i<days;i++){
        const d = new Date(start.getTime() + i*stepMs);
        const offset = Math.round(Math.sin((seed+i)*0.7)*80) + ((seed+i)%40-20);
        const curP = Math.max(basePrice-200, Math.min(basePrice+200, prevPrice + offset));
        prevPrice = curP;
        const change = i===0 ? '+0.0%' : (curP - (rows[i-1]?rows[i-1]._num:basePrice)) / (rows[i-1]?rows[i-1]._num:basePrice) * 100;
        const changeStr = (change>0?'+':'') + change.toFixed(1) + '%';
        const changeCls = change>0.5 ? 'danger-price' : (change<-0.5 ? 'success-price' : '');
        const timeStr = fmt(d) + ' ' + String(isIntraday ? (i*3+8)%24 : 8+(seed+i)%10).padStart(2,'0') + ':' + String((seed*3+i*7)%60).padStart(2,'0');
        rows.push({
          date: fmt(d),
          curPrice: '¥'+curP.toLocaleString(),
          origPrice: '¥'+origP.toLocaleString(),
          change: changeStr,
          changeCls: changeCls,
          time: timeStr,
          _num: curP
        });
      }
      const thead = '<thead><tr><th>品牌</th><th>型号</th><th>渠道</th><th>到手价</th><th>原价</th><th>波动幅度</th><th>调价时间</th></tr></thead>';
      let tbody = '';
      rows.forEach(r=>{
        tbody += '<tr>'
          + '<td>'+brand+'</td>'
          + '<td><b>'+model+'</b></td>'
          + '<td>'+channel+'</td>'
          + '<td><b>'+r.curPrice+'</b></td>'
          + '<td><span style="color:var(--muted);font-size:12px">'+r.origPrice+'</span></td>'
          + '<td class="'+r.changeCls+'">'+r.change+'</td>'
          + '<td style="font-size:12px;color:var(--muted)">'+r.time+'</td>'
          + '</tr>';
      });
      const periodLabel = period==='today' ? '今日价格明细' : (period==='yesterday' ? '昨日价格明细' : (period==='month' ? '近30天价格明细' : (period==='custom' ? '自定义周期价格明细' : '近7天价格明细')));
      document.getElementById('rivalDetailTitle').textContent = brand+' '+model+' · '+periodLabel;
      const wrap = document.getElementById('rivalPriceDetailTableWrap');
      wrap.innerHTML = '<table class="monitor-table rival-monitor-table" style="min-width:760px">'+thead+'<tbody>'+tbody+'</tbody></table>';
      openModal('rivalPriceDetailModal');
    }

    function removeMultiSelectTag(e,id,opt){
      e.stopPropagation();
      toggleMultiSelectOption(id,opt);
    }

    // 单选搜索下拉框逻辑（我品型号）
    const singleSelectData = {
      rivalOwnModelSelect: {
        selected: '',
        tempSelected: '',
        allOptions: ['65E7Q','75E8N Pro','55E5N','85E8K','65E5N Pro','75E7K','55E7H','100E8K','65E8K','75E5N Pro'],
        filtered: null
      }
    };
    function toggleSingleSelectDropdown(id,e){
      if(e) e.stopPropagation();
      const el = document.getElementById(id);
      const all = document.querySelectorAll('.multi-select.open');
      all.forEach(m => { if(m.id !== id) m.classList.remove('open'); });
      el.classList.toggle('open');
      if(el.classList.contains('open')){
        const input = el.querySelector('.ms-search input');
        if(input) { input.value = ''; }
        const data = singleSelectData[id];
        if(data) { data.filtered = null; data.tempSelected = data.selected; }
        renderSingleSelectOptions(id,'');
        updateSingleSelectCount(id);
      }
    }
    function filterSingleSelectOptions(id,keyword){
      const data = singleSelectData[id];
      if(!data) return;
      data.filtered = keyword.trim()
        ? data.allOptions.filter(o=>o.toLowerCase().includes(keyword.toLowerCase()))
        : null;
      renderSingleSelectOptions(id,keyword);
    }
    function renderSingleSelectOptions(id,keyword){
      const data = singleSelectData[id];
      const optionsEl = document.getElementById(id + 'Options');
      if(!data || !optionsEl) return;
      const list = data.filtered !== null ? data.filtered : data.allOptions;
      if(list.length===0){
        optionsEl.innerHTML = '<div class="ms-empty">未找到匹配型号</div>';
        return;
      }
      optionsEl.innerHTML = list.map(opt=>{
        const sel = data.tempSelected === opt;
        return '<div class="ms-option single-opt '+(sel?'selected':'')+'" onclick="selectSingleOption(\''+id+'\',\''+opt+'\')">'
          + '<span class="ss-radio"><span class="ss-radio-dot"></span></span>'
          + '<span>'+opt+'</span></div>';
      }).join('');
    }
    function selectSingleOption(id,opt){
      const data = singleSelectData[id];
      if(!data) return;
      data.tempSelected = opt;
      renderSingleSelectOptions(id, document.querySelector('#'+id+' .ms-search input')?.value||'');
      updateSingleSelectCount(id);
    }
    function updateSingleSelectCount(id){
      const data = singleSelectData[id];
      if(!data) return;
      const countEl = document.getElementById(id+'Count');
      const tipEl = document.getElementById(id+'FooterTip');
      const total = data.allOptions.length;
      const sel = data.tempSelected ? 1 : 0;
      if(countEl) countEl.textContent = sel + '/' + total;
      if(tipEl) tipEl.textContent = '已选' + sel + '个';
    }
    function confirmSingleSelect(id){
      const data = singleSelectData[id];
      if(!data) return;
      data.selected = data.tempSelected;
      renderSingleSelectTags(id);
      const el = document.getElementById(id);
      if(el) el.classList.remove('open');
    }
    function cancelSingleSelect(id){
      const data = singleSelectData[id];
      if(!data) return;
      data.tempSelected = data.selected;
      const el = document.getElementById(id);
      if(el) el.classList.remove('open');
    }
    function renderSingleSelectTags(id){
      const data = singleSelectData[id];
      const tagsEl = document.getElementById(id.replace('Select','')+'Tags') || document.getElementById(id+'Tags');
      if(!data || !tagsEl) return;
      if(!data.selected){
        tagsEl.innerHTML = '<span class="ms-placeholder">请选择我品型号</span>';
        return;
      }
      tagsEl.innerHTML = '<span class="ms-inline-text">'+data.selected+'</span>';
    }

    // 竞品上新提醒页 - 品类联动
    const launchCategoryMap = {
      '电视': ['平板电视'],
      '空调': ['家用空调'],
      '冰箱': ['冰箱','冷柜','冰吧'],
      '洗衣机': ['洗衣机'],
      '厨卫': ['油烟机','燃气灶','消毒柜','电热水器','燃气热水器','洗碗机','嵌入式微蒸烤']
    };
    function onLaunchCategoryChange(cat){
      const subSel = document.getElementById('launch-subcategory-filter');
      subSel.innerHTML = '<option value="全部">全部</option>';
      if (cat !== '全部' && launchCategoryMap[cat]) {
        launchCategoryMap[cat].forEach(s => {
          subSel.innerHTML += '<option value="'+s+'">'+s+'</option>';
        });
      }
      updateLaunchTableTotal();
    }
    function onLaunchDateFilterChange(val){
      currentLaunchPeriod=val;
      document.getElementById('launchDateRange').style.display = val === 'custom' ? '' : 'none';
      if(currentLaunchProduct&&document.getElementById('launchEncyclopediaModal').classList.contains('show'))renderLaunchEncyclopedia();
      updateLaunchTableTotal();
    }
    function updateLaunchTableTotal(){
      const table=document.querySelector('#page-launch .launch-table tbody');
      if(!table)return;
      const rows=table.querySelectorAll('tr');
      let count=0;
      rows.forEach(tr=>{if(tr.style.display!=='none')count++;});
      const el=document.getElementById('launchTableTotal');
      if(el){el.textContent='共 '+count+' 条';}
      // 同步底部分页条数
      const pageTotal=document.querySelector('#page-launch .ep-total');
      if(pageTotal){pageTotal.textContent='共 '+count+' 条';}
    }

    // AI总结：根据筛选条件重新生成
    function regenAISummary(type) {
      const btn = event.target;
      btn.classList.add('loading');
      btn.textContent = '生成';

      let summaryEl;
      if (type === 'own') {
        summaryEl = document.querySelector('#page-own-monitor .monitor-ai-summary');
      } else if (type === 'rival') {
        summaryEl = document.querySelector('#page-rival-monitor .monitor-ai-summary');
      } else if (type === 'launch') {
        summaryEl = document.querySelector('#page-launch .monitor-ai-summary');
      } else if (type === 'competitor') {
        summaryEl = document.querySelector('#page-competitor .monitor-ai-summary');
      } else if (type === 'pv') {
        summaryEl = document.querySelector('#panel-pricevolume .monitor-ai-summary');
      } else if (type === 'premium') {
        summaryEl = document.querySelector('#panel-premium .monitor-ai-summary');
      } else if (type === 'daily') {
        summaryEl = document.querySelector('#page-daily .daily-ai-overview');
      }
      if (summaryEl) summaryEl.classList.add('loading');

      // 模拟AI生成过程
      setTimeout(() => {
        btn.classList.remove('loading');
        btn.textContent = '重新生成';
        if (summaryEl) summaryEl.classList.remove('loading');

        // 更新时间
        const now = new Date();
        const timeStr = now.getFullYear() + '-' + String(now.getMonth()+1).padStart(2,'0') + '-' + String(now.getDate()).padStart(2,'0') + ' ' + String(now.getHours()).padStart(2,'0') + ':' + String(now.getMinutes()).padStart(2,'0');
        const timeEl = summaryEl.querySelector('.ai-time');
        if (timeEl) {
          timeEl.innerHTML = '<i></i>基于当前筛选条件生成 · ' + timeStr;
        }
        showToast('AI总结已根据当前筛选条件重新生成');
      }, 1200);
    }

    /* TOP3 重点产品型号弹窗 */
    const kpModelPool = {
      '电视': [
        {name:'海信 65E7Q', tag:'主力走量 · 65寸'},
        {name:'海信 75E8N Pro', tag:'高端大屏 · 75寸'},
        {name:'海信 55E5N', tag:'入门爆款 · 55寸'},
        {name:'海信 85E8K', tag:'旗舰巨幕 · 85寸'},
        {name:'海信 65E5N Pro', tag:'中端走量 · 65寸'},
        {name:'海信 100E8K', tag:'激光巨幕 · 100寸'},
        {name:'海信 55E7N', tag:'中高端 · 55寸'},
        {name:'海信 75E7N', tag:'中高端 · 75寸'},
        {name:'海信 65WS8Q', tag:'游戏旗舰 · 65寸'},
        {name:'海信 55A52N', tag:'入门走量 · 55寸'}
      ],
      '冰箱': [
        {name:'海信 BCD-516WTDGVBP', tag:'十字对开门 · 516L'},
        {name:'海信 BCD-606WTDGVBP', tag:'对开门 · 606L'},
        {name:'海信 BCD-452WMK1DP', tag:'法式多门 · 452L'}
      ],
      '空调': [
        {name:'海信 KFR-35GW/A8X700Z-A1', tag:'1.5匹挂机 · 新一级'},
        {name:'海信 KFR-72LW/A8X700Z-A1', tag:'3匹柜机 · 新一级'}
      ],
      '洗衣机': [
        {name:'海信 HG100DG12F', tag:'10kg滚筒 · 洗烘一体'},
        {name:'海信 HG100DSE12F', tag:'10kg滚筒 · 直驱变频'}
      ],
      '厨卫': [
        {name:'海信 CXW-230-HQ708', tag:'侧吸油烟机 · 22m³'},
        {name:'海信 JZT-HB301', tag:'嵌入式燃气灶 · 5.0kW'}
      ]
    };
    let kpSelected = [];

    function openDailyTop3Modal(){
      kpSelected = dailyModels.slice(0,3).map(m=>({name:m.name, tag:m.tag}));
      renderKpSelected();
      document.getElementById('kpSearchInput').value='';
      hideKpSearchResults();
      openModal('keyProductModal');
    }
    function closeKeyProductModal(){closeModal('keyProductModal')}

    function onKpCategoryChange(){
      document.getElementById('kpSearchInput').value='';
      hideKpSearchResults();
    }

    function onKpSearchInput(){
      const kw = document.getElementById('kpSearchInput').value.trim();
      const cat = document.getElementById('kpCategory').value;
      const list = kpModelPool[cat] || [];
      const results = kw ? list.filter(m=>m.name.toLowerCase().includes(kw.toLowerCase())) : list;
      const box = document.getElementById('kpSearchResults');
      if(!results.length || !kw){box.innerHTML='';box.classList.remove('show');return;}
      box.innerHTML = results.map(m=>{
        const selected = kpSelected.some(s=>s.name===m.name);
        return `<div class="kp-search-item" onmousedown="selectKpModel('${m.name}','${m.tag}')">
          <div class="kp-si-name">${m.name}${selected?' <span style="color:var(--muted);font-weight:400;font-size:11px">（已选）</span>':''}</div>
          <div class="kp-si-tag">${m.tag}</div>
        </div>`;
      }).join('');
      box.classList.add('show');
    }
    function onKpSearchFocus(){onKpSearchInput()}
    function hideKpSearchResults(){document.getElementById('kpSearchResults').classList.remove('show')}

    function selectKpModel(name, tag){
      if(kpSelected.length>=3){showToast('最多只能添加3个重点产品型号');return;}
      if(kpSelected.some(s=>s.name===name)){return;}
      kpSelected.push({name, tag});
      renderKpSelected();
      document.getElementById('kpSearchInput').value='';
      hideKpSearchResults();
    }

    function removeKpModel(index){
      kpSelected.splice(index, 1);
      renderKpSelected();
    }

    function renderKpSelected(){
      const box = document.getElementById('kpSelectedList');
      if(!kpSelected.length){
        box.innerHTML = '<div class="kp-empty">暂未添加重点产品型号，请在上方搜索并添加</div>';
        return;
      }
      box.innerHTML = kpSelected.map((m,i)=>`
        <div class="kp-selected-item">
          <div class="kp-si-main">
            <div class="kp-si-name">${m.name}</div>
            <div class="kp-si-tag">${m.tag}</div>
          </div>
          <button class="kp-remove-btn" onclick="removeKpModel(${i})">删除</button>
        </div>
      `).join('');
    }

    function confirmKeyProduct(){
      if(kpSelected.length < 3){
        showToast('请维护3个重点产品型号');
        return;
      }
      // 用已选型号替换 dailyModels 前3个并刷新模块
      const newModels = kpSelected.map((m,i)=>{
        const exist = dailyModels.find(d=>d.name===m.name);
        if(exist) return exist;
        // 模拟数据，复用第一个数据模板
        const base = dailyModels[0];
        return {
          name: m.name,
          tag: m.tag,
          units: JSON.parse(JSON.stringify(base.units)),
          revenue: JSON.parse(JSON.stringify(base.revenue)),
          price: JSON.parse(JSON.stringify(base.price)),
          trend: JSON.parse(JSON.stringify(base.trend))
        };
      });
      dailyModels.splice(0, newModels.length, ...newModels);
      dailyCurrentModel = 0;
      switchDailyModel(0, null);
      // 刷新卡片列表
      const cardsBox = document.getElementById('dailyModelCards');
      if(cardsBox){
        cardsBox.innerHTML = newModels.map((m,i)=>`
          <div class="daily-model-card ${i===0?'active':''}" onclick="switchDailyModel(${i},this)">
            <div class="dm-name">${m.name}</div>
            <div class="dm-tag">${m.tag}</div>
          </div>
        `).join('');
      }
      closeKeyProductModal();
      showToast('重点产品型号已更新');
    }
function escapeSampleText(value) {
  const node = document.createElement("span");
  node.textContent = String(value ?? "");
  return node.innerHTML;
}
