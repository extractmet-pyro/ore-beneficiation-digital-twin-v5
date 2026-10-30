// Validation and acceptance — the page a client reads before signing.
//
// Four things have to be on the table before a digital twin can be accepted: the criteria, the
// operating conditions they apply over, the scenarios they are demonstrated on, and the
// procedure by which someone signs. This page carries all four, plus the live result of running
// them, plus the report that comes out of it.
import * as api from '../api/client.js';
import {blandAltmanChart, chart, criteriaMarginChart, envelopeChart, parityPlot,
  residualProfileChart, scenarioMatrixChart} from '../charts/plots.js';
import {metric, pageHeader, statusBadge} from '../ui/components.js';
import {button, download, expander, grid, h, kvTable, note, select, table, tabs, toast} from '../ui/dom.js';
import {fmt, humanise} from '../utils/format.js';
import {sectionCard} from './common.js';

const VERDICT_CLASS = {pass: 'ok', marginal: 'warn', fail: 'bad', partial: 'warn',
  incomplete: 'warn', insufficient_data: '', not_evaluated: '', not_discriminating: '',
  not_applicable: ''};

const badge = v => h('span', {class: `badge s-${v === 'pass' ? 'normal' : v === 'fail' ? 'alarm'
  : v === 'marginal' || v === 'partial' || v === 'incomplete' ? 'caution' : 'offline'}`},
String(v).replace(/_/g, ' ').toUpperCase());

export async function render(root, ctx) {
  const pid = ctx.plantId;
  root.append(pageHeader('Validation and acceptance', {
    subtitle: 'Measurable criteria, the envelope they apply over, the scenarios, and the verdict'}));
  root.append(note(
    'Acceptance criteria are agreed and frozen at Gate 0, <b>before</b> the model is built, and ' +
    'every tolerance is set as a multiple of the reference measurement\'s own repeatability — ' +
    'a model cannot be held to a tolerance tighter than the instrument it is graded against. ' +
    'Everything on this page is produced by the twin itself and can be reproduced by re-running ' +
    'the validation endpoint on the same model version and data window.'));

  const [criteria, scenarios, protocol, envelope] = await Promise.all([
    api.get('val_criteria', {}), api.get('val_scenarios', {}),
    api.get('val_protocol', {}), api.get('val_envelope', {plant_id: pid}),
  ]);

  root.append(tabs([
    {label: '✅ Run & verdict', render: p => runTab(p, pid)},
    {label: '📏 Acceptance criteria', render: p => criteriaTab(p, criteria)},
    {label: '📐 Operating envelope', render: p => envelopeTab(p, envelope)},
    {label: '🧪 Scenarios', render: p => scenarioTab(p, scenarios)},
    {label: '🗂️ Procedure & gates', render: p => protocolTab(p, protocol)},
    {label: '📄 Report', render: p => reportTab(p, pid)},
  ]));
}

