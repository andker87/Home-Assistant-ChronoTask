import { makeTranslator } from './chronotask-common.js?v=__VERSION__';

const CTBK_VERSION = '__VERSION__';

try {
  console.info(
    `%c chronotask-backup-card %c ${CTBK_VERSION} `,
    'background:#5a4e8e;color:#fff;border-radius:4px 0 0 4px;padding:2px 6px;font-weight:600',
    'background:#efecff;color:#5a4e8e;border-radius:0 4px 4px 0;padding:2px 6px'
  );
} catch (_) {}

// Dizionario inline (come nelle altre card: nessuna risorsa condivisa in più).
// Fallback: inglese. Le voci-funzione ricevono argomenti da _t(key, ...args).
const CTBK_STRINGS = {
  en: {
    title: 'ChronoTask backup',
    hint: 'Download all rules as a file, or load a file exported from this or another Home Assistant.',
    exportBtn: 'Export rules', importBtn: 'Import rules',
    exportDone: (n, f) => `Exported ${n} rules to ${f}.`,
    fileInfo: (n, f, d) => `${f}: ${n} rules${d ? ' (exported ' + d + ')' : ''}.`,
    addBtn: 'Add to existing', replaceBtn: 'Replace all', cancelBtn: 'Cancel',
    confirmReplace: (n) => `Replace ALL current rules with the ${n} rules in the file? This cannot be undone.`,
    result: (i, t, s, r) => `Imported ${i} of ${t} rules` + (r ? `, new id for ${r} (already existed)` : '') + (s ? `, skipped: ${s}.` : '.'),
    skippedList: (l) => `Skipped: ${l}`,
    errFile: 'The file is not a valid JSON.', errTooBig: 'The file is too big (max 2 MB).',
    errNoRules: 'No rules found in the file.',
    errUnavailable: 'Export/import services not found: update ChronoTask and restart Home Assistant.',
    errGeneric: (m) => `Error: ${m}`, working: 'Working…'
  },
  it: {
    title: 'Backup ChronoTask',
    hint: 'Scarica tutte le regole in un file, oppure carica un file esportato da questo o da un altro Home Assistant.',
    exportBtn: 'Esporta regole', importBtn: 'Importa regole',
    exportDone: (n, f) => `Esportate ${n} regole in ${f}.`,
    fileInfo: (n, f, d) => `${f}: ${n} regole${d ? ' (esportato il ' + d + ')' : ''}.`,
    addBtn: 'Aggiungi alle esistenti', replaceBtn: 'Sostituisci tutte', cancelBtn: 'Annulla',
    confirmReplace: (n) => `Sostituire TUTTE le regole attuali con le ${n} del file? L'operazione non si può annullare.`,
    result: (i, t, s, r) => `Importate ${i} regole su ${t}` + (r ? `, nuovo id per ${r} (esistevano già)` : '') + (s ? `, scartate: ${s}.` : '.'),
    skippedList: (l) => `Scartate: ${l}`,
    errFile: 'Il file non è un JSON valido.', errTooBig: 'Il file è troppo grande (max 2 MB).',
    errNoRules: 'Nessuna regola trovata nel file.',
    errUnavailable: 'Servizi di export/import non trovati: aggiorna ChronoTask e riavvia Home Assistant.',
    errGeneric: (m) => `Errore: ${m}`, working: 'Operazione in corso…'
  },
  fr: {
    title: 'Sauvegarde ChronoTask',
    hint: 'Téléchargez toutes les règles dans un fichier, ou chargez un fichier exporté depuis ce Home Assistant ou un autre.',
    exportBtn: 'Exporter les règles', importBtn: 'Importer des règles',
    exportDone: (n, f) => `${n} règles exportées dans ${f}.`,
    fileInfo: (n, f, d) => `${f} : ${n} règles${d ? ' (exporté le ' + d + ')' : ''}.`,
    addBtn: 'Ajouter aux existantes', replaceBtn: 'Tout remplacer', cancelBtn: 'Annuler',
    confirmReplace: (n) => `Remplacer TOUTES les règles actuelles par les ${n} du fichier ? Action irréversible.`,
    result: (i, t, s, r) => `${i} règles importées sur ${t}` + (r ? `, nouvel id pour ${r} (déjà existant)` : '') + (s ? `, ignorées : ${s}.` : '.'),
    skippedList: (l) => `Ignorées : ${l}`,
    errFile: "Le fichier n'est pas un JSON valide.", errTooBig: 'Le fichier est trop volumineux (max 2 Mo).',
    errNoRules: 'Aucune règle trouvée dans le fichier.',
    errUnavailable: "Services d'export/import introuvables : mettez à jour ChronoTask et redémarrez Home Assistant.",
    errGeneric: (m) => `Erreur : ${m}`, working: 'En cours…'
  },
  de: {
    title: 'ChronoTask-Backup',
    hint: 'Alle Regeln als Datei herunterladen oder eine Datei laden, die aus diesem oder einem anderen Home Assistant exportiert wurde.',
    exportBtn: 'Regeln exportieren', importBtn: 'Regeln importieren',
    exportDone: (n, f) => `${n} Regeln nach ${f} exportiert.`,
    fileInfo: (n, f, d) => `${f}: ${n} Regeln${d ? ' (exportiert am ' + d + ')' : ''}.`,
    addBtn: 'Zu vorhandenen hinzufügen', replaceBtn: 'Alle ersetzen', cancelBtn: 'Abbrechen',
    confirmReplace: (n) => `ALLE aktuellen Regeln durch die ${n} Regeln aus der Datei ersetzen? Das lässt sich nicht rückgängig machen.`,
    result: (i, t, s, r) => `${i} von ${t} Regeln importiert` + (r ? `, neue ID für ${r} (bereits vorhanden)` : '') + (s ? `, übersprungen: ${s}.` : '.'),
    skippedList: (l) => `Übersprungen: ${l}`,
    errFile: 'Die Datei ist kein gültiges JSON.', errTooBig: 'Die Datei ist zu groß (max. 2 MB).',
    errNoRules: 'Keine Regeln in der Datei gefunden.',
    errUnavailable: 'Export-/Import-Dienste nicht gefunden: ChronoTask aktualisieren und Home Assistant neu starten.',
    errGeneric: (m) => `Fehler: ${m}`, working: 'Wird ausgeführt…'
  },
  es: {
    title: 'Copia de seguridad de ChronoTask',
    hint: 'Descarga todas las reglas en un archivo, o carga un archivo exportado desde este u otro Home Assistant.',
    exportBtn: 'Exportar reglas', importBtn: 'Importar reglas',
    exportDone: (n, f) => `${n} reglas exportadas a ${f}.`,
    fileInfo: (n, f, d) => `${f}: ${n} reglas${d ? ' (exportado el ' + d + ')' : ''}.`,
    addBtn: 'Añadir a las existentes', replaceBtn: 'Reemplazar todas', cancelBtn: 'Cancelar',
    confirmReplace: (n) => `¿Reemplazar TODAS las reglas actuales por las ${n} del archivo? No se puede deshacer.`,
    result: (i, t, s, r) => `${i} de ${t} reglas importadas` + (r ? `, id nuevo para ${r} (ya existían)` : '') + (s ? `, omitidas: ${s}.` : '.'),
    skippedList: (l) => `Omitidas: ${l}`,
    errFile: 'El archivo no es un JSON válido.', errTooBig: 'El archivo es demasiado grande (máx. 2 MB).',
    errNoRules: 'No se encontraron reglas en el archivo.',
    errUnavailable: 'No se encuentran los servicios de exportación/importación: actualiza ChronoTask y reinicia Home Assistant.',
    errGeneric: (m) => `Error: ${m}`, working: 'En curso…'
  },
  zh: {
    title: 'ChronoTask 备份',
    hint: '将所有规则下载为文件，或载入从本机或其他 Home Assistant 导出的文件。',
    exportBtn: '导出规则', importBtn: '导入规则',
    exportDone: (n, f) => `已将 ${n} 条规则导出到 ${f}。`,
    fileInfo: (n, f, d) => `${f}：${n} 条规则${d ? '（导出于 ' + d + '）' : ''}。`,
    addBtn: '添加到现有规则', replaceBtn: '全部替换', cancelBtn: '取消',
    confirmReplace: (n) => `用文件中的 ${n} 条规则替换当前所有规则？此操作无法撤销。`,
    result: (i, t, s, r) => `已导入 ${i}/${t} 条规则` + (r ? `，${r} 条因 ID 已存在而获得新 ID` : '') + (s ? `，跳过 ${s} 条。` : '。'),
    skippedList: (l) => `已跳过：${l}`,
    errFile: '该文件不是有效的 JSON。', errTooBig: '文件过大（最大 2 MB）。',
    errNoRules: '文件中没有找到规则。',
    errUnavailable: '未找到导出/导入服务：请更新 ChronoTask 并重启 Home Assistant。',
    errGeneric: (m) => `错误：${m}`, working: '处理中…'
  }
};

