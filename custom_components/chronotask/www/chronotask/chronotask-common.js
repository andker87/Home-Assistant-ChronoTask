// Funzioni condivise dalle card ChronoTask. Viene importato dalle card con la
// versione nell'URL (?v=...), quindi una cache vecchia non può mescolare
// versioni diverse. Ogni card mantiene il proprio dizionario di testi.

// Tag da qualunque formato (lista o testo separato da virgole) a lista in minuscolo.
export function tagsToArray(raw) {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw.map((x) => String(x || '').trim().toLowerCase()).filter(Boolean);
  const s = String(raw).trim();
  if (!s) return [];
  return s.split(',').map((t) => t.trim().toLowerCase()).filter(Boolean);
}

// Restituisce {lang, t} legati al dizionario della card:
// lang(hass) -> codice lingua disponibile (fallback 'en');
// t(hass, key, ...args) -> testo tradotto; le voci-funzione ricevono args,
// le voci mancanti ricadono sull'inglese e poi sulla chiave stessa.
export function makeTranslator(strings) {
  const lang = (hass) => {
    const raw = String(hass?.locale?.language || hass?.language || navigator.language || 'en').toLowerCase();
    const short = raw.split('-')[0];
    return strings[short] ? short : 'en';
  };
  const t = (hass, key, ...args) => {
    const v = (strings[lang(hass)] || {})[key] ?? strings.en?.[key];
    if (typeof v === 'function') return v(...args);
    return v ?? key;
  };
  return { lang, t };
}