// ------------------------------------------------------------------------------- run
function runTab(pane, pid) {
  const host = h('div', {}, h('div', {class: 'loading'}, 'Running the validation suite…'));
  pane.append(host);

  api.get('val_run', {plant_id: pid, section: 'all', tests_pass: true}).then(run => {
    const acc = run.accuracy, beh = run.behaviour, fs = run.fail_safe, sys = run.system;
    const gr = run.gate_readiness;
    host.replaceChildren(
      note(`Overall verdict: <b>${String(run.overall_verdict).toUpperCase()}</b>. ` +
        `Factory acceptance (G1): <b>${gr.G1_FAT}</b>. Site acceptance (G2): <b>${gr.G2_SAT}</b>.` +
        (gr.blocking.length ? ` Blocking: ${gr.blocking.join(', ')}.` : ' Nothing blocking.'),
      run.overall_verdict === 'fail' ? 'bad'
        : run.overall_verdict === 'pass' ? 'ok' : 'warn'),

      grid(4,
        metric('Accuracy criteria', `${acc.summary.pass}/${acc.summary.evaluated} pass`),
        metric('Step tests', `${beh.rows.filter(r => r.verdict === 'pass').length}/${beh.rows.length} pass`),
        metric('Fail-safe', String(fs.verdict).toUpperCase()),
        metric('System criteria', `${sys.summary.pass} pass, ${sys.summary.evidence_required} pending`)),

      gr.evidence_outstanding.length
        ? note('<b>Evidence outstanding.</b> These can only be measured on the live installation ' +
          'and are supplied at the site acceptance test rather than assumed here: ' +
          gr.evidence_outstanding.join('; ') + '.', 'warn')
        : null,

      sectionCard('Accuracy against plant data',
        note(`${acc.hours_evaluated} hours evaluated, ${acc.hours_excluded} excluded ` +
          `(${acc.exclusion_pct} %). ${acc.data_source}`),
        chart(criteriaMarginChart(acc.results)),
        table(acc.results.map(r => ({
          KPI: r.kpi, Class: r.class, n: r.n,
          Bias: r.statistics ? r.statistics.bias : null,
          MAE: r.statistics ? r.statistics.mae : null,
          RMSE: r.statistics ? r.statistics.rmse : null,
          'RMSE/σ': r.rmse_in_sigmas,
          'R²': r.statistics ? r.statistics.r2 : null,
          Verdict: r.verdict,
        })),
        ['KPI', 'Class', {key: 'n', num: true}, {key: 'Bias', num: true, fmt: '+.4f'},
          {key: 'MAE', num: true, fmt: '.4f'}, {key: 'RMSE', num: true, fmt: '.4f'},
          {key: 'RMSE/σ', num: true, fmt: '.2f'}, {key: 'R²', num: true, fmt: '.3f'},
          {key: 'Verdict', render: badge}], {height: 420}),
        suppressedPanel(acc.results)),

      sectionCard('Step tests — does it move the right lever the right way?',
        note(beh.method),
        chart(scenarioMatrixChart(beh.rows)),
        ...beh.rows.map(r => expander(
          `${r.scenario_id} — ${r.name} — ${r.verdict.toUpperCase()}`,
          h('div', {},
            note(`Step: <code>${r.step.variable}</code> ${r.step.from} → ${r.step.to}. ` +
              r.rationale),
            table(r.checks.map(c => ({Variable: c.kpi, Expected: c.expected, From: c.from,
              To: c.to, 'Change %': c.change_pct, Verdict: c.verdict})),
            ['Variable', 'Expected', {key: 'From', num: true, fmt: '.4g'},
              {key: 'To', num: true, fmt: '.4g'}, {key: 'Change %', num: true, fmt: '+.3f'},
              {key: 'Verdict', render: badge}]))))),

      sectionCard('Behaviour outside the validated envelope',
        note(fs.statement, fs.verdict === 'pass' ? 'ok' : 'bad'),
        table(fs.checks.map(c => ({Check: c.check, Verdict: c.verdict, Detail: c.detail})),
          ['Check', {key: 'Verdict', render: badge}, 'Detail'])),

      sectionCard('System criteria',
        note(sys.note),
        table(sys.results.map(r => ({Criterion: r.name, Class: r.class, Limit: r.limit,
          Measured: r.value, Verdict: r.verdict, Method: r.method})),
        ['Criterion', 'Class', 'Limit', {key: 'Measured', num: true, fmt: '.4g'},
          {key: 'Verdict', render: badge}, 'Method'], {height: 380})),
    );
  }).catch(e => host.replaceChildren(note(`Validation run failed: ${e.message}`, 'bad')));
}

function suppressedPanel(results) {
  const rows = [];
  results.forEach(r => (r.suppressed_checks || []).forEach(k => rows.push({
    KPI: r.kpi, Measure: k, Status: r.checks[k].verdict,
    Reason: r.checks[k].reason || '',
  })));
  if (!rows.length) return null;
  return expander(`Measures suppressed, and why (${rows.length})`,
    h('div', {},
      note('A correlation measure applied to a variable that barely moves over the test period ' +
        'grades the measurement noise, not the model. Where that happens the measure is reported ' +
        'but is not allowed to decide the verdict, and the reason is recorded here rather than ' +
        'left for someone to discover later.'),
      table(rows, ['KPI', 'Measure', {key: 'Status', render: badge}, 'Reason'], {height: 280})));
}

