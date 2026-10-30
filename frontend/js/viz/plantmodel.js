// Data-driven 3-D plant model.
//
// Nothing about the plant layout lives in this file. The backend sends a scene graph — one node
// per asset with a geometry archetype, a position, dimensions and the twin bindings — and this
// module turns it into meshes. Change the plant in `app/plant3d/model.py`, or import the site's
// own CAD model, and the picture changes with no front-end edit.
//
// The viewer adds the things a plant model needs to be useful rather than decorative: slice by
// level, isolate an area, paint a live KPI onto the geometry as a heat map, click an asset for
// its datasheet and live state, and jump to a saved viewpoint.
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/OrbitControls.js';

const STATUS = {normal: 0x43a047, caution: 0xfb8c00, alarm: 0xe53935, offline: 0x78909c};
const HEAT = [[0.0, 0x1e88e5], [0.25, 0x26c6da], [0.5, 0x66bb6a], [0.72, 0xffb300], [1.0, 0xe53935]];

function heatColour(t) {
  const x = Math.max(0, Math.min(1, t));
  for (let i = 1; i < HEAT.length; i++) {
    if (x <= HEAT[i][0]) {
      const [a, ca] = HEAT[i - 1], [b, cb] = HEAT[i];
      const f = (x - a) / Math.max(b - a, 1e-6);
      return new THREE.Color(ca).lerp(new THREE.Color(cb), f);
    }
  }
  return new THREE.Color(HEAT[HEAT.length - 1][1]);
}

/**
 * @param {HTMLElement} container
 * @param {object} model  payload from GET /plant3d/model
 * @param {object} opts   {dark, onPick, state}
 */
