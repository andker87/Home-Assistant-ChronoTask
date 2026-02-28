const CTTM_VERSION = 'chronotask-tag-manager v0.1';

try {
  console.info(
    `%c chronotask-tag-manager %c ${CTTM_VERSION} `,
    'background:#0b806a;color:#fff;border-radius:4px 0 0 4px;padding:2px 6px;font-weight:600',
    'background:#e7fff9;color:#0b806a;border-radius:0 4px 4px 0;padding:2px 6px'
  );
} catch (_){}

function _tagsToArray(raw){
  if(!raw) return [];
  if(Array.isArray(raw)) return raw.map(x=>String(x||'').trim().toLowerCase()).filter(Boolean);
  const s=String(raw).trim();
  if(!s) return [];
  return s.split(',').map(t=>t.trim().toLowerCase()).filter(Boolean);
}

function _fmtDay(d){
  const days=['Lun','Mar','Mer','Gio','Ven','Sab','Dom'];
  const n=Number(d);
  return (n>=0 && n<=6) ? days[n] : '';
}

function _uniqSorted(arr){
  return Array.from(new Set((arr||[]).filter(Boolean))).sort((a,b)=>String(a).localeCompare(String(b)));
}

class ChronoTaskTagManagerCard extends HTMLElement {
  static getConfigElement(){ return document.createElement('chronotask-tag-manager-editor'); }
  static getStubConfig(hass){
    let rules_entity;
    let tag='';
    try{
      if(hass?.states){
        rules_entity = Object.keys(hass.states).find(eid=> eid.startsWith('sensor.') && hass.states[eid]?.attributes?.planner_id && Array.isArray(hass.states[eid]?.attributes?.rules));
        if(rules_entity){
          const rules = hass.states[rules_entity]?.attributes?.rules||[];
          const tags=[];
          for(const r of rules){ for(const t of _tagsToArray(r?.tags)) tags.push(t); }
          tag = _uniqSorted(tags)[0] || '';
        }
      }
    }catch(_){}
    return { title:'ChronoTask — Tag Manager', ...(rules_entity?{rules_entity}:{}) , ...(tag?{tag}:{}) };
  }

  constructor(){
    super();
    this._updateScheduled=false;
    this._optimistic=new Map();
  }

  setConfig(config){
    const cfg={...(config||{})};
    if(cfg.entity && !cfg.rules_entity) cfg.rules_entity=cfg.entity;
    if(!cfg.rules_entity) throw new Error('chronotask-tag-manager: serve rules_entity');
    if(!cfg.tag) throw new Error('chronotask-tag-manager: serve tag');
    this._config = Object.assign({ title:'' }, cfg);
    this._config.tag = String(this._config.tag).trim().toLowerCase();
    if(!this.shadowRoot) this.attachShadow({mode:'open'});
    this._render();
  }

  set hass(hass){
    this._hass=hass;
    this._scheduleUpdate();
  }

  getCardSize(){ return 3; }

  _scheduleUpdate(){
    if(this._updateScheduled) return;
    this._updateScheduled=true;
    requestAnimationFrame(()=>{
      this._updateScheduled=false;
      this._update();
    });
  }

