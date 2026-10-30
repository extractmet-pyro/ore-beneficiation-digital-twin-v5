// Plant 3-D model — the geometry of the plant, driven by the live twin.
//
// The scene is built entirely from what the backend sends: equipment, structures, routes, levels
// and the bindings that tie each asset to a twin variable. Three things make it a twin rather
// than a drawing: the colour and fill follow the process, clicking an asset opens its live state
// and datasheet, and the model can be sliced by floor the way maintenance actually thinks.
import * as api from '../api/client.js';
import {chart} from '../charts/plots.js';
import {pageHeader, statusBadge} from '../ui/components.js';
import {button, expander, grid, h, kvTable, note, seg, select, table, tabs, toggle, toast} from '../ui/dom.js';
import {fmt, humanise} from '../utils/format.js';
import {sectionCard} from './common.js';

let viewer = null;

export function dispose() {
  if (viewer) { viewer.dispose(); viewer = null; }
}

export async function render(root, ctx) {
  const pid = ctx.plantId;
  const [model, levels, clash, spec] = await Promise.all([
    api.get('p3d_model', {plant_id: pid}),
    api.get('p3d_levels', {plant_id: pid}),
    api.get('p3d_clash', {plant_id: pid}),
    api.get('p3d_import_spec', {plant_id: pid}),
  ]);

  root.append(pageHeader('Plant 3-D model', {
    subtitle: `${model.counts.equipment} tagged assets · ${model.counts.routes} material routes · ` +
      `${model.counts.bound_to_twin} bound to live twin variables`}));
  root.append(note(
    'This is the geometry of the plant with the twin behind it. Every object carries its plant ' +
    'tag, and the ones the simulator solves also carry live state: colour follows the chosen ' +
    'overlay, the halo follows the constraint status, and clicking an asset opens its datasheet ' +
    'and its current duty. Where a site has its own CAD or scan model, that model replaces this ' +
    'one and the bindings carry across — see the <b>Import</b> tab.'));

  root.append(tabs([
    {label: '🏗️ Model', render: pane => renderModel(pane, pid, model, levels)},
    {label: '📋 Asset register', render: pane => renderRegister(pane, pid, model)},
    {label: '📐 Levels & layout', render: pane => renderLayout(pane, model, levels, clash)},
    {label: '📥 Import site geometry', render: pane => renderImport(pane, spec, model)},
  ]));
}

