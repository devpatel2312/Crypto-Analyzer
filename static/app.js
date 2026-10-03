const $ = s => document.querySelector(s);
const S = {asset: null, expiry: null, expiries: [], depth: 5, page: 'chain', mode: 'live', metric: 'vega',
           timeline: [], timer: null, chart: null, liveSeries: [], seq: 0};
const DEPTHS = [5, 10, 15, 20];

const fmt = (v, d = 2) => v == null ? '–' : Number(v).toLocaleString('en-IN', {minimumFractionDigits: d, maximumFractionDigits: d});
const fmtInt = v => v == null ? '–' : Number(v).toLocaleString('en-IN', {maximumFractionDigits: 0});
const sign = v => v > 0 ? 'up' : v < 0 ? 'dn' : '';
const hhmm = ms => new Date(ms).toLocaleTimeString('en-IN', {hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Kolkata'});
const expLabel = e => new Date(Date.UTC(+e.slice(0, 4), +e.slice(4, 6) - 1, +e.slice(6)))
  .toLocaleDateString('en-GB', {day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC'});

async function api(path, params = {}) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== ''));
  const r = await fetch(`/api/${path}?${q}`);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
}
function showError(e) { const el = $('#error'); el.hidden = !e; el.textContent = e ? (e.message || e) : ''; }
function status(t) { $('#status').textContent = t; }

// ---------------------------------------------------------------- setup
async function init() {
  const a = await api('assets');
  $('#mockBadge').hidden = !a.mock;
  $('#assets').innerHTML = a.assets.map(x => `<button data-a="${x.id}">${x.label}</button>`).join('');
  $('#assets').onclick = e => e.target.dataset.a && selectAsset(e.target.dataset.a);
  $('#depth').innerHTML = DEPTHS.map(d => `<option value="${d}" ${d === S.depth ? 'selected' : ''}>${d}</option>`).join('');
  $('#depth').onchange = e => { S.depth = +e.target.value; S.liveSeries = []; refresh(); };
  $('#expiryOptions').onchange = e => {
    if (!e.target.matches('input[type="checkbox"]')) return;
    S.expiries = [...$('#expiryOptions').querySelectorAll('input:checked')].map(input => input.value);
    S.expiry = S.expiries[0] || null;
    S.liveSeries = []; refresh();
  };
  S.crypto = false;
  document.querySelectorAll('.tab').forEach(b => b.onclick = () => setPage(b.dataset.page));
  $('#mode').onclick = e => e.target.dataset.mode && setMode(e.target.dataset.mode);
  $('#metric').onclick = e => { if (e.target.dataset.m) { S.metric = e.target.dataset.m;
    document.querySelectorAll('#metric button').forEach(b => b.classList.toggle('active', b === e.target)); drawChart(); } };
  $('#load').onclick = () => loadHist(true);
  let t; $('#slider').oninput = e => { updSliderLabel(); clearTimeout(t); t = setTimeout(() => loadHist(false), 250); };
  const y = new Date(Date.now() - 864e5); $('#day').value = y.toISOString().slice(0, 10);
  selectAsset(a.assets[0].id);
}

async function selectAsset(id) {
  S.seq++;
  S.asset = id; S.liveSeries = []; S.timeline = [];
  S.crypto = ['BTC', 'ETH'].includes(id);
  $('#mode button[data-mode=hist]').hidden = S.crypto;
  if (S.crypto) { S.mode = 'live'; document.querySelectorAll('#mode button').forEach(b => b.classList.toggle('active', b.dataset.mode === 'live')); $('#histControls').hidden = true; }
  document.querySelectorAll('#assets button').forEach(b => b.classList.toggle('active', b.dataset.a === id));
  try {
    const ex = await api('expiries', {asset: id});
    S.expiries = ex.length ? [ex[0]] : [];
    S.expiry = S.expiries[0] || null;
    $('#expiryOptions').innerHTML = ex.map(e =>
      `<label class="expiry-option"><input type="checkbox" value="${e}" ${e === S.expiry ? 'checked' : ''}><span>${expLabel(e)}</span></label>`
    ).join('');
    showError(null);
  } catch (e) { showError(e); return; }
  refresh();
}
function setPage(p) {
  S.page = p;
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.page === p));
  $('#page-chain').hidden = p !== 'chain'; $('#page-greeks').hidden = p !== 'greeks';
  refresh();
}
function setMode(m) {
  S.mode = m;
  document.querySelectorAll('#mode button').forEach(b => b.classList.toggle('active', b.dataset.mode === m));
  $('#histControls').hidden = m !== 'hist';
  refresh();
}
function updSliderLabel() { const t = S.timeline[+$('#slider').value]; $('#sliderLabel').textContent = t ? hhmm(t) : '--:--'; }