  _render(){
    const root=this.shadowRoot;
    root.innerHTML=`
      <style>
        :host{display:block}
        .wrap{padding:8px}
        .hdr{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}
        .left{display:flex;align-items:center;gap:10px;min-width: 0;}
        .title{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
        .actions{display:flex;align-items:center;gap:8px;flex-shrink:0;}
        .chip{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border:1px solid var(--divider-color);border-radius:999px;font-size:12px;opacity:.9; user-select:none}
        .chip-btn{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border:2px solid var(--divider-color);border-radius:999px;font-size:12px;font-weight:600;opacity:.95; user-select:none; cursor:pointer; background:transparent; line-height:20px}
        .chip-btn:focus{outline:none; box-shadow:0 0 0 2px rgba(3,102,214,.25)}
        .chip-btn:hover{filter:brightness(1.03)}
        .chip-btn:active{transform:translateY(1px)}
        .chip-enable{border-color:#0b806a; color:#0b806a}
        .chip-disable{border-color:#ed1c24; color:#ed1c24}
        .btns{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
        .list{display:flex;flex-direction:column;gap:6px}
        .row{display:flex;align-items:center;gap:10px;padding:8px;border:1px solid var(--divider-color);border-radius:10px;background:var(--card-background-color)}
        .row.disabled{opacity:.55}
        .main{flex:1 1 auto;min-width:0}
        .name{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .meta{font-size:12px;opacity:.75;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}
        .tag{font-size:11px;opacity:.85;border:1px solid var(--divider-color);border-radius:999px;padding:1px 8px}
        .empty{opacity:.7;font-size:12px;padding:8px}
        .warn{color:var(--error-color,#b00020); font-size:12px; opacity:.9; padding:6px 0;}
      </style>
      <ha-card>
        <div class="wrap">
          <div class="hdr">
            <div class="left">
              <div class="title" id="title"></div>
              <span class="chip" id="chip"></span>
            </div>
            <div class="actions">
              <button class="chip-btn chip-enable" id="btn_enable" type="button">Abilita</button>
              <button class="chip-btn chip-disable" id="btn_disable" type="button">Disabilita</button>
            </div>
          </div>
          <div class="warn" id="warn" style="display:none"></div>
          <div class="list" id="list"></div>
        </div>
      </ha-card>
    `;

    this._els={
      title: root.getElementById('title'),
      chip: root.getElementById('chip'),
      list: root.getElementById('list'),
      btn_enable: root.getElementById('btn_enable'),
      btn_disable: root.getElementById('btn_disable'),
      warn: root.getElementById('warn'),
    };

    this._els.btn_enable.addEventListener('click', (e)=>{ e.preventDefault(); e.stopPropagation(); this._bulk(true); });
    this._els.btn_disable.addEventListener('click', (e)=>{ e.preventDefault(); e.stopPropagation(); this._bulk(false); });

    this._scheduleUpdate();
  }

  _getState(){
    const eid=this._config?.rules_entity;
    if(!eid || !this._hass?.states?.[eid]) return null;
    return this._hass.states[eid];
  }

  _plannerId(){
    const st=this._getState();
    return this._config.planner_id || st?.attributes?.planner_id;
  }

  _rules(){
    const st=this._getState();
    const rules = (st?.attributes?.rules)||[];
    return Array.isArray(rules) ? rules : [];
  }

  _sortRules(rules){
    return rules.slice().sort((a,b)=>{
      const da=Number(a.day); const db=Number(b.day);
      if(da!==db) return da-db;
      const sa=String(a.start||'').slice(0,5);
      const sb=String(b.start||'').slice(0,5);
      return sa.localeCompare(sb);
    });
  }

  _servicesAvailable(){
    const svc = this._hass?.services?.chronotask;
    return !!(svc && svc.update_rule && svc.enable_tag && svc.disable_tag);
  }

  async _bulk(enable){
    if(!this._hass) return;
    if(!this._servicesAvailable()){
      this._showWarn('Servizi ChronoTask non disponibili. Riavvia Home Assistant e ricarica la pagina.');
      return;
    }
    const pid=this._plannerId();
    const tag=this._config.tag;
    const service = enable ? 'enable_tag' : 'disable_tag';
    const payload = pid ? { planner_id: pid, tag } : { tag };
    try{
      await this._hass.callService('chronotask', service, payload);
    }catch(err){
      console.error('ChronoTask bulk tag error', err);
      this._showWarn('Errore durante il bulk del tag (vedi console).');
    }
  }

  async _toggleRule(rule, enabled){
    if(!this._hass) return;
    if(!this._servicesAvailable()){
      this._showWarn('Servizi ChronoTask non disponibili. Riavvia Home Assistant e ricarica la pagina.');
      return;
    }
    const pid=this._plannerId();
    const rid = rule?.id || rule?.uid;
    if(!rid) return;

    this._optimistic.set(String(rid), !!enabled);
    this._scheduleUpdate();

    const payload = pid ? { planner_id: pid, id: rid, enabled: !!enabled } : { id: rid, enabled: !!enabled };
    try{
      await this._hass.callService('chronotask', 'update_rule', payload);
    }catch(err){
      console.error('ChronoTask toggle rule error', err);
      this._showWarn('Errore durante l\'aggiornamento della regola (vedi console).');
      this._optimistic.delete(String(rid));
      this._scheduleUpdate();
    }
  }