const { lang: _bkLang, t: _bkT } = makeTranslator(CTBK_STRINGS);

class ChronoTaskBackupCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
    this._hass = null;
    this._pending = null;
    this._busy = false;
    this._status = null;
  }

  static getStubConfig() { return {}; }
  getCardSize() { return 3; }

  setConfig(config) {
    this._config = { ...(config || {}) };
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    const langChanged = this._hass && _bkLang(this._hass) !== _bkLang(hass);
    this._hass = hass;
    if (first || langChanged) this._render();
  }

  _t(key, ...args) {
    return _bkT(this._hass, key, ...args);
  }

  _base() {
    const pid = this._config.planner_id;
    return pid ? { planner_id: pid } : {};
  }

  async _call(service, data) {
    const res = await this._hass.callWS({
      type: 'call_service',
      domain: 'chronotask',
      service,
      service_data: data,
      return_response: true,
    });
    return res?.response;
  }

  _servicesOk() {
    const s = this._hass?.services?.chronotask;
    return !!(s && s.export_rules && s.import_rules);
  }

  _setStatus(text, kind) {
    this._status = text ? { text, kind: kind || 'info' } : null;
    this._renderStatus();
  }

  _render() {
    const root = this.shadowRoot;
    root.innerHTML = `
      <style>
        :host{display:block}
        ha-card{padding:16px}
        h2{margin:0 0 4px;font-size:1.1rem;font-weight:500}
        p{margin:0 0 12px;color:var(--secondary-text-color);font-size:.9rem}
        .row{display:flex;gap:8px;flex-wrap:wrap}
        button{font:inherit;cursor:pointer;border-radius:8px;padding:8px 14px;border:1px solid var(--primary-color);
          background:var(--primary-color);color:var(--text-primary-color,#fff)}
        button.ghost{background:transparent;color:var(--primary-color)}
        button.danger{background:var(--error-color,#db4437);border-color:var(--error-color,#db4437);color:#fff}
        button:disabled{opacity:.5;cursor:default}
        .panel{margin-top:12px;padding:12px;border:1px solid var(--divider-color);border-radius:8px}
        .panel[hidden]{display:none}
        .panel .info{margin-bottom:10px}
        .status{margin-top:12px;font-size:.9rem;white-space:pre-wrap}
        .status.error{color:var(--error-color,#db4437)}
        .status.ok{color:var(--success-color,#43a047)}
      </style>
      <ha-card>
        <h2></h2>
        <p></p>
        <div class="row">
          <button type="button" id="b_export"></button>
          <button type="button" id="b_import" class="ghost"></button>
        </div>
        <input type="file" id="f_file" accept=".json,application/json" hidden>
        <div class="panel" id="panel" hidden>
          <div class="info" id="info"></div>
          <div class="row">
            <button type="button" id="b_add"></button>
            <button type="button" id="b_replace" class="danger"></button>
            <button type="button" id="b_cancel" class="ghost"></button>
          </div>
        </div>
        <div class="status" id="status"></div>
      </ha-card>`;
    const $ = (id) => root.getElementById(id);
    this._els = {
      h2: root.querySelector('h2'), p: root.querySelector('p'),
      bExport: $('b_export'), bImport: $('b_import'), file: $('f_file'),
      panel: $('panel'), info: $('info'),
      bAdd: $('b_add'), bReplace: $('b_replace'), bCancel: $('b_cancel'), status: $('status'),
    };
    this._els.h2.textContent = this._config.title || this._t('title');
    this._els.p.textContent = this._t('hint');
    this._els.bExport.textContent = this._t('exportBtn');
    this._els.bImport.textContent = this._t('importBtn');
    this._els.bAdd.textContent = this._t('addBtn');
    this._els.bReplace.textContent = this._t('replaceBtn');
    this._els.bCancel.textContent = this._t('cancelBtn');

    this._els.bExport.addEventListener('click', () => this._export());
    this._els.bImport.addEventListener('click', () => this._els.file.click());
    this._els.file.addEventListener('change', () => this._onFile(this._els.file.files && this._els.file.files[0]));
    this._els.bAdd.addEventListener('click', () => this._runImport('merge'));
    this._els.bReplace.addEventListener('click', () => this._runImport('replace'));
    this._els.bCancel.addEventListener('click', () => this._clearPending());
    this._renderPanel();
    this._renderStatus();
  }

  _renderStatus() {
    if (!this._els) return;
    const st = this._status;
    this._els.status.textContent = st ? st.text : '';
    this._els.status.className = 'status' + (st && st.kind !== 'info' ? ' ' + st.kind : '');
  }

  _renderPanel() {
    if (!this._els) return;
    const p = this._pending;
    this._els.panel.hidden = !p;
    if (p) this._els.info.textContent = this._t('fileInfo', p.rules.length, p.name, p.date);
    const dis = this._busy;
    [this._els.bExport, this._els.bImport, this._els.bAdd, this._els.bReplace, this._els.bCancel].forEach((b) => { b.disabled = dis; });
  }

  _clearPending() {
    this._pending = null;
    if (this._els && this._els.file) this._els.file.value = '';
    this._renderPanel();
  }

  async _export() {
    if (this._busy) return;
    if (!this._servicesOk()) { this._setStatus(this._t('errUnavailable'), 'error'); return; }
    this._busy = true; this._renderPanel(); this._setStatus(this._t('working'));
    try {
      const doc = await this._call('export_rules', this._base());
      if (!doc || !Array.isArray(doc.rules)) throw new Error('empty response');
      const slug = String(doc.planner_name || 'planner').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'planner';
      const d = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const stamp = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}`;
      const filename = `chronotask-${slug}-${stamp}.json`;
      const blob = new Blob([JSON.stringify(doc, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      this._setStatus(this._t('exportDone', doc.rules.length, filename), 'ok');
    } catch (err) {
      console.error('ChronoTask export error', err);
      this._setStatus(this._t('errGeneric', err?.message || String(err)), 'error');
    } finally {
      this._busy = false; this._renderPanel();
    }
  }

  async _onFile(file) {
    if (!file) return;
    this._setStatus('');
    if (file.size > 2 * 1024 * 1024) { this._setStatus(this._t('errTooBig'), 'error'); this._clearPending(); return; }
    let doc;
    try { doc = JSON.parse(await file.text()); } catch (_) { this._setStatus(this._t('errFile'), 'error'); this._clearPending(); return; }
    const rules = Array.isArray(doc) ? doc : (Array.isArray(doc?.rules) ? doc.rules : null);
    if (!rules || !rules.length) { this._setStatus(this._t('errNoRules'), 'error'); this._clearPending(); return; }
    let date = '';
    try { if (doc && doc.exported_at) date = new Date(doc.exported_at).toLocaleString(this._hass?.language || undefined); } catch (_) {}
    this._pending = { rules, name: file.name, date };
    this._renderPanel();
  }

  async _runImport(mode) {
    if (this._busy || !this._pending) return;
    if (!this._servicesOk()) { this._setStatus(this._t('errUnavailable'), 'error'); return; }
    const total = this._pending.rules.length;
    if (mode === 'replace' && !confirm(this._t('confirmReplace', total))) return;
    this._busy = true; this._renderPanel(); this._setStatus(this._t('working'));
    try {
      const res = await this._call('import_rules', { ...this._base(), rules: this._pending.rules, mode });
      const skipped = Array.isArray(res?.skipped) ? res.skipped : [];
      let msg = this._t('result', res?.imported ?? 0, total, skipped.length, res?.renamed_ids ?? 0);
      if (skipped.length) {
        const names = skipped.slice(0, 5).map((s) => `#${(s.index ?? 0) + 1}${s.title ? ' ' + s.title : ''}`).join(', ');
        msg += '\n' + this._t('skippedList', names + (skipped.length > 5 ? ', …' : ''));
      }
      this._setStatus(msg, 'ok');
      this._pending = null;
      if (this._els && this._els.file) this._els.file.value = '';
    } catch (err) {
      console.error('ChronoTask import error', err);
      this._setStatus(this._t('errGeneric', err?.message || String(err)), 'error');
    } finally {
      this._busy = false; this._renderPanel();
    }
  }
}

if (!customElements.get('chronotask-backup-card')) customElements.define('chronotask-backup-card', ChronoTaskBackupCard);

try {
  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c?.type === 'chronotask-backup-card')) {
    window.customCards.push({
      type: 'chronotask-backup-card',
      name: 'ChronoTask Backup',
      description: 'Export and import all ChronoTask rules as a JSON file.',
      preview: false,
    });
  }
} catch (_) {}