export function mountPlantModel(container, model, opts = {}) {
  const {dark = true, onPick = null} = opts;
  container.innerHTML = '';
  container.classList.add('canvas-wrap');
  container.style.position = 'relative';
  const W = () => container.clientWidth || 900;
  const H = () => container.clientHeight || 620;

  const renderer = new THREE.WebGLRenderer({antialias: true, alpha: true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(W(), H());
  renderer.localClippingEnabled = true;
  container.append(renderer.domElement);

  const tip = Object.assign(document.createElement('div'), {className: 'scene-tip'});
  container.append(tip);

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(dark ? 0x0e1117 : 0xf5f7fa, 180, 520);
  const b = model.bounds;
  const span = Math.max(b.size[0], b.size[2]);
  const camera = new THREE.PerspectiveCamera(45, W() / H(), 0.5, span * 6);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.49;
  controls.minDistance = 12;
  controls.maxDistance = span * 3;

  scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 0.95));
  const sun = new THREE.DirectionalLight(0xffffff, 0.85);
  sun.position.set(b.centre[0] - 60, 140, b.centre[2] + 90);
  scene.add(sun);

  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(b.size[0] * 1.3, b.size[2] * 1.5),
    new THREE.MeshStandardMaterial({color: dark ? 0x151b23 : 0xdfe6ec, roughness: 1}));
  ground.rotation.x = -Math.PI / 2;
  ground.position.set(b.centre[0], -0.02, b.centre[2]);
  scene.add(ground);
  const grid = new THREE.GridHelper(Math.max(b.size[0], b.size[2]) * 1.3,
    Math.round(Math.max(b.size[0], b.size[2]) / 10), 0x2a3542, 0x2a3542);
  grid.position.set(b.centre[0], 0.01, b.centre[2]);
  scene.add(grid);

  const mat = (c, o = {}) => new THREE.MeshStandardMaterial({color: c, metalness: 0.32, roughness: 0.58, ...o});
  const spin = [];      // {mesh, axis, rate}
  const picks = [];
  const nodes = new Map();   // asset_id -> {group, meshes, base, halo, fillMesh, label}
  const labels = [];
  const clip = new THREE.Plane(new THREE.Vector3(0, -1, 0), 1e6);

  // ------------------------------------------------------------------ primitive builders
  function build(n) {
    const d = n.dims || {};
    const c = new THREE.Color(n.colour || '#78909c').getHex();
    const g = new THREE.Group();
    const M = (geom, color = c, o = {}) => new THREE.Mesh(geom, mat(color, {clippingPlanes: [clip], ...o}));
    const push = (m) => { g.add(m); return m; };

    switch (n.primitive) {
      case 'drum': {
        const m = push(M(new THREE.CylinderGeometry(d.diameter_m / 2, d.diameter_m / 2, d.length_m, 28)));
        m.rotation.z = Math.PI / 2;
        m.rotation.x = THREE.MathUtils.degToRad(d.incline_deg || 0);
        spin.push({mesh: m, axis: 'y', rate: 0.9});
        for (const s of [-1, 1]) {
          const t = push(M(new THREE.CylinderGeometry(d.diameter_m * 0.18, d.diameter_m * 0.26, 1.3, 16), 0x90a4ae));
          t.rotation.z = Math.PI / 2;
          t.position.x = s * (d.length_m / 2 + 0.7);
        }
        push(M(new THREE.BoxGeometry(d.length_m * 0.92, 1.0, d.diameter_m * 0.8), 0x455a64))
          .position.y = -d.diameter_m / 2 - 0.5;
        break;
      }
      case 'cone_body': {
        const m = push(M(new THREE.CylinderGeometry(d.diameter_m / 2, d.diameter_m * 0.3, d.height_m, 22)));
        m.position.y = 0;
        push(M(new THREE.CylinderGeometry(d.diameter_m * 0.56, d.diameter_m * 0.56, 0.8, 22), 0x546e7a))
          .position.y = d.height_m / 2 + 0.4;
        break;
      }
      case 'cone_pile': {
        const m = push(M(new THREE.ConeGeometry(d.base_radius_m, d.height_m, 36), c, {roughness: 0.95}));
        m.position.y = d.height_m / 2;
        break;
      }
      case 'hopper': {
        const m = push(M(new THREE.CylinderGeometry(d.top_m / 2, d.bottom_m / 2, d.height_m, 4)));
        m.rotation.y = Math.PI / 4;
        break;
      }
      case 'tank_cone': {
        push(M(new THREE.CylinderGeometry(d.diameter_m / 2, d.diameter_m / 2, d.side_depth_m, 44, 1, true),
          c, {side: THREE.DoubleSide})).position.y = d.side_depth_m / 2;
        const cone = push(M(new THREE.ConeGeometry(d.diameter_m / 2, 2.4, 44), 0x6d4c41));
        cone.rotation.x = Math.PI;
        cone.position.y = -1.0;
        const bridge = push(M(new THREE.BoxGeometry(d.diameter_m, 0.5, 1.2), 0x90a4ae));
        bridge.position.y = d.side_depth_m + 0.4;
        spin.push({mesh: bridge, axis: 'y', rate: 0.18});
        break;
      }
      case 'cylinder':
        push(M(new THREE.CylinderGeometry(d.diameter_m / 2, d.diameter_m / 2, d.height_m, 30)))
          .position.y = d.height_m / 2;
        break;
      case 'inclined_box': {
        const m = push(M(new THREE.BoxGeometry(d.length_m, d.height_m, d.width_m)));
        m.rotation.z = -THREE.MathUtils.degToRad(d.incline_deg || 0);
        for (let i = 1; i < 3; i++) {
          const deck = push(M(new THREE.BoxGeometry(d.length_m * 0.96, 0.08, d.width_m * 0.9), 0x263238));
          deck.rotation.z = m.rotation.z;
          deck.position.y = -d.height_m / 2 + i * (d.height_m / 3);
        }
        spin.push({mesh: m, axis: 'shake', rate: 26});
        break;
      }
      case 'inclined_trough': {
        const m = push(M(new THREE.BoxGeometry(d.length_m, 1.6, d.width_m)));
        m.rotation.z = -THREE.MathUtils.degToRad(d.incline_deg || 0);
        const screw = push(M(new THREE.CylinderGeometry(0.5, 0.5, d.length_m * 0.94, 14), 0x90a4ae));
        screw.rotation.z = Math.PI / 2 - THREE.MathUtils.degToRad(d.incline_deg || 0);
        spin.push({mesh: screw, axis: 'x', rate: 1.6});
        break;
      }
      case 'wedge': {
        push(M(new THREE.BoxGeometry(d.width_m, d.height_m, d.length_m)));
        const jaw = push(M(new THREE.BoxGeometry(d.width_m * 0.7, d.height_m * 0.5, 0.6), 0x37474f));
        jaw.position.set(0, d.height_m * 0.1, d.length_m * 0.3);
        spin.push({mesh: jaw, axis: 'nudge', rate: 10});
        break;
      }
      case 'cell_bank': {
        const n_ = d.n_cells || 4;
        for (let i = 0; i < n_; i++) {
          const cell = push(M(new THREE.BoxGeometry(d.cell_width_m * 0.92, d.height_m, d.cell_length_m * 0.92)));
          cell.position.x = (i - (n_ - 1) / 2) * d.cell_width_m;
          const bed = push(M(new THREE.BoxGeometry(d.cell_width_m * 0.8, 0.3, d.cell_length_m * 0.8),
            0xfff3c4, {roughness: 0.9}));
          bed.position.set(cell.position.x, d.height_m * 0.32, 0);
          spin.push({mesh: bed, axis: 'pulse', rate: 3.2 + i * 0.1});
        }
        break;
      }
      case 'cyclone_ring': {
        const n_ = d.n_units || 6;
        for (let i = 0; i < n_; i++) {
          const a = (i / n_) * Math.PI * 2;
          const body = push(M(new THREE.CylinderGeometry(d.diameter_mm / 2000, d.diameter_mm / 6000,
            d.height_m, 14), 0x1e88e5));
          body.position.set(Math.cos(a) * d.radius_m, 0, Math.sin(a) * d.radius_m);
        }
        push(M(new THREE.CylinderGeometry(d.radius_m * 0.5, d.radius_m * 0.5, 1.0, 20), 0x455a64))
          .position.y = d.height_m / 2 + 0.6;
        break;
      }
      case 'helix_bank': {
        const rows = Math.max(1, Math.round((d.n_starts || 60) / 12));
        for (let r = 0; r < rows; r++) {
          for (let k = 0; k < 6; k++) {
            const col = push(M(new THREE.CylinderGeometry(0.16, 0.16, d.height_m, 8), 0x455a64));
            col.position.set(r * 1.6 - rows * 0.8, d.height_m / 2, k * d.diameter_m * 1.05 - 3 * d.diameter_m);
            const turns = Math.round(d.turns || 5);
            for (let t = 0; t < turns * 6; t++) {
              const f = t / (turns * 6);
              const seg = push(M(new THREE.BoxGeometry(d.diameter_m * 0.42, 0.1, 0.5), 0x0288d1));
              const ang = f * turns * Math.PI * 2;
              seg.position.set(col.position.x + Math.cos(ang) * d.diameter_m * 0.42,
                d.height_m * (1 - f), col.position.z + Math.sin(ang) * d.diameter_m * 0.42);
              seg.rotation.y = -ang;
            }
          }
        }
        break;
      }
      case 'deck_bank': {
        const n_ = d.n_decks || 12;
        const cols = Math.max(1, Math.round(n_ / 4));
        for (let i = 0; i < n_; i++) {
          const r = i % 4, cIdx = Math.floor(i / 4);
          const deck = push(M(new THREE.BoxGeometry(d.deck_length_m, 0.22, d.deck_width_m), c));
          deck.position.set(cIdx * (d.deck_length_m + 0.6) - cols * d.deck_length_m / 2,
            0.9, r * (d.deck_width_m + 0.5) - 2 * d.deck_width_m);
          deck.rotation.z = -0.045;
          spin.push({mesh: deck, axis: 'shake', rate: 18});
          const legs = push(M(new THREE.BoxGeometry(d.deck_length_m * 0.8, 0.9, 0.3), 0x546e7a));
          legs.position.set(deck.position.x, 0.45, deck.position.z);
        }
        break;
      }
      case 'carousel': {
        const n_ = d.n_units || 3;
        for (let i = 0; i < n_; i++) {
          const ring = push(M(new THREE.TorusGeometry(d.diameter_m / 2, 0.42, 10, 34), c));
          ring.rotation.x = Math.PI / 2;
          ring.position.set(i * (d.diameter_m + 1.2) - (n_ - 1) * (d.diameter_m + 1.2) / 2,
            d.height_m * 0.62, 0);
          spin.push({mesh: ring, axis: 'z', rate: 0.6});
          const coil = push(M(new THREE.BoxGeometry(d.diameter_m * 0.3, d.height_m * 0.42, d.diameter_m * 0.9),
            0x37474f));
          coil.position.set(ring.position.x, d.height_m * 0.3, 0);
        }
        break;
      }
      case 'pump_set': {
        const body = push(M(new THREE.CylinderGeometry(d.height_m * 0.42, d.height_m * 0.42, 1.1, 20), 0x607d8b));
        body.rotation.z = Math.PI / 2;
        body.position.y = d.height_m * 0.55;
        const motor = push(M(new THREE.CylinderGeometry(d.height_m * 0.3, d.height_m * 0.3, d.length_m * 0.5, 16),
          0x455a64));
        motor.rotation.z = Math.PI / 2;
        motor.position.set(d.length_m * 0.35, d.height_m * 0.55, 0);
        spin.push({mesh: motor, axis: 'x', rate: 5.0});
        push(M(new THREE.BoxGeometry(d.length_m, 0.35, d.height_m * 0.9), 0x37474f)).position.y = 0.18;
        break;
      }
      case 'belt': {
        const m = push(M(new THREE.BoxGeometry(d.length_m, 0.35, d.width_m), 0x37474f));
        m.rotation.z = -THREE.MathUtils.degToRad(d.incline_deg || 0);
        const cover = push(M(new THREE.BoxGeometry(d.length_m, 0.9, d.width_m + 0.5), c,
          {transparent: true, opacity: 0.4}));
        cover.rotation.z = m.rotation.z;
        cover.position.y = 0.6;
        for (let i = 0; i < Math.max(2, Math.round(d.length_m / 5)); i++) {
          const leg = push(M(new THREE.BoxGeometry(0.3, 3.0, 0.3), 0x546e7a));
          leg.position.set(-d.length_m / 2 + i * 5, -1.6, 0);
        }
        break;
      }
      case 'shell': {
        push(M(new THREE.BoxGeometry(d.length_m, d.height_m, d.width_m), 0x90a4ae,
          {transparent: true, opacity: n.transparent ? 0.09 : 0.85, side: THREE.DoubleSide}))
          .position.y = d.height_m / 2;
        break;
      }
      case 'slab':
        push(M(new THREE.BoxGeometry(d.length_m, d.thickness_m, d.width_m), 0x546e7a,
          {transparent: true, opacity: 0.55})).position.y = 0;
        break;
      default:
        push(M(new THREE.BoxGeometry(3, 3, 3)));
    }
    return g;
  }

  // ------------------------------------------------------------------ assemble
  const baseAtY = new Set(['cone_pile', 'cylinder', 'tank_cone', 'shell', 'pump_set', 'hopper']);
  for (const n of model.nodes) {
    const g = build(n);
    g.position.set(n.position.x, n.position.y, n.position.z);
    g.rotation.y = THREE.MathUtils.degToRad(n.rotation_deg || 0);
    scene.add(g);
    const meshes = [];
    g.traverse(o => {
      if (o.isMesh) {
        o.userData.node = n.node_id;
        meshes.push(o);
        if (n.kind === 'equipment') picks.push(o);
      }
    });
    let halo = null;
    if (n.kind === 'equipment' && n.aabb) {
      const r = Math.max(n.aabb.max[0] - n.aabb.min[0], n.aabb.max[2] - n.aabb.min[2]) / 2 + 0.9;
      halo = new THREE.Mesh(new THREE.RingGeometry(r, r + 0.75, 40),
        new THREE.MeshBasicMaterial({color: STATUS.normal, side: THREE.DoubleSide,
          transparent: true, opacity: 0.0}));
      halo.rotation.x = -Math.PI / 2;
      halo.position.set(n.position.x, (baseAtY.has(n.primitive) ? n.position.y : n.aabb.min[1]) + 0.06,
        n.position.z);
      scene.add(halo);
    }
    let label = null;
    if (n.kind === 'equipment') {
      label = Object.assign(document.createElement('div'),
        {className: 'scene-lbl', textContent: n.tag});
      container.append(label);
      labels.push({el: label, node: n});
    }
    nodes.set(n.node_id, {node: n, group: g, meshes, halo, label,
      baseColours: meshes.map(m => m.material.color.clone())});
  }

  // ------------------------------------------------------------------ routes
  const routeObjs = new Map();
  for (const r of model.routes) {
    const curve = new THREE.CatmullRomCurve3(r.path.map(p => new THREE.Vector3(p[0], p[1], p[2])));
    const tube = new THREE.Mesh(
      new THREE.TubeGeometry(curve, Math.max(8, r.path.length * 6), r.radius_m, 8, false),
      new THREE.MeshStandardMaterial({color: new THREE.Color(r.colour), metalness: 0.3,
        roughness: 0.7, transparent: true, opacity: 0.85, clippingPlanes: [clip]}));
    tube.userData.route = r.route_id;
    scene.add(tube);
    routeObjs.set(r.route_id, tube);
  }

  // ------------------------------------------------------------------ interaction
  const ray = new THREE.Raycaster();
  const ptr = new THREE.Vector2();
  let hovered = null;

  function onMove(ev) {
    const rect = renderer.domElement.getBoundingClientRect();
    ptr.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
    ptr.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
    ray.setFromCamera(ptr, camera);
    const hit = ray.intersectObjects(picks, false)[0];
    const id = hit ? hit.object.userData.node : null;
    hovered = id;
    if (!id) { tip.style.display = 'none'; return; }
    const e = nodes.get(id);
    const s = e.state || {};
    tip.style.display = 'block';
    tip.style.left = `${ev.clientX - rect.left + 14}px`;
    tip.style.top = `${ev.clientY - rect.top + 12}px`;
    tip.innerHTML = `<b>${e.node.tag}</b> ${e.node.name}<br>` +
      `<span class="muted">${e.node.area_name} · ${e.node.level}</span>` +
      (s.throughput_tph != null ? `<br>${s.throughput_tph.toFixed(1)} t/h` : '') +
      (s.power_kw != null ? ` · ${s.power_kw.toFixed(0)} kW` : '') +
      (s.duty_pct != null ? `<br>duty ${s.duty_pct.toFixed(0)} %` : '') +
      (s.status && s.status !== 'normal' ? `<br><b>${s.status.toUpperCase()}</b>` : '');
  }
  function onClick() { if (hovered && onPick) onPick(hovered, nodes.get(hovered).node); }
  renderer.domElement.addEventListener('pointermove', onMove);
  renderer.domElement.addEventListener('click', onClick);

  // ------------------------------------------------------------------ public controls
  const api = {
    applyState(frame) {
      const vals = (frame.assets || []).map(a => a.overlay_value)
        .filter(v => typeof v === 'number');
      const lo = frame.overlay_range ? frame.overlay_range.lo : Math.min(...vals, 0);
      const hi = frame.overlay_range ? frame.overlay_range.hi : Math.max(...vals, 1);
      const useHeat = frame.overlay && frame.overlay !== 'none' && frame.overlay !== 'status';
      for (const a of frame.assets || []) {
        const e = nodes.get(a.asset_id);
        if (!e) continue;
        e.state = a;
        if (e.halo) {
          e.halo.material.color.setHex(STATUS[a.status] || STATUS.normal);
          e.halo.material.opacity = a.status === 'normal' ? 0.0 : 0.9;
        }
        e.meshes.forEach((m, i) => {
          if (useHeat && typeof a.overlay_value === 'number') {
            const t = (a.overlay_value - lo) / Math.max(hi - lo, 1e-6);
            m.material.color.copy(heatColour(t));
          } else if (frame.overlay === 'status' && a.status !== 'normal') {
            m.material.color.setHex(STATUS[a.status]);
          } else {
            m.material.color.copy(e.baseColours[i]);
          }
          m.material.opacity = a.in_service === false ? 0.35 : (m.material.opacity < 0.5 ? m.material.opacity : 1);
          m.material.transparent = m.material.opacity < 1;
        });
        if (e.label) {
          const v = a.overlay_value;
          e.label.textContent = useHeat && typeof v === 'number'
            ? `${e.node.tag}  ${v.toFixed(v > 50 ? 0 : 2)}`
            : e.node.tag;
        }
      }
      for (const r of frame.routes || []) {
        const t = routeObjs.get(r.route_id);
        if (!t) continue;
        t.material.opacity = r.active ? 0.9 : 0.15;
        t.visible = r.active || r.solids_tph == null;
      }
    },
    setLevel(levelId) {
      for (const [, e] of nodes) {
        if (e.node.kind !== 'equipment') continue;
        const on = !levelId || e.node.level === levelId;
        e.group.visible = on;
        if (e.halo) e.halo.visible = on;
        if (e.label) e.label.style.display = on ? '' : 'none';
      }
    },
    setArea(areaId) {
      for (const [, e] of nodes) {
        const on = !areaId || e.node.area === areaId;
        e.group.visible = on;
        if (e.halo) e.halo.visible = on && e.group.visible;
        if (e.label) e.label.style.display = on ? '' : 'none';
      }
    },
    setStructures(show) {
      for (const [, e] of nodes) if (e.node.kind === 'structure') e.group.visible = !!show;
    },
    setLabels(show) {
      for (const l of labels) l.el.dataset.hidden = show ? '' : '1';
    },
    setClipHeight(y) { clip.constant = y == null ? 1e6 : y; },
    goTo(bookmark) {
      camera.position.set(...bookmark.eye);
      controls.target.set(...bookmark.target);
      controls.update();
    },
    focus(assetId) {
      const e = nodes.get(assetId);
      if (!e) return;
      const p = e.node.position;
      const r = e.node.aabb
        ? Math.max(e.node.aabb.max[0] - e.node.aabb.min[0], e.node.aabb.max[2] - e.node.aabb.min[2])
        : 10;
      controls.target.set(p.x, p.y, p.z);
      camera.position.set(p.x - r * 2.2, p.y + r * 1.8, p.z + r * 2.4);
      controls.update();
    },
    snapshot() { return renderer.domElement.toDataURL('image/png'); },
    dispose,
  };
  api.goTo(model.bookmarks[0]);

  // ------------------------------------------------------------------ loop
  let raf = 0, t0 = performance.now(), running = true;
  const tmp = new THREE.Vector3();
  function frame() {
    if (!running) return;
    raf = requestAnimationFrame(frame);
    const t = (performance.now() - t0) / 1000;
    for (const s of spin) {
      if (s.axis === 'shake') s.mesh.position.y += Math.sin(t * s.rate) * 0.004;
      else if (s.axis === 'pulse') s.mesh.scale.y = 1 + 0.22 * Math.sin(t * s.rate);
      else if (s.axis === 'nudge') s.mesh.rotation.x = 0.04 * Math.sin(t * s.rate);
      else s.mesh.rotation[s.axis] += s.rate * 0.012;
    }
    controls.update();
    renderer.render(scene, camera);
    for (const l of labels) {
      if (l.el.dataset.hidden === '1' || l.el.style.display === 'none') { l.el.style.opacity = 0; continue; }
      const n = l.node;
      tmp.set(n.position.x, (n.aabb ? n.aabb.max[1] : n.position.y) + 2.2, n.position.z).project(camera);
      const vis = tmp.z < 1 && Math.abs(tmp.x) < 1.05 && Math.abs(tmp.y) < 1.05;
      l.el.style.opacity = vis ? 0.92 : 0;
      l.el.style.left = `${(tmp.x * 0.5 + 0.5) * W()}px`;
      l.el.style.top = `${(-tmp.y * 0.5 + 0.5) * H()}px`;
    }
  }
  frame();

  const ro = new ResizeObserver(() => {
    if (!container.clientWidth) return;
    camera.aspect = W() / H();
    camera.updateProjectionMatrix();
    renderer.setSize(W(), H());
  });
  ro.observe(container);

  function dispose() {
    running = false;
    cancelAnimationFrame(raf);
    ro.disconnect();
    renderer.domElement.removeEventListener('pointermove', onMove);
    renderer.domElement.removeEventListener('click', onClick);
    controls.dispose();
    scene.traverse(o => {
      if (o.isMesh) { o.geometry.dispose(); (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => m.dispose()); }
    });
    renderer.dispose();
    labels.forEach(l => l.el.remove());
    container.innerHTML = '';
  }

  return api;
}

export {heatColour};