// ---------------------------------------------------------------------------------- model tab
function renderModel(pane, pid, model, levels) {
  const state = {overlay: 'status', level: '', area: '', structures: true, labels: true, slice: null};
  const canvas = h('div', {class: 'scene3d', style: {height: '620px'}});
  const sidebar = h('div', {class: 'card', style: {minHeight: '620px', overflow: 'auto'}},
    h('h4', {}, 'Select an asset'),
    h('p', {class: 'muted'}, 'Click a piece of equipment in the model.'));
  const legend = h('div', {class: 'note'});

  const overlaySel = select(model.overlays.map(o => o.id), state.overlay, {
    format: v => (model.overlays.find(o => o.id === v) || {}).name || v,
    onchange: v => { state.overlay = v; refresh(); }});
  const levelSel = select(['', ...levels.levels.map(l => l.level_id)], state.level, {
    format: v => (v ? `${v} — ${(levels.levels.find(l => l.level_id === v) || {}).name}` : 'All levels'),
    onchange: v => { state.level = v; state.area = ''; viewer.setArea(''); viewer.setLevel(v); }});
  const areaSel = select(['', ...Object.keys(model.areas)], state.area, {
    format: v => (v ? `${v} — ${model.areas[v].name}` : 'All areas'),
    onchange: v => { state.area = v; state.level = ''; viewer.setLevel(''); viewer.setArea(v); }});
  const bookmarkSel = select(model.bookmarks.map(b => b.id), model.bookmarks[0].id, {
    format: v => (model.bookmarks.find(b => b.id === v) || {}).name || v,
    onchange: v => viewer.goTo(model.bookmarks.find(b => b.id === v))});

  const controls = h('div', {class: 'toolbar'},
    h('label', {}, 'Overlay', overlaySel),
    h('label', {}, 'Level', levelSel),
    h('label', {}, 'Area', areaSel),
    h('label', {}, 'View', bookmarkSel),
    toggle('Structures', true, v => viewer.setStructures(v)),
    toggle('Tags', true, v => viewer.setLabels(v)),
    button('Cut away above main floor', () => {
      state.slice = state.slice == null ? 15.0 : null;
      viewer.setClipHeight(state.slice);
      toast(state.slice == null ? 'Full height restored' : 'Clipped at 15.0 m');
    }, 'ghost'),
    button('⤓ PNG', () => {
      const a = document.createElement('a');
      a.href = viewer.snapshot();
      a.download = `plant-model-${pid}.png`;
      a.click();
    }, 'ghost'));

  pane.append(controls, grid(3, h('div', {style: {gridColumn: 'span 2'}}, canvas), sidebar), legend);

  import('../viz/plantmodel.js').then(({mountPlantModel}) => {
    dispose();
    viewer = mountPlantModel(canvas, model, {
      dark: document.documentElement.dataset.theme !== 'light',
      onPick: id => openAsset(sidebar, pid, id),
    });
    refresh();
  }).catch(e => {
    // No WebGL (headless, locked-down browser, remote desktop). The page stays usable: the
    // register, the layout check and the import tabs carry the same information in tables.
    canvas.replaceChildren(note(`3-D scene unavailable: ${e.message}. The asset register, ` +
      'levels and import tabs still work.', 'warn'));
    controls.querySelectorAll('button, select, input').forEach(el => { el.disabled = true; });
  });

  async function refresh() {
    const frame = await api.get('p3d_state', {plant_id: pid, overlay: state.overlay});
    if (!viewer) return;
    viewer.applyState(frame);
    const spec = frame.overlay_spec || {};
    legend.innerHTML = state.overlay === 'status'
      ? 'Halo colour is the constraint status of that asset: green normal, amber caution, red alarm. ' +
        `Currently ${frame.summary.alarms.length} in alarm, ${frame.summary.cautions.length} in caution.`
      : `<b>${spec.name}</b> painted onto the geometry` +
        (frame.overlay_range ? `, ${fmt(frame.overlay_range.lo, '.3g')} to ` +
          `${fmt(frame.overlay_range.hi, '.3g')} ${spec.unit || ''}` : '') +
        ' — blue is low, red is high. Equipment not in service is dimmed.';
  }
}

async function openAsset(sidebar, pid, assetId) {
  sidebar.replaceChildren(h('div', {class: 'loading'}, 'Loading asset…'));
  try {
    const d = await api.get('p3d_asset', {plant_id: pid, asset_id: assetId});
    const a = d.asset, s = d.state;
    sidebar.replaceChildren(
      h('h4', {}, `${a.tag} — ${a.name}`),
      h('p', {class: 'muted'}, `${humanise(a.type)} · ${a.area} · level ${a.level} · ` +
        `criticality ${a.criticality}`),
      h('div', {}, statusBadge(s.status)),
      s.status_from ? note(`Driven by constraint: <b>${s.status_from}</b>`, 'warn') : null,
      h('h5', {}, 'Live'),
      kvTable({
        'Throughput (t/h)': s.throughput_tph, 'Motor power (kW)': s.power_kw,
        'Duty (% of limit)': s.duty_pct, 'Stream Fe (%)': s.fe_pct, 'Solids (%)': s.solids_pct,
      }, 'Measure', 'Value'),
      h('h5', {}, 'Datasheet'),
      kvTable(a.datasheet, 'Item', 'Value'),
      h('h5', {}, 'Connected streams'),
      table(d.streams.map(x => ({Stream: x.stream, Dir: x.direction, 't/h': x.solids_tph,
        '% solids': x.solids_pct, '% Fe': x.fe_pct, '% Al₂O₃': x.al2o3_pct})),
      ['Stream', 'Dir', {key: 't/h', num: true, fmt: ',.1f'},
        {key: '% solids', num: true, fmt: '.1f'}, {key: '% Fe', num: true, fmt: '.2f'},
        {key: '% Al₂O₃', num: true, fmt: '.2f'}], {height: 200}),
      Object.keys(d.unit_result).length
        ? expander('Full unit state from the twin', kvTable(d.unit_result, 'Parameter', 'Value'))
        : null,
      button('Centre the view on this asset', () => viewer && viewer.focus(assetId), 'ghost'),
    );
  } catch (e) {
    sidebar.replaceChildren(note(`Could not load that asset: ${e.message}`, 'bad'));
  }
}