// ---------------------------------------------------------------- data loading
function refresh() {
  clearInterval(S.timer);
  if (!S.expiries.length) {
    S.seq++;
    $('#chainSummary').textContent = '';
    $('#chainResults').innerHTML = '<div class="expiry-empty">Select one or more expiries to view automatically selected ATM and OTM contracts.</div>';
    status('Select at least one expiry');
    return;
  }
  if (S.mode === 'live') { loadLive(); S.timer = setInterval(loadLive, 5000); }
  else { status('Pick a date and press Load'); }
}

async function loadLive() {
  const my = ++S.seq;
  try {
    if (S.page === 'chain') {
      const chains = await Promise.all(S.expiries.map(expiry =>
        api('chain/live', {asset: S.asset, expiry, otm_count: S.depth})));
      if (my !== S.seq) return;
      renderChain(chains, 'Live'); status('Updated ' + new Date().toLocaleTimeString());
    } else {
      const g = await api('greeks/live', {asset: S.asset, expiries: S.expiries.join(','), depth: S.depth});
      if (my !== S.seq) return;
      renderGreeks(g.open, g.current, g.change, 'Live');
      S.liveSeries.push({t: g.current.ts, ...flat(g.change)}); S.liveSeries = S.liveSeries.slice(-500);
      drawChart(); status('Updated ' + new Date().toLocaleTimeString());
    }
    showError(null);
  } catch (e) { showError(e); }
}

async function loadHist(fresh) {
  const day = $('#day').value; if (!day) return;
  const params = {asset: S.asset, expiry: S.expiry, day, depth: S.depth, interval: $('#interval').value};
  if (!fresh && S.timeline.length) params.time = hhmm(S.timeline[+$('#slider').value]);
  status('Loading… first load of a day makes several API calls (rate-limited to 60/min)');
  try {
    const h = await api('historical', params);
    S.timeline = h.timeline; S.histSeries = h.series;
    const sl = $('#slider'); sl.max = h.timeline.length - 1;
    sl.value = h.timeline.indexOf(h.selected.ts); updSliderLabel();
    if (S.page === 'chain') renderChain([{...h.chain, expiry: h.expiry}], 'Historical · ' + h.date);
    else { renderGreeks(h.open, h.selected, h.change, 'Historical · ' + h.date); drawChart(); }
    showError(null); status(`${h.timeline.length} candles`);
  } catch (e) { showError(e); status(''); }
}

// ---------------------------------------------------------------- option chain
function chainSelection(ch) {
  if (ch.selection) return ch.selection;
  const strikes = [...new Set(ch.rows.map(row => row.strike))].sort((a, b) => a - b);
  const atm = strikes.reduce((nearest, strike) =>
    Math.abs(strike - ch.spot) < Math.abs(nearest - ch.spot) ? strike : nearest, strikes[0]);
  const i = strikes.indexOf(atm);
  return {atm, ce_strikes: strikes.slice(i, i + S.depth + 1),
    pe_strikes: strikes.slice(Math.max(0, i - S.depth), i + 1).reverse()};
}

