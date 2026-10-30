// Admin: backend connection, personas, model metadata, tag dictionary, operator log and state reset.
import * as api from '../api/client.js';
import * as S from '../state.js';
import {PAGES, PERSONAS} from '../utils/constants.js';
import {pageHeader} from '../ui/components.js';
import {button, confirmDialog, download, grid, h, note, select, table, tabs, toCSV, toast} from '../ui/dom.js';
import {sectionCard} from './common.js';

export async function render(root, ctx) {
  const pid = ctx.plantId;
  root.append(pageHeader('Admin / configuration', {subtitle: 'Connection, personas, model provenance and the operator log'}));
  const url = h('input', {type: 'text', value: S.get('backendUrl'), style: {minWidth: '320px'}});
  const key = h('input', {type: 'password', value: S.get('apiKey'), placeholder: 'X-API-Key (optional)'});
  const status = h('div', {class: 'subtitle'});

  root.append(tabs([
    {label: '🔌 Backend', render: pane => {
      pane.append(sectionCard('Connection',
        h('div', {class: 'row'}, h('label', {}, 'Backend URL'), url, h('label', {}, 'API key'), key,
          button('💾 Save', () => { S.set('backendUrl', url.value.trim()); S.set('apiKey', key.value.trim());
            api.clearCache(); toast('Saved — reloading data', 'ok'); ctx.go('admin'); }, 'primary'),
          button('🩺 Test', async () => {
            status.textContent = 'Testing…';
            try { const hcheck = await api.get('health'); status.textContent =
              `OK — ${hcheck.service} ${hcheck.version} (${hcheck.env}, historian ${hcheck.historian})`; }
            catch (e) { status.textContent = `Failed: ${e.message}`; }
          })), status,
        note('Mock mode replays payloads captured from a live backend, so the desk stays demonstrable offline. ' +
          'Toggle it in the sidebar.')));
      pane.append(sectionCard('Endpoints in use', table(Object.entries(api.ENDPOINTS || {}).length
        ? Object.entries(api.ENDPOINTS).map(([k, v]) => ({Name: k, Method: v.method, Path: v.path, 'Cache (s)': v.ttl || '—'}))
        : [{Name: '—', Method: '—', Path: '—', 'Cache (s)': '—'}], ['Name', 'Method', 'Path', 'Cache (s)'], {height: 400})));
    }},
    {label: '👤 Personas', render: pane => {
      pane.append(table(Object.entries(PERSONAS).map(([name, p]) => ({Persona: name, Focus: p.focus,
        'Can accept moves': p.canAccept ? 'yes' : 'no', 'Can edit configuration': p.canEditConfig ? 'yes' : 'no'})),
      ['Persona', 'Focus', 'Can accept moves', 'Can edit configuration']));
      pane.append(h('div', {class: 'row'}, h('label', {}, 'Active persona'),
        select(Object.keys(PERSONAS), S.get('persona'), {onchange: v => { S.set('persona', v); toast(`Persona: ${v}`); }})));
      pane.append(sectionCard('Pages', table(PAGES.map(p => ({Page: `${p.icon} ${p.label}`, Route: `#/${p.id}`,
        Purpose: p.desc})), ['Page', 'Route', 'Purpose'])));
    }},
    {label: '📚 Model metadata', render: async pane => {
      const meta = await api.get('metadata');
      pane.append(note(`<b>${meta.name}</b> · version ${meta.model_version} · ${meta.environment}<br>${meta.flowsheet}`));
      pane.append(sectionCard('Unit models', table(meta.unit_models.map(m => ({Unit: m.unit, Model: m.model,
        Reference: m.reference, Inputs: (m.inputs || []).join(', '), Outputs: (m.outputs || []).join(', ')})),
      ['Unit', 'Model', 'Reference', 'Inputs', 'Outputs'], {height: 400})));
      pane.append(grid(2,
        sectionCard('Assumptions', table(meta.assumptions.map(a => ({Assumption: a})), ['Assumption'])),
        sectionCard('Validation plan', table(meta.validation.map(v => ({Check: v.check, Target: v.target, Method: v.method})),
          ['Check', 'Target', 'Method']))));
      pane.append(sectionCard('Soft sensors', table(meta.soft_sensors.map(s => ({Sensor: s.label, Basis: s.basis,
        Unit: s.unit, 'Uncertainty': s.sigma, 'Valid (min)': s.valid_window_min, Drives: s.drives})),
      ['Sensor', 'Basis', 'Unit', {key: 'Uncertainty', num: true, fmt: '.3f'}, {key: 'Valid (min)', num: true}, 'Drives'])));
    }},
    {label: '🏷️ Tag dictionary', render: async pane => {
      const t = await api.get('plant_tags', {plant_id: pid});
      pane.append(table(t.tags.map(x => ({Tag: x.tag, Description: x.label, Area: x.area, Type: x.type, Unit: x.unit,
        'Sample (s)': x.sample_s, 'Noise %': x.noise_pct, Source: x.source})),
      ['Tag', 'Description', 'Area', 'Type', 'Unit', {key: 'Sample (s)', num: true}, {key: 'Noise %', num: true, fmt: '.2f'},
        'Source'], {height: 520}));
      pane.append(button('⤓ CSV', () => download('tag_dictionary.csv', toCSV(t.tags), 'text/csv')));
    }},
    {label: '📝 Operator log', render: pane => {
      const log = S.get('operatorLog') || [];
      pane.append(log.length ? table(log, ['time_utc', 'persona', 'plant', 'action', 'detail', 'outcome'], {height: 460})
        : note('No actions logged in this session.'));
      pane.append(h('div', {class: 'row mt'},
        button('⤓ CSV', () => download('operator_log.csv', toCSV(log), 'text/csv')),
        button('🗑 Clear log', async () => {
          if (await confirmDialog('Clear operator log', '<p>This removes the locally stored action log.</p>',
            {okLabel: 'Clear', danger: true})) { S.set('operatorLog', []); ctx.go('admin'); }
        }, 'danger')));
      pane.append(sectionCard('Session state',
        note('Preferences, scenarios and the log live in this browser only — nothing is sent anywhere.'),
        button('♻ Reset desk state', async () => {
          if (await confirmDialog('Reset the desk', '<p>Plant selection, persona, scenarios and the log are cleared.</p>',
            {okLabel: 'Reset', danger: true})) { S.reset(); location.hash = '#/home'; location.reload(); }
        }, 'danger')));
    }},
  ], 'admin'));
}