// ---------------------------------------------------------------------------------- register
function renderRegister(pane, pid, model) {
  const eq = model.nodes.filter(n => n.kind === 'equipment');
  pane.append(sectionCard('Tagged asset register',
    note('Every row is a real object in the 3-D model. “Bound” means the asset is tied to a unit ' +
      'the simulator solves, so its appearance follows the process rather than being decorative.'),
    table(eq.map(n => ({
      Tag: n.tag, Asset: n.name, Type: humanise(n.archetype), Area: n.area, Level: n.level,
      'X (m)': n.position.x, 'Y (m)': n.position.y, 'Z (m)': n.position.z,
      Bound: n.unit_key ? 'yes' : '—', Criticality: n.criticality,
      Bindings: n.bindings.length, In: n.streams_in.length, Out: n.streams_out.length,
    })),
    ['Tag', 'Asset', 'Type', 'Area', 'Level', {key: 'X (m)', num: true, fmt: '.1f'},
      {key: 'Y (m)', num: true, fmt: '.1f'}, {key: 'Z (m)', num: true, fmt: '.1f'},
      'Bound', 'Criticality', {key: 'Bindings', num: true}, {key: 'In', num: true},
      {key: 'Out', num: true}], {height: 520})));

  pane.append(sectionCard('Material routes',
    table(model.routes.map(r => ({
      Route: r.stream, From: r.from_asset, To: r.to_asset, Family: r.family,
      'Length (m)': r.length_m, 'Ø (m)': r.radius_m, Pumped: r.pumped ? 'yes' : '—',
    })), ['Route', 'From', 'To', 'Family', {key: 'Length (m)', num: true, fmt: '.1f'},
      {key: 'Ø (m)', num: true, fmt: '.2f'}, 'Pumped'], {height: 360})));
}

// ---------------------------------------------------------------------------------- layout
function renderLayout(pane, model, levels, clash) {
  pane.append(sectionCard('Elevations',
    table(levels.levels.map(l => ({Level: l.level_id, Name: l.name,
      'From (m)': l.elevation_m, 'To (m)': l.to_m, Equipment: l.equipment})),
    ['Level', 'Name', {key: 'From (m)', num: true, fmt: '.1f'},
      {key: 'To (m)', num: true, fmt: '.1f'}, {key: 'Equipment', num: true}])));

  pane.append(sectionCard('Plant extents',
    kvTable({
      'Length, east–west (m)': model.bounds.size[0],
      'Height (m)': model.bounds.size[1],
      'Width, north–south (m)': model.bounds.size[2],
      'Coordinate convention': model.coordinate_note,
      Units: model.units, 'Up axis': model.up_axis,
    }, 'Property', 'Value')));

  pane.append(sectionCard('Clash and clearance check',
    note(clash.clean
      ? `No clashes. ${clash.pairs_tested} asset pairs tested at a ${clash.clearance_m} m ` +
        'clearance envelope.'
      : `<b>${clash.clashes.length} clashes</b> and ${clash.clearance_warnings.length} clearance ` +
        'warnings found.', clash.clean ? 'ok' : 'bad'),
    clash.clashes.length
      ? table(clash.clashes.map(c => ({A: c.a_name, 'Tag A': c.a_tag, B: c.b_name, 'Tag B': c.b_tag,
        'Overlap X': c.overlap_m[0], 'Overlap Y': c.overlap_m[1], 'Overlap Z': c.overlap_m[2]})),
      ['A', 'Tag A', 'B', 'Tag B', {key: 'Overlap X', num: true, fmt: '.2f'},
        {key: 'Overlap Y', num: true, fmt: '.2f'}, {key: 'Overlap Z', num: true, fmt: '.2f'}])
      : null,
    note(clash.method)));
}

