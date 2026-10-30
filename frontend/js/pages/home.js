// Landing page: what the twin is, the plant at a glance and quick links.
import * as api from '../api/client.js';
import {HEADLINE_KPIS, PAGES, PRODUCTS} from '../utils/constants.js';
import {pageHeader} from '../ui/components.js';
import {grid, h, table} from '../ui/dom.js';
import {kpiCardsFromDict, sectionCard} from './common.js';

export async function render(root, ctx) {
  const [plant, meta] = await Promise.all([api.get('plant', {plant_id: ctx.plantId}), api.get('metadata')]);
  let overview = null;
  try { overview = await api.get('overview', {plant_id: ctx.plantId}); } catch { /* backend may be warming */ }
  root.append(pageHeader(`${plant.name}`, {subtitle: plant.description, timestamp: overview && overview.timestamp}));
  if (overview) root.append(kpiCardsFromDict(overview.kpis, HEADLINE_KPIS,
    {targets: {lump_fe_pct: plant.flowsheet.design_lump_fe_pct,
      lump_al2o3_pct: plant.flowsheet.design_lump_al2o3_pct,
      fines_fe_pct: plant.flowsheet.design_fines_fe_pct,
      fe_recovery_pct: plant.flowsheet.design_fe_recovery_pct},
    source: 'measured'}));
  if (overview) root.append(sectionCard('Three products from one ROM stream',
    grid(3, PRODUCTS.map(p => h('div', {class: 'tile', style: {borderLeft: `4px solid ${p.colour}`}},
      h('b', {}, p.label), h('small', {}, p.use),
      table([{Item: 'Rate', Value: overview.kpis[p.tph], Unit: 't/h'},
        {Item: 'Yield', Value: overview.kpis[p.yieldKey], Unit: '%'},
        {Item: 'Fe', Value: overview.kpis[p.fe], Unit: '%'},
        {Item: 'SiO₂', Value: overview.kpis[p.si], Unit: '%'},
        {Item: 'Al₂O₃', Value: overview.kpis[p.al], Unit: '%'}],
      ['Item', {key: 'Value', num: true, fmt: '.2f'}, 'Unit']))))));
  root.append(grid(2,
    sectionCard('Flowsheet', h('p', {}, meta.flowsheet),
      h('p', {class: 'subtitle'}, `Commodity: ${meta.commodity} · product specification: ${plant.product} · ` +
        `nameplate ${plant.nameplate_tph} t/h · commissioned ${plant.commissioned}`),
      h('p', {class: 'subtitle'}, `State representation: ${meta.state_representation.size_classes} size classes × ` +
        `${meta.state_representation.liberation_classes} liberation classes (${meta.state_representation.series} series to ` +
        `${(meta.state_representation.top_size_um / 1000).toFixed(0)} mm). ` +
        `Separating property: ${meta.state_representation.separating_property || 'particle density'}.`)),
    sectionCard('Supervisory layers',
      table([{Layer: 'Digital twin', Contents: `${meta.unit_models.length} first-principles unit models, ` +
          `${meta.counts.constraints} constraints, ${meta.counts.objectives} objectives`},
      {Layer: 'Model predictive control', Contents: `${meta.control.mvs} manipulated variables, ${meta.control.cvs} controlled ` +
          `variables, ${meta.control.formulation}`},
      {Layer: 'Machine learning', Contents: 'Soft sensors, hybrid twin-residual correction, anomaly detection, drift monitoring'},
      {Layer: 'Soft sensors', Contents: meta.soft_sensors.map(s => s.label).join(', ')}], ['Layer', 'Contents']))));
  root.append(sectionCard('Where to go next', grid(3, PAGES.filter(p => p.id !== 'home').map(p =>
    h('a', {class: 'tile link', href: `#/${p.id}`}, h('b', {}, `${p.icon} ${p.label}`), h('small', {}, p.desc))))));
  root.append(sectionCard('Modelling basis', table(meta.unit_models.map(m => ({Unit: m.unit, Model: m.model,
    Reference: m.reference})), ['Unit', 'Model', 'Reference'], {height: 380})));
}