// ------------------------------------------------------------------------------- criteria
function criteriaTab(pane, c) {
  pane.append(grid(4,
    metric('KPI criteria', c.counts.kpi),
    metric('Class A (contractual)', c.counts.class_a),
    metric('Class B (operational)', c.counts.class_b),
    metric('System criteria', c.counts.system)));

  pane.append(sectionCard('Principles',
    h('ol', {}, ...c.principles.map(p => h('li', {}, p))),
    note(`<b>Amendment.</b> ${c.amendment}`, 'warn')));

  pane.append(sectionCard('Tolerance classes',
    table(Object.entries(c.tolerance_classes).map(([k, v]) => ({Class: k, Name: v.name,
      'Gates acceptance': v.gates_acceptance ? 'yes' : 'no',
      'Tolerance (× measurement σ)': v.sigma_multiple, Definition: v.definition})),
    ['Class', 'Name', 'Gates acceptance', {key: 'Tolerance (× measurement σ)', num: true, fmt: '.1f'},
      'Definition'])));

  pane.append(sectionCard('Per-KPI acceptance criteria',
    note('Read the <b>reference σ</b> column alongside the limits. Every tolerance is a stated ' +
      'multiple of the measurement\'s own repeatability, which is why none of them can be ' +
      'argued down to a number the laboratory could not resolve in the first place.'),
    table(c.kpi_criteria.map(k => ({
      KPI: k.kpi, Label: k.label, Unit: k.unit, Class: k.class,
      'Reference σ': k.reference_sigma, 'Max |bias|': k.limits.max_abs_bias,
      'Max MAE': k.limits.max_mae, 'Max RMSE': k.limits.max_rmse,
      'Max MAPE %': k.limits.max_mape_pct, 'Min R²': k.limits.min_r2,
      'Min coverage %': k.limits.min_coverage_95_pct, 'n min': k.n_min, Window: k.window,
      Basis: k.measurement_basis,
    })),
    ['KPI', 'Label', 'Unit', 'Class', {key: 'Reference σ', num: true, fmt: '.3g'},
      {key: 'Max |bias|', num: true, fmt: '.3g'}, {key: 'Max MAE', num: true, fmt: '.3g'},
      {key: 'Max RMSE', num: true, fmt: '.3g'}, {key: 'Max MAPE %', num: true, fmt: '.3g'},
      {key: 'Min R²', num: true, fmt: '.2f'}, {key: 'Min coverage %', num: true, fmt: '.0f'},
      {key: 'n min', num: true}, 'Window', 'Basis'], {height: 480}),
    h('div', {}, ...c.kpi_criteria.filter(k => k.note).map(k =>
      note(`<b>${k.kpi}.</b> ${k.note}`)))));

  pane.append(sectionCard('System criteria',
    table(c.system_criteria.map(s => ({Criterion: s.name, Class: s.class, Limit: s.limit,
      Method: s.method, Why: s.why || ''})),
    ['Criterion', 'Class', 'Limit', 'Method', 'Why'], {height: 420})));
}

// ------------------------------------------------------------------------------- envelope
function envelopeTab(pane, env) {
  const cur = env.current_point;
  if (cur) {
    pane.append(note(cur.statement, cur.inside_envelope ? 'ok' : 'warn'));
    pane.append(chart(envelopeChart(cur.rows)));
    if (cur.near_edge.length) {
      pane.append(note('Near the edge of the envelope: <b>' + cur.near_edge.join(', ') +
        '</b>. Still covered by the criteria, but worth knowing before a step test is planned.',
      'warn'));
    }
  }
  pane.append(sectionCard('The claimed envelope',
    note('Outside any of these ranges the twin still solves and still answers, but it labels the ' +
      'result as outside the validated envelope, names the variables that are outside, and ' +
      'switches the learned correction off. The accuracy criteria do not apply there, and we do ' +
      'not pretend they do.'),
    table(env.envelope.map(e => ({Variable: e.variable, Label: e.label, Unit: e.unit,
      From: e.lo, To: e.hi, Basis: e.basis,
      Current: cur ? (cur.rows.find(r => r.variable === e.variable) || {}).value : null,
      State: cur ? (cur.rows.find(r => r.variable === e.variable) || {}).state : null})),
    ['Variable', 'Label', 'Unit', {key: 'From', num: true, fmt: '.4g'},
      {key: 'To', num: true, fmt: '.4g'}, {key: 'Current', num: true, fmt: '.4g'},
      'State', 'Basis'], {height: 420})));
}