function renderChain(chains, label) {
  const first = chains[0];
  $('#chainSummary').innerHTML = `<div>${label}</div><div>Expiries <b>${chains.map(ch => expLabel(String(ch.expiry))).join(', ')}</b></div>` +
    (first ? `<div>Spot <b>${fmt(first.spot)}</b></div><div>OTM strikes <b>${S.depth} per side</b></div>` : '') +
    (first?.provider ? `<div>Provider <b>${first.provider}</b></div>` : '') +
    (first?.ts ? `<div>As of <b>${hhmm(first.ts)} IST</b></div>` : '');
  $('#chainResults').innerHTML = chains.map(renderExpiryChain).join('');
}

function renderExpiryChain(ch) {
  const selection = chainSelection(ch);
  const ceStrikes = new Set(selection.ce_strikes);
  const peStrikes = new Set(selection.pe_strikes);
  const maxOi = Math.max(1, ...ch.rows.flatMap(r => [r.ce?.oi || 0, r.pe?.oi || 0]));
  const oiCell = (leg, side) => {
    const w = leg?.oi ? Math.round(100 * leg.oi / maxOi) : 0;
    const col = side === 'ce' ? 'rgba(47,191,113,.28)' : 'rgba(239,91,91,.28)';
    return `<td class="oi" style="background-image:linear-gradient(${col},${col});background-size:${w}% 100%">${fmtInt(leg?.oi)}</td>`;
  };
  const cols = l => [
    `<td class="${sign(l?.oi_chg)}">${l?.oi_chg == null ? '–' : fmt(l.oi_chg, 1) + '%'}</td>`,
    `<td>${fmtInt(l?.vol)}</td>`, `<td>${fmt(l?.iv, 1)}</td>`,
    `<td>${fmt(l?.delta, 3)}</td>`, `<td>${fmt(l?.theta, 2)}</td>`, `<td>${fmt(l?.vega, 2)}</td>`,
    `<td><b>${fmt(l?.ltp)}</b></td>`, `<td>${fmt(l?.bid)}</td>`, `<td>${fmt(l?.ask)}</td>`];
  const head = ['OI', 'OI chg', 'Volume', 'IV', 'Delta', 'Theta', 'Vega', 'LTP', 'Bid', 'Ask'];
  let h = `<tr><th colspan="10" style="text-align:center">CALLS (CE)</th><th class="strike">Strike</th><th colspan="10" style="text-align:center">PUTS (PE)</th></tr>
    <tr>${head.map(x => `<th>${x}</th>`).join('')}<th class="strike"></th>${[...head].reverse().map(x => `<th>${x}</th>`).join('')}</tr>`;
  const selected = ch.rows.filter(r => ceStrikes.has(r.strike) || peStrikes.has(r.strike))
    .sort((a, b) => b.strike - a.strike);
  const blank = '<td>–</td>'.repeat(head.length);
  for (const r of selected) {
    const atm = r.strike === selection.atm;
    const ce = ceStrikes.has(r.strike) ? [oiCell(r.ce, 'ce'), ...cols(r.ce)].join('') : blank;
    const pe = peStrikes.has(r.strike) ? [...cols(r.pe)].reverse().join('') + oiCell(r.pe, 'pe') : blank;
    const role = atm ? 'ATM' : 'OTM';
    h += `<tr class="${atm ? 'atm' : ''}">${ce}<td class="strike">${fmt(r.strike, 0)}<span class="strike-kind">${role}</span></td>${pe}</tr>`;
  }
  const table = `<div class="scroll"><table>${h}</table></div>`;
  return `<section class="expiry-panel"><div class="expiry-heading"><h3>${expLabel(String(ch.expiry))}</h3>
    <span>Spot <b>${fmt(ch.spot)}</b></span><span>ATM <b>${fmt(selection.atm, 0)}</b></span>
    <span>CE OTM <b>${selection.ce_otm_strikes?.length ?? selection.ce_strikes.length - 1}</b></span>
    <span>PE OTM <b>${selection.pe_otm_strikes?.length ?? selection.pe_strikes.length - 1}</b></span>
    ${ch.ts ? `<span>As of ${hhmm(ch.ts)} IST</span>` : ''}</div>${table}</section>`;
}

