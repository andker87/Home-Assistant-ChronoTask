const CTW_VERSION = 'chronotask-weekly-card v0.1';
try {
  console.info(
    `%c chronotask-weekly-card %c ${CTW_VERSION} `,
    'background:#0b806a;color:#fff;border-radius:4px 0 0 4px;padding:2px 6px;font-weight:600',
    'background:#e7fff9;color:#0b806a;border-radius:0 4px 4px 0;padding:2px 6px'
  );
} catch (_){}
const _cssEscape=(s)=>{ try{ return (window.CSS&&CSS.escape)?CSS.escape(String(s)):String(s).replace(/[^a-zA-Z0-9_\-]/g,ch=>'\\'+ch);}catch(_){return String(s);} };
function _normalizeHex(hex,fallback='#5a8e62'){ if(!hex) return fallback; let h=String(hex).trim(); if(!h.startsWith('#')) h='#'+h; if(/^#([0-9a-fA-F]{6})$/.test(h)) return h.toLowerCase(); if(/^#([0-9a-fA-F]{3})$/.test(h)){ const r=h[1],g=h[2],b=h[3]; return (`#${r}${r}${g}${g}${b}${b}`).toLowerCase(); } return fallback||null; }
function _toHexFromAny(input,fallback='#5a8e62'){ if(!input) return _normalizeHex(fallback,fallback); const s=String(input).trim(); const direct=_normalizeHex(s,null); if(direct) return direct; try{ const ctx=(_toHexFromAny._ctx)||(()=>{ const c=document.createElement('canvas'); c.width=c.height=1; _toHexFromAny._ctx=c.getContext('2d'); return _toHexFromAny._ctx; })(); ctx.clearRect(0,0,1,1); ctx.fillStyle='#000'; ctx.fillStyle=s; const computed=ctx.fillStyle; if(/^#([0-9a-f]{6})$/i.test(computed)) return computed.toLowerCase(); const m=computed.match(/^rgba?\((\d+),(\d+),(\d+)/i); if(m){ const r=Math.max(0,Math.min(255,parseInt(m[1],10))); const g=Math.max(0,Math.min(255,parseInt(m[2],10))); const b=Math.max(0,Math.min(255,parseInt(m[3],10))); return '#'+[r,g,b].map(v=>v.toString(16).padStart(2,'0')).join(''); } }catch(_){ } return _normalizeHex(fallback,'#5a8e62'); }
function _hexToRgb(hex){ const h=_normalizeHex(hex); const m=/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(h); return m?{r:parseInt(m[1],16),g:parseInt(m[2],16),b:parseInt(m[3],16)}:{r:90,g:142,b:98}; }
function _relativeLuminance({r,g,b}){ const s=[r,g,b].map(v=>v/255).map(v=> v<=0.03928? v/12.92:Math.pow((v+0.055)/1.055,2.4)); return 0.2126*s[0]+0.7152*s[1]+0.0722*s[2]; }
function _idealTextColor(hex){ return _relativeLuminance(_hexToRgb(hex))>0.5?'#000':'#fff'; }
function _darkenHex(hex,amount=15){ const {r,g,b}=_hexToRgb(hex); const clamp=x=>Math.max(0,Math.min(255,x)); const rr=clamp(r-amount),gg=clamp(g-amount),bb=clamp(b-amount); const toH=v=>v.toString(16).padStart(2,'0'); return `#${toH(rr)}${toH(gg)}${toH(bb)}`; }

function _tagsToArray(raw){
  if(!raw) return [];
  if(Array.isArray(raw)) return raw.map(x=>String(x||'').trim().toLowerCase()).filter(Boolean);
  const s=String(raw).trim();
  if(!s) return [];
  return s.split(',').map(t=>t.trim().toLowerCase()).filter(Boolean);
}
function _tagsToText(arr){
  const a=_tagsToArray(arr);
  return a.join(', ');
}

class ChronoTaskWeeklyCard extends HTMLElement{
  static getConfigElement(){ return document.createElement('chronotask-weekly-card-editor'); }
  static getStubConfig(hass){ let rules_entity; try{ if(hass?.states){ rules_entity=Object.keys(hass.states).find(eid=> eid.startsWith('sensor.') && hass.states[eid]?.attributes?.planner_id); } }catch(_){} return { title:'Programmazione settimanale (ricorrente)', start_hour:'06:00', end_hour:'22:00', slot_minutes:60, ...(rules_entity?{rules_entity}:{}) }; }

  constructor(){
    super();
    this._pendingEdits=new Map();
    this._pendingTTL=4000;
    this._pendingUpdateTTL=60000;
    this._activeDialog=null;
    this._updateScheduled=false;
    this._onWinResize=()=>{ this._rebuildOverlayColumns(); };
  }

  setConfig(config){
    const cfg={...(config||{})};
    if(cfg.entity && !cfg.rules_entity) cfg.rules_entity=cfg.entity;
    this._config=Object.assign(
      { rules_entity:undefined, planner_id:undefined, planner_name:undefined, start_hour:'06:00', end_hour:'22:00', slot_minutes:60, locale:'it', title:'Programmazione settimanale (ricorrente)', default_color:'#5a8e62', entity_include_domains:undefined, entity_exclude_domains:undefined },
      cfg
    );
    this._config.default_color=_toHexFromAny(this._config.default_color||'#5a8e62','#5a8e62');

    if(!this.shadowRoot) this.attachShadow({mode:'open'});
    this._ensureLayout();
    this._els.title.textContent=this._config.title||'Programmazione settimanale (ricorrente)';
    this._scheduleUpdate();
  }

  getCardSize(){ return 8; }

  set hass(hass){
    this._hass=hass;
    this._rulesEntityId=this._resolveRulesEntity(hass)||this._rulesEntityId||this._config.rules_entity;
    this._scheduleUpdate();
  }

  connectedCallback(){ try{ window.addEventListener('resize', this._onWinResize);}catch(_){ } }
  disconnectedCallback(){ try{ window.removeEventListener('resize', this._onWinResize);}catch(_){ } try{ if(this._ro) this._ro.disconnect(); }catch(_){ } }

  _scheduleUpdate(){ if(this._updateScheduled) return; this._updateScheduled=true; requestAnimationFrame(()=>{ this._updateScheduled=false; this._update(); }); }

_ensureLayout(){
  if(this._layoutReady) return;
  const root=this.shadowRoot;
  root.innerHTML=`
  <style>
    :host{ display:block }

    /* ✅ container per container-queries */
    .wrap{
      padding:8px;
      container-type: inline-size;
    }

    /* Header a 3 colonne */
    .hdr{
      display:grid;
      grid-template-columns: 1fr auto 1fr;
      align-items:center;
      gap:8px;
      margin-bottom:8px;
    }
    .hdr-left{ justify-self:start; min-width:0; }
    .hdr-center{ justify-self:center; }
    .hdr-right{ justify-self:end; display:flex; gap:8px; align-items:center; }

    /* Chip buttons */
    .chip-btn{
      display:inline-flex;
      align-items:center;
      gap:6px;
      padding:2px 10px;
      border:2px solid var(--divider-color);
      border-radius:999px;
      font-size:12px;
      font-weight:600;
      opacity:.95;
      user-select:none;
      cursor:pointer;
      background:transparent;
      line-height:20px;
    }
    .chip-btn:hover{ filter:brightness(1.03); }
    .chip-btn:active{ transform:translateY(1px); }
    .chip-enable{ border-color:#0b806a; color:#0b806a; }
    .chip-disable{ border-color:#ed1c24; color:#ed1c24; } /* tuo rosso */

    .title{font-weight:600}
    .btn{background:var(--primary-color);color:#fff;border:none;border-radius:6px;padding:6px 10px;cursor:pointer}

    /* Stage / scroll */
    .stage{
      position: relative;
      overflow-x: auto;
      overflow-y: visible;
      -webkit-overflow-scrolling: touch;
    }
    .stage::-webkit-scrollbar{ height: 8px; }
    .stage::-webkit-scrollbar-thumb{
      background: rgba(0,0,0,.25);
      border-radius: 10px;
    }

    /* ✅ GRID: colonna orari ridimensionata (equilibrata) */
    .grid{
      display:grid;
      grid-template-columns: minmax(84px, 9ch) repeat(7,1fr);
      border:1px solid var(--divider-color);
      position:relative;
      z-index:0;
      overflow:visible;
      min-width:680px;
    }

    .cell{border-left:1px solid var(--divider-color);border-top:1px solid var(--divider-color);height:40px;position:relative;overflow:visible}
    .day{padding:6px;font-weight:600;text-align:center;background:var(--secondary-background-color);text-transform:capitalize;white-space:nowrap}
    .time{padding:4px;font-size:12px;white-space:nowrap}

    .events-overlay{position:absolute;inset:0;pointer-events:none;z-index:2}
    .daycol{position:absolute;top:0;bottom:0;left:0;right:0;pointer-events:none}

    .rule{
      position:absolute;
      left:4px;
      right:4px;
      border-radius:6px;
      padding:4px 6px;
      font-size:12px;
      color:#fff;
      background:#5a8e62;
      border:1px solid #3d6a46;
      cursor:pointer;
      opacity:.98;
      box-sizing:border-box;
      display:flex;
      align-items:center;
      gap:6px;
      pointer-events:auto;
      z-index:3;
    }
    .rule.temp{opacity:.7}
    .rule.disabled{
      opacity:.45;
      filter:saturate(.7);
      background-image:repeating-linear-gradient(45deg,
        rgba(255,255,255,.18) 0,
        rgba(255,255,255,.18) 6px,
        rgba(0,0,0,0) 6px,
        rgba(0,0,0,0) 12px
      );
    }
    .rule ha-icon{--mdc-icon-size:16px}

    /* ✅ testo regola sempre “ellissabile” */
    .rule span{
      min-width:0;
      white-space:nowrap;
      overflow:hidden;
      text-overflow:ellipsis;
      flex:1 1 auto;
    }

    .section{margin-top:12px;padding-top:12px;border-top:1px solid var(--divider-color)}
    .section-title{font-weight:600;margin-bottom:6px}

    /* FIX 2: compatta su viewport piccola */
    @media (max-width: 480px){
      .wrap{ padding: 6px; }
      .grid{ min-width: 0; }
      /* ✅ mobile: colonna orari un filo più compatta */
      .grid{ grid-template-columns: minmax(72px, 8ch) repeat(7, 1fr); }
      .cell{ height: 36px; }
      .time{ font-size: 11px; padding: 3px; }
      .day{ font-size: 11px; padding: 5px; }
    }

    /* ✅ leggibilità regole quando la CARD è stretta */
    @container (max-width: 480px){
      .rule{
        padding:2px 4px;
        font-size:11px;
        gap:4px;
      }
      /* Priorità testo su card stretta */
      .rule ha-icon{ display:none; }
    }

  </style>

  <ha-card>
    <div class="wrap">
      <div class="hdr">
        <div class="hdr-left">
          <div class="title" id="title"></div>
        </div>
        <div class="hdr-center">
          <button class="btn" id="btn_add">+ Aggiungi regola</button>
        </div>
        <div class="hdr-right">
          <button class="chip-btn chip-enable" id="btn_enable_all" type="button">Abilita</button>
          <button class="chip-btn chip-disable" id="btn_disable_all" type="button">Disabilita</button>
        </div>
      </div>

      <div class="stage" id="stage">
        <div class="grid" id="grid"></div>
        <div class="events-overlay" id="overlay"></div>
      </div>
    </div>
  </ha-card>`;

  this._els={
    title:root.getElementById('title'),
    grid:root.getElementById('grid'),
    overlay:root.getElementById('overlay'),
    btn_add:root.getElementById('btn_add'),
    stage:root.getElementById('stage'),
    btn_enable_all: root.getElementById('btn_enable_all'),
    btn_disable_all: root.getElementById('btn_disable_all'),
  };

  this._els.btn_add.addEventListener('click',(ev)=>{ev.preventDefault();ev.stopPropagation();this._openDialog({});});
  this._els.btn_enable_all.addEventListener('click',(ev)=>{ev.preventDefault();ev.stopPropagation();this._setAllEnabled(true);});
  this._els.btn_disable_all.addEventListener('click',(ev)=>{ev.preventDefault();ev.stopPropagation();this._setAllEnabled(false);});

  this._buildGrid();
  this._rebuildOverlayColumns();
  this._layoutReady=true;
}

  _toHour(val,fallback=0){ if(typeof val==='number'&&Number.isFinite(val)) return Math.max(0,Math.min(24,val)); if(typeof val==='string'&&val){ const h=parseInt(val.split(':')[0],10); if(Number.isFinite(h)) return Math.max(0,Math.min(24,h)); } return fallback; }
  _getSlotMinutes(){ const v=Number(this._config?.slot_minutes); return [15,30,45,60].includes(v)?v:60; }
  _weekdayNames(locale='it'){ const base=new Date(Date.UTC(2020,10,2)); const fmt=new Intl.DateTimeFormat(locale||'it',{weekday:'long'}); return Array.from({length:7},(_,i)=>{ const d=new Date(base); d.setUTCDate(base.getUTCDate()+i); return fmt.format(d); }); }

  _buildGrid(){
    const g=this._els.grid; if(!g) return;
    g.innerHTML='';
    const days=this._weekdayNames(this._config.locale);
    g.appendChild(this._cell('','day')); for(const d of days) g.appendChild(this._cell(d,'day'));
    const startHour=this._toHour(this._config.start_hour,6);
    const endHour=this._toHour(this._config.end_hour,22);
    const slotMin=this._getSlotMinutes();
    let curMin=startHour*60; const endMin=endHour*60;
    while(curMin<endMin){
      const hh=Math.floor(curMin/60); const mm=curMin%60;
      const label=`${String(hh).padStart(2,'0')}:${String(mm).padStart(2,'0')}`;
      g.appendChild(this._cell(label,'time'));
      for(let wd=0;wd<7;wd++){ const c=this._cell('',''); c.dataset.wd=String(wd); c.dataset.h=String(hh); g.appendChild(c); }
      curMin+=slotMin;
    }
    this._measure();
  }

  _cell(t,c){ const d=document.createElement('div'); d.className='cell '+(c||''); if(t) d.textContent=t; return d; }
  _measure(){ const headerCell=this.shadowRoot.querySelector('.grid .day'); const timeCell=this.shadowRoot.querySelector('.grid .time'); this._headerPx=headerCell?headerCell.getBoundingClientRect().height:40; this._rowPx=timeCell?timeCell.getBoundingClientRect().height:40; }

  _rebuildOverlayColumns(){
    const overlay=this._els.overlay; if(!overlay) return;
    const grid=this._els.grid; if(!grid) return;
    const gr=grid.getBoundingClientRect();
    const headers=this.shadowRoot.querySelectorAll('.grid .day');
    const want=7;
    let cols=Array.from(overlay.querySelectorAll('.daycol'));
    for(let i=cols.length;i<want;i++){ const col=document.createElement('div'); col.className='daycol'; col.dataset.day=String(i); overlay.appendChild(col); cols.push(col); }
    cols=Array.from(overlay.querySelectorAll('.daycol')).slice(0,want);
    cols.forEach((col,i)=>{ col.dataset.day=String(i); });
    for(let i=0;i<want;i++){
      const hd=headers[i+1]; const col=cols[i];
      if(!hd||!col) continue;
      const r=hd.getBoundingClientRect();
      const left=r.left-gr.left; const width=r.width;
      col.style.left=left+'px'; col.style.width=width+'px';
    }
    this._measure();
    this._relayoutBlocks();
  }

  _resolveRulesEntity(hass){
    if(this._config.rules_entity&&hass.states[this._config.rules_entity]) return this._config.rules_entity;
    return undefined;
  }

  _ensureDayColumn(day){
    const col = this._els?.overlay?.querySelector(`.daycol[data-day="${day}"]`);
    return col || null;
  }

  _sanitizeIcon(iconRaw){ const v=String(iconRaw||'').trim(); return v.startsWith('mdi:')?v:''; }
  _uidForRule(r){ const real=r?.id??r?.uid; if(real!=null&&String(real)!=='') return String(real); const day=Number(r?.day??r?.weekday??-1); const start=String(r?.start||r?.time||'').slice(0,5); const end=String(r?.end||'').slice(0,5); const title=String(r?.title||r?.service||''); const svc=String(r?.service||''); const esvc=String(r?.end_service||''); return 's:'+[day,start,end,title,svc,esvc].join('|'); }

  _decorateBlock(block,rule){
    const color=_normalizeHex(rule.color||rule.ui_color||this._config.default_color,this._config.default_color);
    block.style.background=color; block.style.borderColor=_darkenHex(color,25); block.style.color=_idealTextColor(color);
    block.innerHTML='';
    const icon=(rule.icon&&String(rule.icon).startsWith('mdi:'))?String(rule.icon):'';
    if(icon){ const ic=document.createElement('ha-icon'); ic.setAttribute('icon',icon); block.appendChild(ic); }
    const label=(rule.title||rule.service||'Action'); const span=document.createElement('span'); span.textContent=label; block.appendChild(span);
    const startStr=(rule.start||rule.time||'00:00').slice(0,5); const endStr=(rule.end||startStr).slice(0,5);
    block.title=`${label} — ${startStr}${rule.end?' → '+endStr:''}`;
    block.dataset.day=String(Number(rule.day??rule.weekday??-1));
    block.dataset.start=startStr; block.dataset.end=endStr;
    const geom=this._computeGeom(rule);
    block.style.top=`${geom.top}px`; block.style.height=`${geom.height}px`;
    const enabled = (rule.enabled !== false);
    block.classList.toggle('disabled', !enabled);
  }

  _computeGeom(rule){
    const startStr=(rule.start||rule.time||'00:00').slice(0,5);
    const endStr=(rule.end||startStr).slice(0,5);
    const [sh,sm]=startStr.split(':').map(Number); const [eh,em]=endStr.split(':').map(Number);
    const startHour=this._toHour(this._config.start_hour,6); const slotMin=this._getSlotMinutes(); const startMinBaseline=startHour*60;
    const startAbsMin=(sh*60)+(sm||0); const endAbsMin=(eh*60)+(em||0);
    const deltaStartSlots=(startAbsMin-startMinBaseline)/slotMin; const durationSlots=(endAbsMin-startAbsMin)/slotMin;
    const headerPx=this._headerPx||40, rowPx=this._rowPx||40;
    const rawTop=headerPx+(deltaStartSlots*rowPx); const top=Math.max(headerPx,rawTop);
    const height=Math.max(20,(durationSlots<=0 ? (1*rowPx) : (durationSlots*rowPx)));
    return {top,height};
  }

  _relayoutBlocks(){
    const overlay=this._els?.overlay; if(!overlay) return;
    const headerPx=this._headerPx||40, rowPx=this._rowPx||40;
    const startHour=this._toHour(this._config.start_hour,6); const slotMin=this._getSlotMinutes(); const startMinBaseline=startHour*60;
    overlay.querySelectorAll('.rule').forEach(block=>{
      const day=Number(block.dataset.day??-1);
      const startStr=String(block.dataset.start||'00:00'); const endStr=String(block.dataset.end||startStr);
      const [sh,sm]=startStr.split(':').map(Number); const [eh,em]=endStr.split(':').map(Number);
      const startAbsMin=(sh*60)+(sm||0); const endAbsMin=(eh*60)+(em||0);
      const deltaStartSlots=(startAbsMin-startMinBaseline)/slotMin; const durationSlots=(endAbsMin-startAbsMin)/slotMin;
      const rawTop=headerPx+(deltaStartSlots*rowPx); const top=Math.max(headerPx,rawTop);
      const height=Math.max(20,(durationSlots<=0 ? (1*rowPx) : (durationSlots*rowPx)));
      block.style.top=`${top}px`; block.style.height=`${height}px`;
      if(!Number.isNaN(day)&&day>=0&&day<=6){
        const curr=block.closest('.daycol')?.dataset?.day;
        if(String(curr)!==String(day)){
          const col=this._ensureDayColumn(day); if(col){ block.remove(); col.appendChild(block); }
        }
      }
    });
  }

  _findRuleBlockByUid(uid){ if(!uid) return null; try{ return this._els?.overlay?.querySelector(`.rule[data-uid="${_cssEscape(String(uid))}"]`)||null; }catch(_){ return null; } }

  _rulesEqual(a,b){
    if(!a||!b) return false;
    const g=(r)=>({
      day:Number(r.day??r.weekday),
      start:String(r.start||r.time||'').slice(0,5),
      end:String(r.end||'').slice(0,5),
      title:String(r.title||r.service||''),
      color:String(r.color||r.ui_color||''),
      icon:(r.icon&&String(r.icon).startsWith('mdi:'))?String(r.icon):'',
      service:String(r.service||''),
      end_service:String(r.end_service||''),
      enabled:(r.enabled!==false),
      tags:_tagsToArray(r.tags).sort().join('|')
    });
    const A=g(a),B=g(b);
    return A.day===B.day&&A.start===B.start&&A.end===B.end&&A.title===B.title&&A.color===B.color&&A.icon===B.icon&&A.service===B.service&&A.end_service===B.end_service&&A.enabled===B.enabled&&A.tags===B.tags;
  }


_getFreshRuleById(rid, fallbackRule){
  try{
    const st = this._hass?.states?.[this._rulesEntityId];
    const rules = st?.attributes?.rules || [];
    const found = rules.find(x => String(x?.id ?? x?.uid ?? '') === String(rid ?? ''));
    return found || fallbackRule;
  }catch(_){
    return fallbackRule;
  }
}

_openDialogFresh(fallbackRule, blockEl){
  const rid = blockEl?.dataset?.realId || blockEl?.dataset?.uid || fallbackRule?.id || fallbackRule?.uid;
  const fresh = this._getFreshRuleById(rid, fallbackRule);
  this._openDialog({ existing: fresh, blockEl });
}



async _setAllEnabled(enabled){
  try{
    if(!this._hass || !this._rulesEntityId) return;

    const pid = this._getPlannerId();
    const st = this._hass.states?.[this._rulesEntityId];
    const rules = (st?.attributes?.rules) || [];
    if(!Array.isArray(rules) || !rules.length) return;

    // prendo gli id reali
    const ids = rules
      .map(r => r?.id ?? r?.uid)
      .filter(x => x != null && String(x).trim() !== '')
      .map(x => String(x));

    if(!ids.length) return;

    // batching per non stressare HA
    const batchSize = 10;
    for(let i=0; i<ids.length; i+=batchSize){
      const batch = ids.slice(i, i+batchSize);
      await Promise.all(batch.map(id =>
        this._hass.callService('chronotask', 'update_rule', pid ? { planner_id: pid, id, enabled } : { id, enabled })
      ));
      // piccola pausa tra batch
      await new Promise(res => setTimeout(res, 120));
    }

    // refresh UI
    this._scheduleUpdate();

  }catch(err){
    console.error('ChronoTask setAllEnabled error:', err);
  }
}


  _getPlannerId(){
    try{
      const eid=this._rulesEntityId;
      const st = (eid && this._hass?.states?.[eid]) ? this._hass.states[eid] : undefined;
      return this._config.planner_id || st?.attributes?.planner_id || this._plannerId;
    }catch(_){ return this._config.planner_id; }
  }

  async _update(){
    if(!this._hass||!this._els) return;

    if(!this._rulesEntityId||!this._hass.states[this._rulesEntityId]){
      this._els.title.textContent=`${this._config.title} — (configura rules_entity)`;
      return;
    }
    this._els.title.textContent=this._config.title;

    // Rimuovi SOLO temp scaduti; non toccare i blocchi pending ottimistici
    try{
      const now=Date.now();
      this._els.overlay.querySelectorAll('.rule.temp').forEach(el=>{
        const pid = el.dataset.pendingId ? String(el.dataset.pendingId) : '';
        if (pid && this._pendingEdits.has(pid)) return;
        const ts=Number(el.dataset.tempTs||0);
        if(ts && (now-ts)>this._pendingTTL) el.remove();
      });
    }catch(_){ }

    const st=this._hass.states[this._rulesEntityId];
    const rules=(st?.attributes?.rules)||[];
    this._plannerId=st?.attributes?.planner_id||undefined;

    this._rebuildOverlayColumns();
    this._measure();

    // Cleanup pending scaduti
    const now=Date.now();
    for(const [rid,entry] of Array.from(this._pendingEdits.entries())){
      if(!entry) { this._pendingEdits.delete(rid); continue; }
      const until = Number(entry.until||0);
      if (!until || now>until) this._pendingEdits.delete(rid);
    }

    const overlay=this._els.overlay;

    // Indicizza blocchi reali (non temp)
    const existingBlocks=new Map();
    overlay.querySelectorAll('.rule:not(.temp)').forEach(block=>{
      const uid=block.dataset.uid||'';
      if(uid) existingBlocks.set(uid, block);
    });

    const seenUids=new Set();
    for(const r of rules){
      const uid=this._uidForRule(r);
      const day=Number(r.day??r.weekday);
      if(Number.isNaN(day)||day<0||day>6) continue;

      const realId = (r.id ?? r.uid ?? null);
      const pending = realId ? this._pendingEdits.get(String(realId)) : null;

      if (pending) {
        if (!this._rulesEqual(r, pending.payload)) {
          // Mantieni il blocco ottimistico e non renderizzare quello reale ancora
          continue;
        } else {
          // Il sensore riflette -> rimuovi stato pending e normalizza eventuale blocco ottimistico
          const pendEl = overlay.querySelector(`.rule[data-pending-id="${_cssEscape(String(realId))}"]`);
          if (pendEl) {
            pendEl.classList.remove('pending');
            pendEl.removeAttribute('data-pending-id');
          }
          this._pendingEdits.delete(String(realId));
        }
      }

      seenUids.add(uid);
      let block=existingBlocks.get(uid);
      if(!block){
        const daycol=this._ensureDayColumn(day); if(!daycol) continue;
        block=document.createElement('div');
        block.className='rule';
        block.dataset.uid=uid;
        if (realId!=null) block.dataset.realId = String(realId);
        daycol.appendChild(block);
        block.addEventListener('click',(ev)=>{
          ev.preventDefault(); ev.stopPropagation();
          requestAnimationFrame(()=> this._openDialogFresh(r, block));
        });
      } else {
        if (realId!=null) block.dataset.realId = String(realId);
      }

      this._decorateBlock(block,r);
    }

    // Rimuovi orfani (non-temp) ma NON quelli marcati pending-id attivo o realId in pending
    overlay.querySelectorAll('.rule:not(.temp)').forEach(block=>{
      const uid=block.dataset.uid||'';
      const pid = block.dataset.pendingId ? String(block.dataset.pendingId) : '';
      const realId = block.dataset.realId || uid;
      const isPending = (pid && this._pendingEdits.has(pid)) || (realId && this._pendingEdits.has(String(realId)));
      if(uid && !seenUids.has(uid) && !isPending){
        block.remove();
      }
    });
  }

  _renderTempBlock(rule,opts={}){
    const day=Number(rule.day??rule.weekday);
    if(isNaN(day)||day<0||day>6) return;
    const daycol=this._els.overlay.querySelector(`.daycol[data-day="${day}"]`);
    if(!daycol) return;

    const startStr=(rule.start||rule.time||'00:00').slice(0,5);
    const endStr=(rule.end||startStr).slice(0,5);
    const [sh,sm]=startStr.split(':').map(Number); const [eh,em]=endStr.split(':').map(Number);

    const startHour=this._toHour(this._config.start_hour,6);
    const slotMin=this._getSlotMinutes();
    const startMinBaseline=startHour*60;

    const startAbsMin=(sh*60)+(sm||0);
    const endAbsMin=(eh*60)+(em||0);
    const deltaStartSlots=(startAbsMin-startMinBaseline)/slotMin;
    const durationSlots=(endAbsMin-startAbsMin)/slotMin;

    const top=(this._headerPx||40)+(deltaStartSlots*(this._rowPx||40));
    const height=Math.max(20,(durationSlots<=0 ? (1*(this._rowPx||40)) : (durationSlots*(this._rowPx||40))));

    const block=document.createElement('div');
    block.className='rule temp';
    if(opts.pendingId) block.dataset.pendingId=String(opts.pendingId);
    block.dataset.tempTs=String(Date.now());

    const color=_normalizeHex(rule.color||rule.ui_color||this._config.default_color,this._config.default_color);
    block.style.cssText=`top:${Math.max(this._headerPx||40, top)}px;height:${height}px;background:${color};border-color:${_darkenHex(color,25)};color:${_idealTextColor(color)};`;

    const icon=(rule.icon&&String(rule.icon).startsWith('mdi:'))?String(rule.icon):'';
    if(icon){ const ic=document.createElement('ha-icon'); ic.setAttribute('icon',icon); block.appendChild(ic); }

    const span=document.createElement('span'); span.textContent=(rule.title||rule.service||'Action')+' (…)'; block.appendChild(span);
    block.title=`${(rule.title||rule.service||'Action')} — ${startStr}${rule.end?' → '+endStr:''}`;

    block.dataset.day=String(day); block.dataset.start=startStr; block.dataset.end=endStr;
    const enabled = (rule.enabled !== false);
    block.classList.toggle('disabled', !enabled);

    daycol.appendChild(block);
  }

  _openDialog(ctx={}){
    if(this._activeDialog){ setTimeout(()=>{ if(!this._activeDialog) this._openDialog(ctx); },120); return; }
    const HaDialog=customElements.get('ha-dialog'); if(!HaDialog){ alert('Dialog avanzato non disponibile: aggiorna Home Assistant.'); return; }
    const existing=ctx.existing||null; const prefill=ctx.prefill||null;
    const dlg=document.createElement('ha-dialog'); this._activeDialog=dlg; dlg.open=true; try{ dlg.scrimClickAction='close'; dlg.escapeKeyAction='close'; }catch(_){ }
    dlg.addEventListener('closed',()=>{ try{ dlg.remove(); }catch(_){ } if(this._activeDialog===dlg) this._activeDialog=null; });

    const content=document.createElement('div'); content.classList.add('apw-root'); content.style.minWidth='360px'; content.style.maxWidth='92vw';
    const dialogTitleText= existing ? 'Modifica regola' : (prefill ? 'Nuova regola (duplica)' : 'Nuova regola');

    content.innerHTML=`<style>.apw-root{display:flex;flex-direction:column;max-height:min(80vh,680px)}.dialog-header{display:grid;grid-template-columns:auto 1fr auto auto;align-items:center;gap:8px;padding:0 0 8px}.dialog-title{font-weight:600;font-size:16px;text-align:center}.danger{color:var(--error-color,#b00020)}.form-row{margin:10px 0}.form-row label{display:block;font-size:12px;opacity:.8;margin-bottom:4px}.form-row input,.form-row select{width:100%;box-sizing:border-box;padding:10px 12px;border-radius:8px;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color);min-height:40px}.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}.dialog-scroll{flex:1 1 auto;overflow:auto;padding:0}.footer3{display:flex;align-items:center;justify-content:center;gap:32px;padding:12px 0 0}.inline2{display:flex;align-items:center;justify-content:space-between;gap:8px}.chip{display:inline-block;padding:2px 8px;border:1px solid var(--divider-color);border-radius:999px;font-size:12px;opacity:.9}.small{font-size:12px;opacity:.8}</style>
      <div class="dialog-header">
        <ha-icon-button id="btn_close" aria-label="Chiudi" icon="mdi:close"></ha-icon-button>
        <div class="dialog-title" id="dlg_title">${dialogTitleText}</div>
        <mwc-button id="btn_duplicate_text" style="${existing?'':'visibility:hidden'}">Duplica</mwc-button>
        <mwc-button id="btn_delete_text" class="danger" style="${existing?'':'visibility:hidden'}">Elimina</mwc-button>
      </div>
      <input type="hidden" id="f_id" />
      <div class="dialog-scroll">
        <div class="form-row inline2">
          <div style="flex:1 1 auto;">
            <label for="f_title">Titolo</label>
            <input id="f_title" placeholder="Es. Luci Soggiorno" />
          </div>
        </div>

        <div class="two">
          <div class="form-row" id="color_wrap"><label for="f_color">Colore etichetta</label><input id="f_color" type="color" /></div>
          <div class="form-row" id="icon_wrap"><label for="f_icon">Icona</label></div>
        </div>

        <div class="form-row">
          <div class="inline2">
            <div><span class="small">Attiva</span></div>
            <div id="enabled_wrap"></div>
          </div>
        </div>

        <div class="form-row">
          <label for="f_tags">Tag (separati da virgole)</label>
          <input id="f_tags" placeholder="es. luci, vacanza" />
        </div>

        <div class="form-row" id="row_entity"><label for="f_entity">Entità</label></div>

        <div class="section"><div class="section-title">Start</div>
          <div class="two">
            <div class="form-row"><label for="f_day">Giorno</label>
              <select id="f_day"><option value="0">Lunedì</option><option value="1">Martedì</option><option value="2">Mercoledì</option><option value="3">Giovedì</option><option value="4">Venerdì</option><option value="5">Sabato</option><option value="6">Domenica</option></select>
            </div>
            <div class="form-row"><label for="f_start">Ora</label><input id="f_start" type="time" step="60" value="08:00" /></div>
          </div>
          <div class="form-row"><label for="f_service_sel">Action</label><select id="f_service_sel"></select></div>
          <div id="svc_fields"></div>
        </div>

        <div class="section"><div class="section-title">End (opzionale)</div>
          <div class="two">
            <div class="form-row"><label for="f_day_end">Giorno</label>
              <select id="f_day_end"><option value="">(uguale allo start)</option><option value="0">Lunedì</option><option value="1">Martedì</option><option value="2">Mercoledì</option><option value="3">Giovedì</option><option value="4">Venerdì</option><option value="5">Sabato</option><option value="6">Domenica</option></select>
            </div>
            <div class="form-row"><label for="f_end">Ora</label><input id="f_end" type="time" step="60" placeholder="09:00" /></div>
          </div>
          <div class="form-row"><label for="f_service_sel_end">Action</label><select id="f_service_sel_end"></select></div>
          <div id="svc_fields_end"></div>
        </div>
      </div>
      <div class="footer3"><mwc-button id="btn_cancel">Annulla</mwc-button><mwc-button id="btn_save">Salva</mwc-button></div>`;

    dlg.appendChild(content); document.body.appendChild(dlg);

    const $=(sel)=>content.querySelector(sel);
    const f_id=$('#f_id'), f_title=$('#f_title'), f_day=$('#f_day'), f_start=$('#f_start'), f_day_end=$('#f_day_end'), f_end=$('#f_end');
    const f_color=$('#f_color'); const row_entity=$('#row_entity'); const f_service_sel=$('#f_service_sel'); const svc_fields=$('#svc_fields'); const f_service_sel_end=$('#f_service_sel_end'); const svc_fields_end=$('#svc_fields_end'); const icon_wrap=$('#icon_wrap');
    const f_tags=$('#f_tags');

    const stepSec=this._getSlotMinutes()*60; try{ if(f_start) f_start.step=String(stepSec); if(f_end) f_end.step=String(stepSec);}catch(_){ }

    // Enabled switch
    let enabledSwitch=null;
    const enabledWrap=$('#enabled_wrap');
    if(customElements.get('ha-switch')){
      enabledSwitch=document.createElement('ha-switch');
      enabledSwitch.checked = true;
      enabledWrap.appendChild(enabledSwitch);
    } else {
      // fallback
      enabledSwitch=document.createElement('input'); enabledSwitch.type='checkbox'; enabledSwitch.checked=true;
      enabledWrap.appendChild(enabledSwitch);
    }

    let f_icon=null, icon_picker=null;
    if(customElements.get('ha-icon-picker')){
      icon_picker=document.createElement('ha-icon-picker');
      icon_picker.hass=this._hass; icon_picker.label='Seleziona icona (mdi)'; icon_picker.value='';
      try{ icon_picker.setAttribute('outlined',''); }catch(_){ }
      icon_picker.style.cssText='display:block;width:100%;box-sizing:border-box;border:1px solid var(--divider-color);border-radius:8px;min-height:40px;padding:6px 8px;background:var(--card-background-color);color:var(--primary-text-color)';
      icon_wrap.appendChild(icon_picker);
      icon_picker.addEventListener('value-changed',ev=>{ const v=this._sanitizeIcon(ev.detail?.value); icon_picker.value=v; });
    } else {
      f_icon=document.createElement('input'); f_icon.id='f_icon'; f_icon.placeholder='mdi:lightbulb'; f_icon.style.cssText='width:100%;box-sizing:border-box;min-height:40px'; icon_wrap.appendChild(f_icon);
    }
    const getIconValue=()=> (icon_picker? this._sanitizeIcon(icon_picker.value): this._sanitizeIcon(f_icon?.value||''));
    const setIconValue=(val)=>{ const v=this._sanitizeIcon(val); if(icon_picker) icon_picker.value=v; else if(f_icon) f_icon.value=v; };

    // Entity picker
    let f_entity;
    const includeDomains=Array.isArray(this._config.entity_include_domains)?this._config.entity_include_domains:undefined;
    const excludeDomains=Array.isArray(this._config.entity_exclude_domains)?this._config.entity_exclude_domains:undefined;
    const makeFilterFn=(q)=>{ const qq=String(q||'').trim().toLowerCase(); if(!qq) return ()=>true; return (eid,st)=>{ const name=(st?.attributes?.friendly_name||'').toLowerCase(); return eid.toLowerCase().includes(qq) || name.includes(qq); }; };
    if(customElements.get('ha-entity-picker')){
      const ep=document.createElement('ha-entity-picker');
      ep.id='f_entity'; ep.hass=this._hass;
      ep.setAttribute('allow-custom-entity',''); ep.setAttribute('required',''); ep.setAttribute('show-entity-id',''); ep.placeholder='Cerca entità…';
      if(includeDomains) ep.includeDomains=includeDomains; if(excludeDomains) ep.excludeDomains=excludeDomains;
      try{ ep.setAttribute('outlined',''); }catch(_){ }
      row_entity.appendChild(ep); f_entity=ep;
      const openIfPossible=()=>{ try{ if(typeof ep.open==='function') ep.open(); }catch(_){ } };
      ['focus','click','value-changed','input'].forEach(evt=> ep.addEventListener(evt, openIfPossible));
      let lastTimer=null; const pingRefresh=()=>{ if(lastTimer) clearTimeout(lastTimer); lastTimer=setTimeout(()=>openIfPossible(),60); };
      ['value-changed','input'].forEach(evt=> ep.addEventListener(evt, pingRefresh));
    } else {
      const inp=document.createElement('input'); inp.id='f_entity'; inp.placeholder='es. light.soggiorno'; inp.autocomplete='off'; inp.style.cssText='width:100%;box-sizing:border-box;min-height:40px';
      const dl=document.createElement('datalist'); const dlId='entity_suggestions_'+Math.random().toString(36).slice(2); dl.id=dlId; inp.setAttribute('list',dlId);
      const all=Object.keys(this._hass?.states||{}).map(eid=>({eid,st:this._hass.states[eid]})).filter(({eid})=>{
        const dom=eid.split('.')[0]; if(includeDomains && !includeDomains.includes(dom)) return false; if(excludeDomains && excludeDomains.includes(dom)) return false; return true;
      });
      const rebuild=(q='')=>{ const filter=makeFilterFn(q); dl.innerHTML=''; let count=0; for(const {eid,st} of all){ if(!filter(eid,st)) continue; const opt=document.createElement('option'); opt.value=eid; opt.label=(st?.attributes?.friendly_name)||eid; dl.appendChild(opt); if(++count>=150) break; } };
      rebuild('');
      let t=null; const onType=()=>{ clearTimeout(t); t=setTimeout(()=>rebuild(inp.value||''),60); };
      ['input','change','keyup','focus'].forEach(evt=> inp.addEventListener(evt,onType));
      row_entity.appendChild(inp); row_entity.appendChild(dl); f_entity=inp;
    }
    const getEntityId=()=> (row_entity.querySelector('#f_entity')?.value||'').trim();

    // Prefill existing
    if(existing){ try{
      if(existing.id||existing.uid) f_id.value=String(existing.id||existing.uid);
      f_title.value=(existing.title||existing.service||'Action').trim();
      const dayVal=(typeof existing.day==='number')?existing.day: (typeof existing.weekday==='number'?existing.weekday:undefined);
      if(dayVal!=null) f_day.value=String(dayVal);
      if(existing.start||existing.time) f_start.value=String((existing.start||existing.time)).slice(0,5);
      if(typeof existing.end_day==='number') f_day_end.value=String(existing.end_day);
      if(existing.end) f_end.value=String(existing.end).slice(0,5);
      // enabled
      enabledSwitch.checked = (existing.enabled !== false);
      // tags
      f_tags.value = _tagsToText(existing.tags);
    }catch(_){ } }

    // Prefill for new/duplicate
    if(!existing && prefill){
      try{
        if(prefill.title) f_title.value = String(prefill.title);
        if(typeof prefill.day==='number') f_day.value = String(prefill.day);
        if(prefill.start) f_start.value = String(prefill.start).slice(0,5);
        if(prefill.end) f_end.value = String(prefill.end).slice(0,5);
        if(typeof prefill.end_day==='number') f_day_end.value = String(prefill.end_day);
        enabledSwitch.checked = (prefill.enabled !== false);
        f_tags.value = _tagsToText(prefill.tags);
      }catch(_){ }
    }

    const preSelStart=(existing?.service)??(prefill?.service)??'';
    const preSelEnd=(existing?.end_service)??(prefill?.end_service)??'';
    const preDataStart=(existing?.service_data)??(prefill?.service_data)??{};
    const preDataEnd=(existing?.end_service_data)??(prefill?.end_service_data)??{};
    const existingEntityId=preDataStart?.entity_id||preDataEnd?.entity_id||'';
    if(existingEntityId){ try{ (row_entity.querySelector('#f_entity')||{}).value=existingEntityId; }catch(_){ } }

    // Dynamic services & fields
    const _getDomain=(entityId)=>{ if(!entityId||typeof entityId!=='string') return ''; const i=entityId.indexOf('.'); return i>0?entityId.slice(0,i):''; };
    const _listServicesForDomain=(domain,includeHA)=>{ const svc=(this._hass&&this._hass.services)||{}; const list=[]; if(domain && svc[domain]){ for(const s of Object.keys(svc[domain])) list.push(`${domain}.${s}`);} if(includeHA){ ['turn_on','turn_off','toggle'].forEach(s=>{ if(svc.homeassistant&&svc.homeassistant[s]) list.push(`homeassistant.${s}`);}); } list.sort((a,b)=>{ const pr=x=> (x.endsWith('.turn_on')||x.endsWith('.turn_off')||x.endsWith('.toggle'))?0:1; return pr(a)-pr(b)||a.localeCompare(b); }); return Array.from(new Set(list)); };
    const _renderServiceFields=(container,fullService,entityId,currentData={})=>{
      container.innerHTML=''; if(!fullService) return;
      const [domain,service]=fullService.split('.');
      const addRow=(name,label,type='text',attrs={})=>{
        const row=document.createElement('div'); row.className='form-row';
        const id=`svc_field_${name}_${container.id}`;
        const lab=document.createElement('label'); lab.setAttribute('for',id); lab.textContent=label; row.appendChild(lab);
        let input;
        if(type==='select'){ input=document.createElement('select'); (attrs.options||[]).forEach(opt=>{ const o=document.createElement('option'); o.value=String(opt); o.textContent=String(opt); input.appendChild(o);}); }
        else { input=document.createElement('input'); input.type=type; if(attrs.min!=null) input.min=String(attrs.min); if(attrs.max!=null) input.max=String(attrs.max); if(attrs.step!=null) input.step=String(attrs.step); if(attrs.placeholder) input.placeholder=attrs.placeholder; }
        input.id=id; input.setAttribute('data-field',name);
        const v=currentData[name]; if(v!=null) input.value=String(v);
        row.appendChild(input); container.appendChild(row); return input;
      };
      if(domain==='light'&&service==='turn_on'){ addRow('brightness','Luminosità (0–255)','number',{min:0,max:255,step:1}); addRow('transition','Transizione (s)','number',{min:0,step:0.1}); addRow('effect','Effetto','text',{placeholder:'es. colorloop'}); }
      else if(domain==='climate'&&service==='set_temperature'){ addRow('temperature','Temperatura','number',{min:5,max:35,step:0.5}); }
      else if(domain==='climate'&&service==='set_hvac_mode'){ addRow('hvac_mode','HVAC mode','select',{options:['off','heat','cool','auto','dry','fan_only']}); }
      else if(domain==='cover'&&(service==='set_cover_position'||service==='set_position')){ addRow('position','Posizione (0–100)','number',{min:0,max:100,step:1}); }
      else if(domain==='media_player'&&service==='volume_set'){ addRow('volume_level','Volume (0.0–1.0)','number',{min:0,max:1,step:0.01}); }
      const meta=(this._hass?.services?.[domain]?.[service])||null;
      if(meta?.fields){
        for(const [fname,fdesc] of Object.entries(meta.fields)){
          if(container.querySelector(`[data-field="${fname}"]`)) continue;
          const label=(fdesc?.name||fdesc?.description)?(fdesc.name||fdesc.description):fname;
          const isNum=/temperature|position|volume|brightness|delay|duration|transition|level|percent/.test(fname);
          addRow(fname,label,isNum?'number':'text');
        }
      }
    };
    const _populateServiceSelect=(selectEl,services,preselected)=>{
      if(!selectEl) return; selectEl.innerHTML='';
      const placeholder=document.createElement('option'); placeholder.value=''; placeholder.textContent='(seleziona servizio)'; selectEl.appendChild(placeholder);
      for(const svc of services){ const opt=document.createElement('option'); opt.value=String(svc); opt.textContent=String(svc); selectEl.appendChild(opt); }
      if(preselected && !services.includes(preselected)){ const extra=document.createElement('option'); extra.value=preselected; extra.textContent=preselected+' (non nel dominio attuale)'; selectEl.appendChild(extra);}
      selectEl.value=preselected && (services.includes(preselected) || preselected) ? preselected : '';
    };
    const _collectServiceData=(container)=>{
      const data={}; container.querySelectorAll('[data-field]').forEach(el=>{
        const name=el.getAttribute('data-field'); const raw=(el.value??'').toString();
        if(el.type==='number'){ if(raw.trim()==='') return; const num=Number(raw); if(!Number.isFinite(num)) return; data[name]=num; }
        else { if(raw.trim()!=='') data[name]=raw.trim(); }
      }); return data;
    };

    const refreshServiceSelects=(opts={preserveSelection:false})=>{
      const domain=_getDomain(getEntityId());
      const services=_listServicesForDomain(domain,!domain);
      const selStart=opts.preserveSelection?(f_service_sel.value||preSelStart):preSelStart;
      const selEnd=opts.preserveSelection?(f_service_sel_end.value||preSelEnd):preSelEnd;
      _populateServiceSelect(f_service_sel,services,selStart);
      _populateServiceSelect(f_service_sel_end,services,selEnd);
      const eid=getEntityId();
      _renderServiceFields(svc_fields,f_service_sel.value,eid,f_service_sel.value===preSelStart?preDataStart:{});
      _renderServiceFields(svc_fields_end,f_service_sel_end.value,eid,f_service_sel_end.value===preSelEnd?preDataEnd:{});
    };

    refreshServiceSelects();
    const f_entityEl=row_entity.querySelector('#f_entity'); if(f_entityEl){ const onEntityChange=()=>refreshServiceSelects({preserveSelection:true}); ['value-changed','change','input','focus'].forEach(evt=> f_entityEl.addEventListener(evt,onEntityChange)); }
    f_service_sel.addEventListener('change',()=>{ const eid=getEntityId(); _renderServiceFields(svc_fields,f_service_sel.value,eid,{}); });
    f_service_sel_end.addEventListener('change',()=>{ const eid=getEntityId(); _renderServiceFields(svc_fields_end,f_service_sel_end.value,eid,{}); });

    const doClose=()=>{ try{ dlg.close(); }catch(_){ } };
    const getPlannerId=()=> this._getPlannerId();

    // Duplica
    const btn_duplicate=content.querySelector('#btn_duplicate_text');
    if(btn_duplicate){
      btn_duplicate.addEventListener('click',(ev)=>{
        ev.preventDefault(); ev.stopPropagation();
        const eid=getEntityId();
        const startService=(f_service_sel.value||'').trim();
        const startData=_collectServiceData(svc_fields); if(eid) startData.entity_id=eid;
        const endService=(f_service_sel_end.value||'').trim();
        const endData=_collectServiceData(svc_fields_end); if(eid && endService) endData.entity_id=eid;
        const colorHex=_toHexFromAny(f_color.value||this._config.default_color,this._config.default_color);
        const iconVal=this._sanitizeIcon(getIconValue());
        const dupPrefill={ title:(f_title.value||'Action').trim(), day:Number(f_day.value), start:(f_start.value||'08:00').slice(0,5), service:startService, service_data:startData, color:colorHex, ui_color:colorHex, enabled: enabledSwitch.checked, tags: _tagsToArray(f_tags.value), ...(iconVal?{icon:iconVal}:{}) };
        const endTime=(f_end.value||'').trim().slice(0,5); const endDayRaw=(f_day_end.value||'').trim();
        if(endTime) dupPrefill.end=endTime;
        if(endDayRaw!=='' && !Number.isNaN(Number(endDayRaw))) dupPrefill.end_day=Number(endDayRaw);
        if(endService){ dupPrefill.end_service=endService; dupPrefill.end_service_data=endData; }
        doClose();
        setTimeout(()=> this._openDialog({prefill:dupPrefill}),50);
      });
    }

    // Salva (ADD/EDIT)
    const doSave=async()=>{
      if(!this._hass) return;
      const eid=getEntityId();
      const serviceStart=(f_service_sel.value||'').trim();
      if(!serviceStart){ console.warn('Seleziona un servizio di inizio.'); return; }

      let picked=(f_color&&f_color.value)?String(f_color.value).toLowerCase():'';
      const initial=(f_color?.dataset?.initialHex||'').toLowerCase();
      if(!picked||picked==='#000000') picked=initial||this._config.default_color;
      const colorHex=_toHexFromAny(picked,this._config.default_color);

      const startVal=(f_start.value||'08:00').slice(0,5);
      const svcStartData=_collectServiceData(svc_fields);
      if(eid) svcStartData.entity_id=eid;
      if(serviceStart==='light.turn_on'){
        if(svcStartData.brightness===0) delete svcStartData.brightness;
        if(svcStartData.brightness_pct===0) delete svcStartData.brightness_pct;
      }
      const iconVal=this._sanitizeIcon(getIconValue());
      const payload={
        title:(f_title.value||(existing?.title||existing?.service)||'Action').trim(),
        day:Number(f_day.value),
        start:startVal,
        service:serviceStart,
        service_data:svcStartData,
        color:colorHex, ui_color:colorHex,
        enabled: !!enabledSwitch.checked,
        tags: _tagsToArray(f_tags.value),
        ...(iconVal?{icon:iconVal}:{}),
      };
      const endTime=(f_end.value||'').trim().slice(0,5);
      const endService=(f_service_sel_end.value||'').trim();
      const endDayRaw=(f_day_end.value||'').trim();
      if(endTime) payload.end=endTime;
      if(endDayRaw!=='' && !Number.isNaN(Number(endDayRaw))) payload.end_day=Number(endDayRaw);
      if(endService){
        const endData=_collectServiceData(svc_fields_end); if(eid) endData.entity_id=eid;
        if(endService==='light.turn_on'){
          if(endData.brightness===0) delete endData.brightness;
          if(endData.brightness_pct===0) delete endData.brightness_pct;
        }
        payload.end_service=endService; payload.end_service_data=endData;
      }

      const pid=getPlannerId();
      const svcBase = pid ? { planner_id:pid, ...payload } : payload;

      const ct=this._hass?.services?.chronotask||{};
      const hasUpdate=!!ct.update_rule; const hasAdd=!!ct.add_rule;

      try{
        if(existing && hasUpdate){
          const idInfo=existing?.id||existing?.uid||(f_id.value||null);
          const updatePayload={ ...(svcBase), ...(idInfo?{id:idInfo,rule_id:idInfo,uid:idInfo}:{}) };

          if(idInfo){
            // UPDATE ottimistico: aggiorna/subentra subito il blocco reale con i nuovi dati
            let block=this._findRuleBlockByUid(idInfo);
            if(!block){
              const col=this._ensureDayColumn(payload.day);
              if(col){
                block=document.createElement('div');
                block.className='rule';
                block.dataset.uid=String(idInfo);
                block.dataset.realId=String(idInfo);
                col.appendChild(block);
                block.addEventListener('click',(ev)=>{ ev.preventDefault(); ev.stopPropagation(); requestAnimationFrame(()=> this._openDialogFresh({ ...payload, id:idInfo, uid:idInfo }, block)); });
              }
            } else {
              block.dataset.realId=String(idInfo);
            }
            if(block){
              block.dataset.pendingId=String(idInfo);
              block.classList.add('pending');
              this._decorateBlock(block, { ...payload, id:idInfo, uid:idInfo });
            }
            this._pendingEdits.set(String(idInfo), {
              payload:{...payload, id:idInfo, uid:idInfo},
              kind:'update',
              since: Date.now(),
              until: Date.now() + this._pendingUpdateTTL
            });
            await this._hass.callService('chronotask','update_rule', updatePayload);
            setTimeout(()=> this._scheduleUpdate(), 200);
          } else {
            await this._hass.callService('chronotask','add_rule', svcBase);
            this._renderTempBlock(payload);
            setTimeout(()=> this._scheduleUpdate(), 200);
          }
        }
        else if(hasAdd){
          await this._hass.callService('chronotask','add_rule', svcBase);
          this._renderTempBlock(payload);
          setTimeout(()=> this._scheduleUpdate(), 200);
        } else {
          console.error('ChronoTask: nessun servizio disponibile per salvare la regola.');
        }
      }catch(err){ console.error('ChronoTask save error:', err); }

      doClose();
    };

    const btn_delete=content.querySelector('#btn_delete_text');
    const doDelete=async()=>{
      if(!existing) return;
      const prevText=btn_delete.textContent; btn_delete.disabled=true; btn_delete.textContent='Eliminando…';

      const pid=getPlannerId();
      const idInfo=existing?.id??existing?.uid??(f_id.value||null);
      if(!idInfo){
        console.warn('Nessun id/uid trovato per la regola; impossibile eliminare.');
        btn_delete.disabled=false; btn_delete.textContent=prevText; return;
      }
      const payload= pid ? { planner_id:pid, id:idInfo, rule_id:idInfo, uid:idInfo } : { id:idInfo, rule_id:idInfo, uid:idInfo };

      try{
        const oldBlock=this._findRuleBlockByUid(idInfo); if(oldBlock) oldBlock.remove();
        this._els.overlay.querySelectorAll(`.rule.temp[data-pending-id="${_cssEscape(String(idInfo))}"]`).forEach(el=>el.remove());
        this._pendingEdits.delete(String(idInfo));
        await this._hass.callService('chronotask','remove_rule', payload);
      } catch(err){
        console.error('Delete fallito (chronotask.remove_rule):',err);
      } finally {
        btn_delete.disabled=false; btn_delete.textContent=prevText;
      }

      doClose();
      this._scheduleUpdate();
    };
    if(btn_delete) btn_delete.addEventListener('click',(ev)=>{ ev.preventDefault(); ev.stopPropagation(); doDelete(); });

    const btn_save=content.querySelector('#btn_save'); const btn_cancel=content.querySelector('#btn_cancel'); const btn_close=content.querySelector('#btn_close');
    if(btn_save) btn_save.addEventListener('click',(ev)=>{ ev.preventDefault(); ev.stopPropagation(); doSave(); });
    if(btn_cancel) btn_cancel.addEventListener('click',(ev)=>{ ev.preventDefault(); ev.stopPropagation(); doClose(); });
    if(btn_close) btn_close.addEventListener('click',(ev)=>{ ev.preventDefault(); ev.stopPropagation(); doClose(); });

    content.addEventListener('keydown',(ev)=>{ if(ev.key==='Enter' && !ev.shiftKey){ ev.preventDefault(); doSave(); } });

    // Init colore
    const fallback=this._config?.default_color||'#5a8e62';
    const base=(existing?(existing.color||existing.ui_color):(prefill?(prefill.color||prefill.ui_color):this._config?.default_color))||fallback;
    const hex=_toHexFromAny(base,fallback);
    try{ f_color.value=hex; }catch(_){ setTimeout(()=>{ try{ f_color.value=hex; }catch(_){ } },0); }
    f_color.dataset.initialHex=hex;

    // Init icon
    if(existing?.icon) setIconValue(existing.icon);
    else if(prefill?.icon) setIconValue(prefill.icon);

    const eid=getEntityId();
    _renderServiceFields(svc_fields,f_service_sel.value,eid,f_service_sel.value===preSelStart?preDataStart:{});
    _renderServiceFields(svc_fields_end,f_service_sel_end.value,eid,f_service_sel_end.value===preSelEnd?preDataEnd:{});
  }
}

// Editor (unchanged except version and default_color helpers)
class ChronoTaskWeeklyCardEditor extends HTMLElement{
  constructor(){ super(); this._config=undefined; this._dcTimer=null; this._rendered=false; }
  setConfig(config){ const incoming=config||{}; if(!this._config){ this._config=incoming; this._render(); this._rendered=true; return; } this._config=Object.assign({},this._config,incoming); this._applyConfigToUI(); }
  set hass(hass){ this._hass=hass; if(this._formTop) this._formTop.hass=hass; if(this._formBottom){ this._formBottom.hass=hass; this._refreshDomainSelectSchema(); } }
  _emitConfigChanged(debounced=true){ const fire=()=> this.dispatchEvent(new CustomEvent('config-changed',{ detail:{ config:this._config } })); if(!debounced){ if(this._dcTimer){ clearTimeout(this._dcTimer); this._dcTimer=null; } fire(); return;} if(this._dcTimer) clearTimeout(this._dcTimer); this._dcTimer=setTimeout(()=>{ this._dcTimer=null; fire(); },400); }
  _uniqSorted(arr){ return Array.from(new Set((arr||[]).filter(Boolean))).sort(); }
  _allDomains(){ if(!this._hass) return []; const fromStates=Object.keys(this._hass.states||{}).map(eid=> (typeof eid==='string' && eid.includes('.')) ? eid.split('.')[0] : null); const fromServices=Object.keys(this._hass.services||{}); return this._uniqSorted([...(fromStates||[]), ...(fromServices||[])]); }
  _domainOptions(){ return this._allDomains().map(d=>({ value:d, label:d })); }
  _buildBottomSchema(){ const opts=this._domainOptions(); return [ { name:'entity_include_domains', selector:{ select:{ multiple:true, mode:'dropdown', options:opts } }, label:'Includi domini (autocomplete entità)' }, { name:'entity_exclude_domains', selector:{ select:{ multiple:true, mode:'dropdown', options:opts } }, label:'Escludi domini' }, ]; }
  _refreshDomainSelectSchema(){ if(!this._formBottom) return; const cur=this._formBottom.data||{}; const schema=this._buildBottomSchema(); this._formBottom.schema=schema; this._formBottom.data=Object.assign({},cur,this._config||{}); }
  _applyConfigToUI(){ if(this._formTop&&this._formTop.data){ this._formTop.data=Object.assign({},this._formTop.data,this._config);} if(this._formBottom&&this._formBottom.data){ this._formBottom.data=Object.assign({},this._formBottom.data,this._config);} const picker=this.shadowRoot?.querySelector('#apw_default_color'); const txt=this.shadowRoot?.querySelector('#apw_default_color_text'); if(picker||txt){ const hex=_toHexFromAny(this._config?.default_color||'#5a8e62','#5a8e62'); if(picker && picker.value?.toLowerCase()!==hex) picker.value=hex; if(txt && txt.value?.toLowerCase()!==hex) txt.value=hex; } this._refreshDomainSelectSchema(); }
  _render(){
    if(!this.shadowRoot) this.attachShadow({mode:'open'}); const root=this.shadowRoot; root.innerHTML=''; const wrap=document.createElement('div');
    wrap.innerHTML=`<style>.row{margin:8px 0}.row label{display:block;font-size:12px;opacity:.85;margin:0 0 4px}.inline{display:flex;gap:8px;align-items:center}.inline input[type="color"]{width:48px;height:36px;padding:0;border:none;background:transparent}.full{width:100%}</style>`;
    const initialData=Object.assign({ start_hour:'06:00', end_hour:'22:00', slot_minutes:60, default_color:'#5a8e62' }, this._config||{});
    if(!initialData.rules_entity && initialData.entity) initialData.rules_entity=initialData.entity;
    initialData.default_color=_toHexFromAny(initialData.default_color||'#5a8e62','#5a8e62');
    this._config=initialData;

    if(customElements.get('ha-form')){
      const schemaTop=[ { name:'title', selector:{ text:{} }, label:'Titolo', optional:true },
        { name:'rules_entity', selector:{ entity:{ domain:'sensor', include_domains:['sensor'], exclude_domains:['calendar'], integration:'chronotask' } }, label:'Entità (ChronoTask)', optional:true },
        { name:'start_hour', selector:{ time:{ show_seconds:false } }, label:'Ora inizio', optional:true },
        { name:'end_hour', selector:{ time:{ show_seconds:false } }, label:'Ora fine', optional:true },
        { name:'slot_minutes', selector:{ select:{ mode:'dropdown', options:[{value:'15',label:'15 min'},{value:'30',label:'30 min'},{value:'45',label:'45 min'},{value:'60',label:'1 h'}] } }, label:'Intervallo slot', optional:true },
      ];
      const formTop=document.createElement('ha-form');
      formTop.schema=schemaTop; formTop.data=initialData; formTop.hass=this._hass;
      formTop.addEventListener('value-changed',(ev)=>{ ev.stopPropagation(); const detail=ev.detail.value||{}; this._config=Object.assign({},this._config,detail);
        const picker=wrap.querySelector('#apw_default_color'); const txt=wrap.querySelector('#apw_default_color_text');
        if(picker||txt){ const hex=_toHexFromAny(this._config.default_color||'#5a8e62','#5a8e62'); if(picker && picker.value.toLowerCase()!==hex) picker.value=hex; if(txt && txt.value.toLowerCase()!==hex) txt.value=hex; }
        this._emitConfigChanged(true);
      });
      wrap.appendChild(formTop); this._formTop=formTop;

      const colorRow=document.createElement('div');
      colorRow.className='row';
      colorRow.innerHTML=`<label for="apw_default_color">Colore predefinito</label>
        <div class="inline">
          <input id="apw_default_color" type="color" class="full" />
          <input id="apw_default_color_text" type="text" class="full" placeholder="HEX o nome colore (es. red)" style="max-width:220px;border:1px solid var(--divider-color);border-radius:6px;padding:6px 8px;min-height:36px">
        </div>`;
      wrap.appendChild(colorRow);
      const picker=colorRow.querySelector('#apw_default_color'); const txt=colorRow.querySelector('#apw_default_color_text');
      const initHex=_toHexFromAny(this._config.default_color||'#5a8e62','#5a8e62'); picker.value=initHex; txt.value=initHex;
      const updateColor=(raw)=>{ const norm=_toHexFromAny(raw||picker.value||txt.value||'#5a8e62','#5a8e62'); if(picker.value.toLowerCase()!==norm) picker.value=norm; if(txt.value.toLowerCase()!==norm) txt.value=norm;
        this._config=Object.assign({},this._config,{ default_color:norm });
        if(this._formTop&&this._formTop.data){ this._formTop.data=Object.assign({},this._formTop.data,{ default_color:norm }); }
        if(this._formBottom&&this._formBottom.data){ this._formBottom.data=Object.assign({},this._formBottom.data,{ default_color:norm }); }
        this._emitConfigChanged(false);
      };
      picker.addEventListener('change',()=>updateColor(picker.value));
      txt.addEventListener('change',()=>updateColor(txt.value));
      txt.addEventListener('blur',()=>updateColor(txt.value));
      txt.addEventListener('keyup',(e)=>{ if(e.key==='Enter') updateColor(txt.value); });

      const formBottom=document.createElement('ha-form');
      formBottom.schema=this._buildBottomSchema(); formBottom.data=initialData; formBottom.hass=this._hass;
      formBottom.addEventListener('value-changed',(ev)=>{ ev.stopPropagation(); const detail=ev.detail.value||{}; this._config=Object.assign({},this._config,detail); this._emitConfigChanged(true); });
      wrap.appendChild(formBottom); this._formBottom=formBottom;

      wrap.addEventListener('focusout',(e)=>{ const t=e.target; if(!t) return; if(t.tagName==='INPUT' || t.tagName==='HA-TEXTFIELD'){ this._emitConfigChanged(false); } });
      setTimeout(()=> this._refreshDomainSelectSchema(),0);
    } else {
      const mkRow=(label,id,placeholder='',type='text')=>{ const d=document.createElement('div'); d.className='row'; d.innerHTML=`<label for="${id}">${label}</label><input id="${id}" placeholder="${placeholder}" style="width:100%" type="${type}">`; return d; };
      const title=mkRow('Titolo','f_title','Programmazione settimanale (ricorrente)'); wrap.appendChild(title);

      const colorRow=document.createElement('div');
      colorRow.className='row';
      colorRow.innerHTML=`<label for="apw_default_color">Colore predefinito</label>
        <div class="inline">
          <input id="apw_default_color" type="color">
          <input id="apw_default_color_text" type="text" placeholder="HEX o nome colore (es. red)" style="max-width:220px;border:1px solid var(--divider-color);border-radius:6px;padding:6px 8px;">
        </div>`;
      wrap.appendChild(colorRow);
      const picker=colorRow.querySelector('#apw_default_color'); const txt=colorRow.querySelector('#apw_default_color_text');
      const initHex=_toHexFromAny(this._config.default_color||'#5a8e62','#5a8e62'); picker.value=initHex; txt.value=initHex;
      const updateColor=(raw)=>{ const norm=_toHexFromAny(raw||picker.value||txt.value||'#5a8e62','#5a8e62'); if(picker.value.toLowerCase()!==norm) picker.value=norm; if(txt.value.toLowerCase()!==norm) txt.value=norm;
        const cfg=Object.assign({},this._config,{ default_color:norm, title: wrap.querySelector('#f_title')?.value||this._config?.title });
        this._config=cfg; this._emitConfigChanged(false);
      };
      picker.addEventListener('change',()=>updateColor(picker.value));
      txt.addEventListener('change',()=>updateColor(txt.value));
      txt.addEventListener('blur',()=>updateColor(txt.value));
      txt.addEventListener('keyup',(e)=>{ if(e.key==='Enter') updateColor(txt.value); });

      let typingTimer=null;
      const onType=()=>{ if(typingTimer) clearTimeout(typingTimer); typingTimer=setTimeout(()=>{ const cfg=Object.assign({},this._config,{ title: wrap.querySelector('#f_title')?.value||this._config?.title }); this._config=cfg; this._emitConfigChanged(false); },350); };
      wrap.querySelector('#f_title')?.addEventListener('input',onType);
    }
    this.shadowRoot.appendChild(wrap);
  }
}

if(!customElements.get('chronotask-weekly-card')) customElements.define('chronotask-weekly-card', ChronoTaskWeeklyCard);
if(!customElements.get('chronotask-weekly-card-editor')) customElements.define('chronotask-weekly-card-editor', ChronoTaskWeeklyCardEditor);

try{
  window.customCards=window.customCards||[];
  const already=window.customCards.some(c=>c?.type==='chronotask-weekly-card');
  if(!already){
    window.customCards.push({
      type:'chronotask-weekly-card',
      name:'ChronoTask Weekly',
      description:'Planner settimanale ricorrente',
      preview:true,
      documentationURL:'https://github.com/andker87/Home-Assistant-ChronoTask'
    });
  }
}catch(_){}