// ------------------------------------------------------------------------------- scenarios
function scenarioTab(pane, sc) {
  pane.append(grid(5, ...Object.entries(sc.counts).map(([k, v]) =>
    metric(humanise(k), v))));
  pane.append(sectionCard('What each kind of test establishes',
    kvTable(sc.kinds, 'Kind', 'What it proves')));
  pane.append(sectionCard('Scenario catalogue',
    table(sc.scenarios.map(s => ({ID: s.scenario_id, Scenario: s.name, Kind: s.kind,
      Purpose: s.purpose, 'KPIs judged': s.kpis_judged.join(', ') || '—',
      Duration: s.duration, Criteria: s.numerical_criteria})),
    ['ID', 'Scenario', 'Kind', 'Purpose', 'KPIs judged', 'Duration', 'Criteria'], {height: 460})));
  pane.append(sectionCard('Expected behaviour, scenario by scenario',
    ...sc.scenarios.map(s => expander(`${s.scenario_id} — ${s.name}`,
      h('div', {},
        note(`<b>Purpose.</b> ${s.purpose}`),
        note(`<b>Expected.</b> ${s.expected_behaviour}`, s.kind === 'excluded' ? 'warn' : ''),
        s.note ? note(`<b>Note.</b> ${s.note}`) : null,
        kvTable({Setup: JSON.stringify(s.setup), 'Data required': s.data_required,
          Duration: s.duration, 'Numerical criteria': s.numerical_criteria},
        'Item', 'Value'))))));
}

// ------------------------------------------------------------------------------- protocol
function protocolTab(pane, p) {
  pane.append(sectionCard('Principles',
    h('ol', {}, ...p.principles.map(x => h('li', {}, x)))));
  pane.append(sectionCard('Roles', kvTable(p.roles, 'Role', 'Responsibility')));
  pane.append(sectionCard('Gates',
    table(p.gates.map(g => ({Gate: g.gate, Name: g.name, Phase: g.phase, Objective: g.objective,
      Exit: g.exit, Signatories: g.signatories.join(', ')})),
    ['Gate', 'Name', 'Phase', 'Objective', 'Exit', 'Signatories'], {height: 320}),
    ...p.gates.map(g => expander(`${g.gate} — ${g.name}`, h('div', {},
      note(`<b>Objective.</b> ${g.objective}`),
      h('h5', {}, 'Entry'), h('ul', {}, ...g.entry.map(x => h('li', {}, x))),
      h('h5', {}, 'Activities'), h('ol', {}, ...g.activities.map(x => h('li', {}, x))),
      h('h5', {}, 'Evidence produced'), h('ul', {}, ...g.evidence.map(x => h('li', {}, x))),
      note(`<b>Exit.</b> ${g.exit}`, 'ok'),
      note(`<b>If it fails.</b> ${g.on_failure}`, 'warn'))))));
  pane.append(sectionCard('Concessions and exclusions',
    note(`<b>Concessions.</b> ${p.concession_rule}`, 'warn'),
    h('h5', {}, 'Periods excluded from the statistics'),
    h('ul', {}, ...p.exclusion_rules.map(x => h('li', {}, x)))));
}

// ------------------------------------------------------------------------------- report
function reportTab(pane, pid) {
  const gateSel = select(['G1', 'G2', 'G3', 'G4'], 'G1', {
    format: v => ({G1: 'G1 — Factory acceptance', G2: 'G2 — Site acceptance',
      G3: 'G3 — Performance trial', G4: 'G4 — Control acceptance'})[v]});
  const out = h('div', {});
  pane.append(h('div', {class: 'toolbar'},
    h('label', {}, 'Gate', gateSel),
    button('Generate the acceptance test report', async () => {
      out.replaceChildren(h('div', {class: 'loading'}, 'Generating…'));
      try {
        const r = await api.get('val_report', {plant_id: pid, gate: gateSel.value,
          tests_pass: true});
        out.replaceChildren(
          note(`Report generated — ${r.characters.toLocaleString()} characters, overall verdict ` +
            `<b>${String(r.overall_verdict).toUpperCase()}</b>.`, 'ok'),
          button('⤓ Download Markdown', () => {
            download(r.filename, r.markdown, 'text/markdown');
            toast('Report downloaded');
          }),
          h('pre', {class: 'report-md'}, r.markdown));
      } catch (e) {
        out.replaceChildren(note(`Could not generate the report: ${e.message}`, 'bad'));
      }
    })), out);
  pane.append(note(
    'The report is the deliverable of a validation run: every criterion, its limit, its measured ' +
    'value and its verdict, plus the criteria table, the scenario catalogue and the gate ' +
    'procedure, with a signature block. It converts straight to Word or PDF.'));
}