// ---------------------------------------------------------------------------------- import
function renderImport(pane, spec, model) {
  pane.append(note(spec.answer, 'ok'));

  pane.append(sectionCard('Formats we can take',
    table(spec.formats.map(f => ({Format: f.format, Extensions: f.extensions.join(', '),
      Support: f.support, Carries: f.carries, Notes: f.note})),
    ['Format', 'Extensions', 'Support', 'Carries', 'Notes'], {height: 340})));

  pane.append(sectionCard('What the site supplies',
    h('ol', {}, ...spec.requirements.map(r => h('li', {}, r)))));

  pane.append(sectionCard('How an imported model becomes a twin surface',
    h('ol', {}, ...spec.workflow.map(r => h('li', {}, r)))));

  pane.append(sectionCard('Limits, stated plainly',
    note('A 3-D model is not by itself a digital twin. These are the things it will not do.', 'warn'),
    h('ul', {}, ...spec.limits.map(r => h('li', {}, r)))));

  // live tag-matching sandbox
  const box = h('textarea', {rows: 6, class: 'mono', style: {width: '100%'},
    placeholder: 'Paste node or object names from your CAD export, one per line…'},
  ['301-JG-001', 'EQUIP_201-SC-001_DRUM', 'Mesh_0042', '602-MS-001'].join('\n'));
  const out = h('div', {});
  pane.append(sectionCard('Try the tag matcher',
    note('Paste the node names out of your model and see which of them would bind to a plant tag. ' +
      'Nothing is bound on a guess: ambiguous and unmatched nodes are listed for an engineer.'),
    box,
    button('Match against the asset register', async () => {
      out.replaceChildren(h('div', {class: 'loading'}, 'Matching…'));
      try {
        const names = box.value.split('\n').map(s => s.trim()).filter(Boolean);
        const r = await api.post('p3d_match', {node_names: names});
        out.replaceChildren(
          note(`${r.matched.length} matched, ${r.ambiguous.length} ambiguous, ` +
            `${r.unmatched.length} unmatched. Coverage of the register: ` +
            `<b>${r.coverage_pct} %</b>. ${r.ready ? 'Ready to bind.' : 'Not ready to bind.'}`,
          r.ready ? 'ok' : 'warn'),
          r.matched.length ? table(r.matched.map(m => ({Node: m.node, Asset: m.asset_id,
            Tag: m.tag, Name: m.name, Method: m.method, Score: m.score})),
          ['Node', 'Asset', 'Tag', 'Name', 'Method', {key: 'Score', num: true, fmt: '.2f'}]) : null,
          r.unmatched.length ? h('div', {}, h('h5', {}, 'Unmatched — left as inert geometry'),
            table(r.unmatched.map(u => ({Node: u.node, 'Nearest asset': u.best_guess,
              Score: u.score})), ['Node', 'Nearest asset',
              {key: 'Score', num: true, fmt: '.2f'}])) : null);
      } catch (e) {
        out.replaceChildren(note(`Match failed: ${e.message}`, 'bad'));
      }
    }),
    out));

  pane.append(sectionCard('Interchange manifest',
    note(`The twin exports a glTF 2.0-shaped node manifest carrying all ${model.counts.tagged} ` +
      'plant tags, which is what a CAD or BIM package is matched against on the way in and ' +
      'updated against on the way out.'),
    button('Download the manifest', async () => {
      const g = await api.get('p3d_gltf', {});
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([JSON.stringify(g, null, 2)],
        {type: 'application/json'}));
      a.download = 'plant-tag-manifest.gltf.json';
      a.click();
    }, 'ghost')));
}