  _showWarn(msg){
    if(!this._els?.warn) return;
    this._els.warn.style.display = msg ? 'block' : 'none';
    this._els.warn.textContent = msg || '';
  }

  _update(){
    if(!this._els || !this._config) return;

    const st=this._getState();
    if(!st){
      this._els.title.textContent = (this._config.title || 'ChronoTask — Tag Manager') + ' — (configura rules_entity)';
      this._els.chip.textContent = `#${this._config.tag}`;
      this._els.list.innerHTML = '';
      const empty=document.createElement('div'); empty.className='empty'; empty.textContent='Entità rules_entity non trovata.';
      this._els.list.appendChild(empty);
      return;
    }

    const tag=this._config.tag;
    this._els.title.textContent = this._config.title || `Tag: ${tag}`;
    this._els.chip.textContent = `#${tag}`;

    if(this._servicesAvailable()) this._showWarn('');

    const rulesAll=this._rules();
    let rules = rulesAll.filter(r=> _tagsToArray(r.tags).includes(tag));
    rules = this._sortRules(rules);

    // clean optimistic when aligned
    for(const r of rulesAll){
      const rid = r?.id || r?.uid;
      if(!rid) continue;
      const key=String(rid);
      if(this._optimistic.has(key)){
        const opt=this._optimistic.get(key);
        const real=(r.enabled !== false);
        if(opt === real) this._optimistic.delete(key);
      }
    }

    const list=this._els.list;
    list.innerHTML='';

    if(!rules.length){
      const empty=document.createElement('div');
      empty.className='empty';
      empty.textContent='Nessuna regola con questo tag.';
      list.appendChild(empty);
      return;
    }

    for(const r of rules){
      const row=document.createElement('div');
      const rid = r?.id || r?.uid || '';
      const key=String(rid);
      const realEnabled = (r.enabled !== false);
      const isEnabled = this._optimistic.has(key) ? this._optimistic.get(key) : realEnabled;

      row.className='row' + (isEnabled ? '' : ' disabled');

      let sw;
      if(customElements.get('ha-switch')){
        sw=document.createElement('ha-switch');
        sw.checked = !!isEnabled;
      }else{
        sw=document.createElement('input');
        sw.type='checkbox';
        sw.checked = !!isEnabled;
      }

      sw.addEventListener('click', (ev)=>{ ev.stopPropagation(); });
      sw.addEventListener('change', (ev)=>{
        ev.stopPropagation();
        const next = (sw.checked !== undefined) ? sw.checked : (!!ev?.target?.checked);
        this._toggleRule(r, next);
      });

      const main=document.createElement('div');
      main.className='main';
      const name=document.createElement('div');
      name.className='name';
      name.textContent = (r.title || r.service || 'Action');
      const meta=document.createElement('div');
      meta.className='meta';
      meta.textContent = `${_fmtDay(r.day)} ${String(r.start||'').slice(0,5)}${r.end?(' → '+String(r.end).slice(0,5)):''} • ${r.service||''}`;

      const tagsWrap=document.createElement('div');
      tagsWrap.className='tags';
      const tags=_tagsToArray(r.tags);
      for(const t of tags){
        const el=document.createElement('span'); el.className='tag'; el.textContent = t;
        tagsWrap.appendChild(el);
      }

      main.appendChild(name);
      main.appendChild(meta);
      if(tags.length) main.appendChild(tagsWrap);

      row.appendChild(sw);
      row.appendChild(main);
      list.appendChild(row);
    }
  }
}

class ChronoTaskTagManagerEditor extends HTMLElement {
  constructor(){
    super();
    this._config={};
    this._rendered=false;
    this._dcTimer=null;
  }