// ---------------------------------------------------------------- greeks tables
function gTable(el, t, isChange) {
  const sums = isChange ? t.sums : t.sums;
  const cell = v => isChange ? `<td class="${sign(v)}">${v > 0 ? '+' : ''}${fmt(v, 3)}</td>` : `<td>${fmt(v, 3)}</td>`;
  const rng = s => isChange ? '' : `<td>${s.strikes_used ? fmt(s.from_strike, 0) + ' → ' + fmt(s.to_strike, 0) : '–'}</td>`;
  el.innerHTML = `<tr><th></th><th>Delta</th><th>Theta</th><th>Vega</th>${isChange ? '' : '<th>Strikes</th>'}</tr>` +
    ['CE', 'PE'].map(s => `<tr><td>${s}</td>${cell(sums[s].delta)}${cell(sums[s].theta)}${cell(sums[s].vega)}${rng(sums[s])}</tr>`).join('');
}
function renderGreeks(open, cur, chg, label) {
  $('#t2title').textContent = label.startsWith('Live') ? 'Current' : 'Selected time';
  gTable($('#t1'), open); gTable($('#t2'), cur); gTable($('#t3'), chg, true);
  $('#t1sub').textContent = `spot ${fmt(open.spot)} · ATM ${fmt(open.atm, 0)}`;
  $('#t2sub').textContent = `spot ${fmt(cur.spot)} · ATM ${fmt(cur.atm, 0)}`;
  const selectedExpiries = S.expiries.map(expLabel).join(', ');
  $('#greekSummary').innerHTML = `<div>${label}</div><div>Expiries <b>${selectedExpiries}</b></div><div>OTM strikes <b>${cur.depth} on each side + ATM</b></div><div>Spot change <b class="${sign(chg.spot_change)}">${chg.spot_change > 0 ? '+' : ''}${fmt(chg.spot_change)}</b></div>` +
    (cur.ts ? `<div>As of <b>${hhmm(cur.ts)} IST</b></div>` : '');
  $('#baselineNote').textContent = open.source === 'first-live-snapshot'
    ? (S.crypto ? 'Crypto opening baseline uses the first live BTC/ETH option snapshot loaded in this browser session.' : '⚠ Opening greeks could not be fetched from historical data, so the first live snapshot seen today is used as the baseline.') : '';
}

// ---------------------------------------------------------------- chart
const flat = c => ({CE_vega: c.sums.CE.vega, PE_vega: c.sums.PE.vega, CE_theta: c.sums.CE.theta,
  PE_theta: c.sums.PE.theta, CE_delta: c.sums.CE.delta, PE_delta: c.sums.PE.delta});
function drawChart() {
  if (typeof Chart === 'undefined') { $('.chartbox').textContent = 'Chart library failed to load (check internet access to cdnjs.cloudflare.com).'; return; }
  const m = S.metric;
  const pts = S.mode === 'live' ? S.liveSeries : (S.histSeries || []).map(p => ({t: p.t,
    CE_vega: p.CE_vega_chg, PE_vega: p.PE_vega_chg, CE_theta: p.CE_theta_chg, PE_theta: p.PE_theta_chg,
    CE_delta: p.CE_delta_chg, PE_delta: p.PE_delta_chg}));
  const data = {labels: pts.map(p => hhmm(p.t)), datasets: [
    {label: `CE ${m}`, data: pts.map(p => p['CE_' + m]), borderColor: '#2fbf71', pointRadius: 0, tension: .2},
    {label: `PE ${m}`, data: pts.map(p => p['PE_' + m]), borderColor: '#ef5b5b', pointRadius: 0, tension: .2}]};
  if (S.chart) { S.chart.data = data; S.chart.update('none'); return; }
  S.chart = new Chart($('#chart'), {type: 'line', data, options: {maintainAspectRatio: false, animation: false,
    interaction: {mode: 'index', intersect: false}, scales: {x: {ticks: {maxTicksLimit: 10}}}}});
}
init();