  setConfig(config){
    const incoming=config||{};
    if(!this._rendered){
      this._config={...incoming};
      this._render();
      this._rendered=true;
      this._applyConfigToUI();
      return;
    }
    this._config={...this._config, ...incoming};
    this._applyConfigToUI();
  }

  set hass(hass){
    this._hass=hass;
    if(this._form) this._form.hass=hass;
    this._refreshTagSchema();
  }

  _emitConfigChanged(debounced=true){
    const fire=()=> this.dispatchEvent(new CustomEvent('config-changed',{ detail:{ config:this._config } }));
    if(!debounced){
      if(this._dcTimer){ clearTimeout(this._dcTimer); this._dcTimer=null; }
      fire();
      return;
    }
    if(this._dcTimer) clearTimeout(this._dcTimer);
    this._dcTimer=setTimeout(()=>{ this._dcTimer=null; fire(); },250);
  }

  _render(){
    if(!this.shadowRoot) this.attachShadow({mode:'open'});
    const root=this.shadowRoot;
    root.innerHTML='';

    if(!customElements.get('ha-form')){
      const d=document.createElement('div');
      d.innerHTML='Aggiorna Home Assistant per usare l\'editor avanzato.';
      root.appendChild(d);
      return;
    }

    const wrap=document.createElement('div');
    this._baseSchema=[
      { name:'title', selector:{ text:{} }, label:'Titolo', optional:true },
      { name:'rules_entity', selector:{ entity:{ domain:'sensor', integration:'chronotask' } }, label:'Rules entity (planner)', optional:false },
    ];

    const form=document.createElement('ha-form');
    form.hass=this._hass;
    form.addEventListener('value-changed',(ev)=>{
      ev.stopPropagation();
      const detail=ev.detail.value||{};
      this._config = Object.assign({}, this._config, detail);
      this._emitConfigChanged(true);
      if(detail.rules_entity !== undefined) this._refreshTagSchema();
    });

    wrap.appendChild(form);
    root.appendChild(wrap);
    this._form=form;
    this._refreshTagSchema();
  }

  _applyConfigToUI(){
    if(this._form){
      this._form.data = Object.assign({}, this._form.data||{}, this._config||{});
      this._refreshTagSchema();
    }
  }

  _collectTags(){
    if(!this._hass) return [];
    const eid = this._config.rules_entity || this._config.entity;
    if(!eid || !this._hass.states?.[eid]) return [];
    const rules = this._hass.states[eid]?.attributes?.rules;
    if(!Array.isArray(rules)) return [];
    const tags=[];
    for(const r of rules){
      for(const t of _tagsToArray(r?.tags)) tags.push(t);
    }
    return _uniqSorted(tags);
  }

  _refreshTagSchema(){
    if(!this._form) return;
    const tags = this._collectTags();
    const options = tags.map(t=>({ value:t, label:t }));

    const curData = Object.assign({}, this._form.data||{}, this._config||{});
    const curTag = String(curData.tag||'').trim().toLowerCase();

    let tagOptions = options;
    if(curTag && !tags.includes(curTag)){
      tagOptions = [...options, {value:curTag, label: curTag + ' (custom)'}];
    }

    const tagSchema = {
      name:'tag',
      selector:{ select:{ mode:'dropdown', options: tagOptions } },
      label:'Tag',
      optional:false,
    };

    this._form.schema = [...this._baseSchema, tagSchema];
    this._form.data = curData;
  }
}

if(!customElements.get('chronotask-tag-manager')) customElements.define('chronotask-tag-manager', ChronoTaskTagManagerCard);
if(!customElements.get('chronotask-tag-manager-editor')) customElements.define('chronotask-tag-manager-editor', ChronoTaskTagManagerEditor);

try{
  window.customCards=window.customCards||[];
  const already=window.customCards.some(c=>c?.type==='chronotask-tag-manager');
  if(!already){
    window.customCards.push({
      type:'chronotask-tag-manager',
      name:'ChronoTask Tag Manager',
      description:'Gestione regole per tag (abilita/disabilita)',
      preview:true,
      documentationURL:'https://github.com/andker87/Home-Assistant-ChronoTask'
    });
  }
}catch(_){}
