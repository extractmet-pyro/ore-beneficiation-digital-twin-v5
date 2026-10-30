// Three.js 3-D scene of the gravity + WHIMS ore-beneficiation plant (ES module, OrbitControls):
// crushing, rotary scrubber, lump and fines jigs, screw classifier, cyclones, spiral banks,
// shaking-table floor, WHIMS carousels, thickener and the three product stockpiles.
// Status halos, rotating equipment, bubbling cells, flow pipes, hover tooltips and 2-D labels.
// Returns a dispose() function for page navigation.
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/OrbitControls.js';

const STATUS = {normal: 0x43a047, caution: 0xfb8c00, alarm: 0xe53935, offline: 0x78909c};

export function mountScene(container, state) {
  container.innerHTML = ''; container.classList.add('canvas-wrap'); container.style.position = 'relative';
  const W = () => container.clientWidth || 800, H = () => container.clientHeight || 600;
  const renderer = new THREE.WebGLRenderer({antialias: true, alpha: true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)); renderer.setSize(W(), H()); container.append(renderer.domElement);
  const tip = Object.assign(document.createElement('div'), {className: 'scene-tip'}); container.append(tip);
  const scene = new THREE.Scene(); scene.fog = new THREE.Fog(state.dark ? 0x0e1117 : 0xf5f7fa, 110, 260);
  const camera = new THREE.PerspectiveCamera(45, W() / H(), 0.1, 1000); camera.position.set(-40, 95, 120);
  const controls = new OrbitControls(camera, renderer.domElement); controls.target.set(15, 0, 8); controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.47; controls.minDistance = 25; controls.maxDistance = 280;
  scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 0.9));
  const sun = new THREE.DirectionalLight(0xffffff, 0.9); sun.position.set(30, 60, 40); scene.add(sun);
  const U = Object.fromEntries((state.units || []).map(u => [u.unit_id, u]));
  const pick = [], spinners = [], rakes = [], bubbles = [], labels = [], halos = [];
  const mat = (c, o = {}) => new THREE.MeshStandardMaterial({color: c, metalness: 0.35, roughness: 0.55, ...o});
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(260, 140), mat(state.dark ? 0x151b23 : 0xdfe6ec, {roughness: 1}));
  ground.rotation.x = -Math.PI / 2; ground.position.set(20, 0, 0); scene.add(ground);
  const grid = new THREE.GridHelper(260, 52, 0x2a3542, 0x2a3542); grid.position.set(20, 0.01, 0); scene.add(grid);

  function add(id, g, x, z, r) {
    if (!U[id]) return;
    const st = U[id].status || 'normal';
    const ring = new THREE.Mesh(new THREE.RingGeometry(r, r + 0.8, 48), new THREE.MeshBasicMaterial({color: STATUS[st] || STATUS.normal, side: THREE.DoubleSide, transparent: true, opacity: 0.85}));
    ring.rotation.x = -Math.PI / 2; ring.position.y = 0.05; g.add(ring); if (st !== 'normal') halos.push(ring);
    g.position.set(x, 0, z); scene.add(g);
    g.traverse(o => { if (o.isMesh) { o.userData.unit = id; pick.push(o); } });
    const el = Object.assign(document.createElement('div'), {className: 'scene-lbl', textContent: U[id].label}); container.append(el);
    labels.push({el, g, h: r * 1.2 + 4});
  }
  function drum(d, l, color) {
    const g = new THREE.Group(); const m = new THREE.Mesh(new THREE.CylinderGeometry(d / 2, d / 2, l, 32), mat(color));
    m.rotation.z = Math.PI / 2; m.position.y = d / 2 + 1.2; g.add(m); spinners.push(m);
    for (const s of [-1, 1]) { const t = new THREE.Mesh(new THREE.CylinderGeometry(d * 0.18, d * 0.28, 1.4, 20), mat(0x90a4ae));
      t.rotation.z = Math.PI / 2; t.position.set(s * (l / 2 + 0.7), d / 2 + 1.2, 0); g.add(t); }
    const base = new THREE.Mesh(new THREE.BoxGeometry(l * 0.9, 1.2, d * 0.7), mat(0x455a64)); base.position.y = 0.6; g.add(base); return g;
  }
  function cone(r, h, color) { const g = new THREE.Group(); const m = new THREE.Mesh(new THREE.ConeGeometry(r, h, 24), mat(color)); m.rotation.x = Math.PI; m.position.y = h / 2 + 1; g.add(m); return g; }
  function bank(n, color) {
    const g = new THREE.Group();
    for (let i = 0; i < n; i++) {
      const c = new THREE.Mesh(new THREE.CylinderGeometry(1.6, 1.6, 3.2, 20), mat(color)); c.position.set(i * 3.6, 1.6, 0); g.add(c);
      const fr = new THREE.Mesh(new THREE.CylinderGeometry(1.62, 1.62, 0.35, 20), mat(0xfff3c4, {roughness: 0.9})); fr.position.set(i * 3.6, 3.3, 0); g.add(fr);
      for (let b = 0; b < 5; b++) { const s = new THREE.Mesh(new THREE.SphereGeometry(0.13, 8, 8), mat(0xe0f7fa));
        s.position.set(i * 3.6 + (Math.random() - 0.5) * 2, 3.5 + Math.random(), (Math.random() - 0.5) * 2); s.userData = {base: s.position.y, ph: Math.random() * 6}; g.add(s); bubbles.push(s); }
    }
    return g;
  }
  function thickener(r, color) {
    const g = new THREE.Group();
    const tank = new THREE.Mesh(new THREE.CylinderGeometry(r, r, 2.6, 48, 1, true), mat(0x8d6e63, {side: THREE.DoubleSide})); tank.position.y = 1.3; g.add(tank);
    const wat = new THREE.Mesh(new THREE.CircleGeometry(r * 0.98, 48), mat(color, {transparent: true, opacity: 0.75})); wat.rotation.x = -Math.PI / 2; wat.position.y = 2.4; g.add(wat);
    const rake = new THREE.Mesh(new THREE.BoxGeometry(r * 1.9, 0.25, 0.5), mat(0xffcc80)); rake.position.y = 2.6; g.add(rake); rakes.push(rake);
    const br = new THREE.Mesh(new THREE.BoxGeometry(r, 0.4, 1), mat(0x607d8b)); br.position.set(r / 2, 3.1, 0); g.add(br); return g;
  }
  const box = (w, h, d, c) => { const g = new THREE.Group(); const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(c)); m.position.y = h / 2; g.add(m); return g; };
  const pipe = (pts, color, r = 0.35) => scene.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts.map(p => new THREE.Vector3(...p))), 40, r, 8, false),
    mat(color, {emissive: color, emissiveIntensity: 0.15})));

  function scrubberDrum(len, color) {
    const g = new THREE.Group();
    const body = new THREE.Mesh(new THREE.CylinderGeometry(3.0, 3.0, len, 28), mat(color));
    body.rotation.z = Math.PI / 2;
    body.position.y = 4.0;
    g.add(body);
    spinners.push(body);
    for (const s of [-1, 1]) {
      const tyre = new THREE.Mesh(new THREE.TorusGeometry(3.2, 0.35, 10, 28), mat(0x90a4ae));
      tyre.rotation.y = Math.PI / 2;
      tyre.position.set(s * len * 0.28, 4.0, 0);
      g.add(tyre);
    }
    const base = new THREE.Mesh(new THREE.BoxGeometry(len * 0.95, 1.4, 5.2), mat(0x37474f));
    base.position.y = 0.7;
    g.add(base);
    return g;
  }

  function jigCell(n, color) {
    const g = new THREE.Group();
    for (let i = 0; i < n; i++) {
      const cell = new THREE.Mesh(new THREE.BoxGeometry(4.0, 2.6, 4.0), mat(color));
      cell.position.set(i * 4.6, 2.6, 0);
      g.add(cell);
      const bed = new THREE.Mesh(new THREE.BoxGeometry(3.6, 0.7, 3.6), mat(0x3e2723));
      bed.position.set(i * 4.6, 1.7, 0);
      g.add(bed);
      const hutch = new THREE.Mesh(new THREE.CylinderGeometry(1.9, 1.1, 2.4, 4), mat(0x37474f));
      hutch.position.set(i * 4.6, 0.7, 0);
      g.add(hutch);
      for (let b = 0; b < 3; b++) {
        const s = new THREE.Mesh(new THREE.SphereGeometry(0.16, 8, 8), mat(0x4fc3f7));
        s.position.set(i * 4.6 + (Math.random() - 0.5) * 2.4, 3.6 + Math.random(), (Math.random() - 0.5) * 2.4);
        s.userData = {base: s.position.y, ph: Math.random() * 6};
        g.add(s);
        bubbles.push(s);
      }
    }
    return g;
  }

  function screwClassifier(len, color) {
    const g = new THREE.Group();
    const trough = new THREE.Mesh(new THREE.BoxGeometry(len, 2.4, 4.4), mat(color, {transparent: true, opacity: 0.6}));
    trough.rotation.z = 0.20;
    trough.position.y = 3.0;
    g.add(trough);
    const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.42, len, 14), mat(0xb0bec5));
    shaft.rotation.z = Math.PI / 2 + 0.20;
    shaft.position.y = 3.0;
    g.add(shaft);
    spinners.push(shaft);
    for (let i = 0; i < 9; i++) {
      const fl = new THREE.Mesh(new THREE.TorusGeometry(1.5, 0.16, 8, 22), mat(0xe3f2fd));
      fl.position.set(-len / 2 + 2 + i * (len - 4) / 8, 3.0 + (i - 4) * 0.42, 0);
      fl.rotation.y = Math.PI / 2;
      g.add(fl);
      spinners.push(fl);
    }
    const legs = new THREE.Mesh(new THREE.BoxGeometry(len * 0.8, 1.2, 3.6), mat(0x455a64));
    legs.position.y = 0.6;
    g.add(legs);
    return g;
  }

  function spiralBank(n, color) {
    const g = new THREE.Group();
    for (let j = 0; j < n; j++) {
      const col = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.28, 9.0, 10), mat(0x455a64));
      col.position.set(j * 3.4, 4.5, 0);
      g.add(col);
      for (let i = 0; i < 5; i++) {
        const t = new THREE.Mesh(new THREE.TorusGeometry(1.5, 0.28, 8, 26, Math.PI * 1.85), mat(color));
        t.position.set(j * 3.4, 1.4 + i * 1.7, 0);
        t.rotation.x = Math.PI / 2;
        t.rotation.z = i * 1.1;
        g.add(t);
      }
    }
    return g;
  }

  function tableDeck(n, color) {
    const g = new THREE.Group();
    for (let i = 0; i < n; i++) {
      const row = Math.floor(i / 4), colm = i % 4;
      const deck = new THREE.Mesh(new THREE.BoxGeometry(5.0, 0.35, 3.0), mat(color));
      deck.position.set(colm * 5.6, 1.9, row * 3.6);
      deck.rotation.z = -0.055;
      g.add(deck);
      const drive = new THREE.Mesh(new THREE.BoxGeometry(1.0, 1.0, 1.2), mat(0x37474f));
      drive.position.set(colm * 5.6 - 2.9, 1.7, row * 3.6);
      g.add(drive);
      const leg = new THREE.Mesh(new THREE.BoxGeometry(4.4, 1.6, 2.4), mat(0x455a64));
      leg.position.set(colm * 5.6, 0.8, row * 3.6);
      g.add(leg);
    }
    return g;
  }

  function whimsCarousel(n, color) {
    const g = new THREE.Group();
    for (let i = 0; i < n; i++) {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(2.6, 0.75, 12, 30), mat(color, {metalness: 0.6}));
      ring.position.set(i * 7.0, 3.4, 0);
      g.add(ring);
      spinners.push(ring);
      const coil = new THREE.Mesh(new THREE.TorusGeometry(3.5, 0.34, 10, 30),
                                  mat(0xffe082, {emissive: 0xffc107, emissiveIntensity: 0.3}));
      coil.position.set(i * 7.0, 3.4, 0);
      coil.rotation.x = Math.PI / 2;
      g.add(coil);
      const base = new THREE.Mesh(new THREE.BoxGeometry(5.0, 1.2, 5.0), mat(0x37474f));
      base.position.set(i * 7.0, 0.6, 0);
      g.add(base);
    }
    return g;
  }

  function stockpile(r, h, color) {
    const g = new THREE.Group();
    const cone = new THREE.Mesh(new THREE.ConeGeometry(r, h, 26), mat(color));
    cone.position.y = h / 2;
    g.add(cone);
    return g;
  }

  // ---- layout (x runs along the process, z separates the parallel circuits) ---------------------
  add('primary_crusher', cone(3.4, 5.4, 0x6d4c41), -92, -10, 4.6);
  add('sizing_screen', box(7.0, 1.2, 4.4, 0x455a64), -74, -10, 4.4);
  add('secondary_crusher', cone(2.8, 4.4, 0x6d4c41), -74, 4, 3.6);
  add('scrubber', scrubberDrum(16.0, 0x00897b), -50, -10, 9.5);
  add('scrubber_trommel', box(6.0, 1.2, 4.0, 0x455a64), -32, -10, 4.0);
  add('lump_jig', jigCell(4, 0x5c6bc0), -14, -22, 11);
  add('tertiary_crusher', cone(2.6, 4.2, 0x6d4c41), 10, -30, 3.6);
  add('spiral_classifier', screwClassifier(18.0, 0x1e88e5), -14, 6, 10.5);
  add('fines_screen', box(6.0, 1.2, 4.0, 0x455a64), 6, 6, 4.0);
  add('fines_jig', jigCell(4, 0x3949ab), 18, 6, 11);
  const cy = new THREE.Group();
  for (let i = 0; i < 9; i++) {
    const a = i / 9 * Math.PI * 2;
    const cc = new THREE.Mesh(new THREE.ConeGeometry(0.62, 3.4, 16), mat(0x0288d1));
    cc.rotation.x = Math.PI;
    cc.position.set(Math.cos(a) * 2.5, 8.2, Math.sin(a) * 2.5);
    cy.add(cc);
  }
  const stack = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.55, 7.2, 12), mat(0x455a64));
  stack.position.y = 3.6;
  cy.add(stack);
  add('spiral_cyclone', cy, 44, 6, 4.4);
  add('spirals', spiralBank(6, 0x0288d1), 58, 6, 11);
  add('shaking_tables', tableDeck(12, 0xf9a825), 58, 28, 12);
  add('deslime_cyclone', cy.clone(), 6, 40, 4.4);
  add('whims', whimsCarousel(3, 0xc62828), 24, 40, 9);
  add('tails_thickener', thickener(11, 0x8d6e63), 92, 34, 12);
  add('water_recovery', box(6.5, 6.0, 6.5, 0x0288d1), 92, 12, 4.8);

  const romPile = stockpile(8, 7, 0x8d6e63);
  romPile.position.set(-112, 0, -10);
  scene.add(romPile);
  const lumpPile = stockpile(6.5, 6, 0x6d4c41);
  lumpPile.position.set(6, 0, -22);
  scene.add(lumpPile);
  const finesPile = stockpile(6.5, 5.5, 0xf9a825);
  finesPile.position.set(84, 0, 20);
  scene.add(finesPile);
  const pelletPile = stockpile(4.5, 4, 0xc62828);
  pelletPile.position.set(42, 0, 40);
  scene.add(pelletPile);
  const tsf = new THREE.Mesh(new THREE.CircleGeometry(15, 44), mat(0x4fc3f7, {transparent: true, opacity: 0.5}));
  tsf.rotation.x = -Math.PI / 2;
  tsf.position.set(122, 0.08, 56);
  scene.add(tsf);
  const dam = new THREE.Mesh(new THREE.TorusGeometry(15, 1.1, 8, 44), mat(0xa1887f));
  dam.rotation.x = Math.PI / 2;
  dam.position.set(122, 0.6, 56);
  scene.add(dam);

  pipe([[-112, 6, -10], [-100, 6, -10], [-96, 5, -10]], 0xbcaaa4);
  pipe([[-88, 5, -10], [-80, 5, -10], [-77, 2, -10]], 0xbcaaa4);
  pipe([[-70, 2, -10], [-72, 2, 0], [-74, 4, 3]], 0xbcaaa4, 0.3);
  pipe([[-74, 4, 7], [-66, 5, -4], [-59, 5, -10]], 0xbcaaa4);
  pipe([[-41, 4, -10], [-36, 4, -10], [-34, 2, -10]], 0x90a4ae);
  pipe([[-29, 2, -10], [-22, 3, -16], [-16, 4, -22]], 0xbcaaa4);
  pipe([[-29, 1.6, -10], [-24, 2, -2], [-20, 3, 4]], 0x90a4ae);
  pipe([[4, 4, -22], [6, 4, -22]], 0x5d4037, 0.4);
  pipe([[4, 3, -22], [8, 3, -26], [10, 3, -30]], 0x90a4ae, 0.3);
  pipe([[13, 4, -30], [4, 5, -12], [-10, 4, 4]], 0xbcaaa4, 0.3);
  pipe([[2, 3, 6], [5, 3, 6], [8, 2, 6]], 0x90a4ae);
  pipe([[10, 2, 6], [14, 3, 6], [17, 4, 6]], 0x90a4ae);
  pipe([[9, 2, 8], [28, 2, 8], [42, 6, 6]], 0x90a4ae, 0.3);
  pipe([[36, 3, 6], [48, 3, 6], [56, 5, 6]], 0x90a4ae);
  pipe([[62, 3, 10], [60, 3, 20], [58, 2, 26]], 0x90a4ae, 0.3);
  pipe([[70, 3, 6], [78, 3, 14], [83, 3, 19]], 0xf9a825, 0.35);
  pipe([[74, 2.5, 30], [80, 2.5, 24], [83, 3, 20]], 0xf9a825, 0.3);
  pipe([[-16, 4, 12], [-6, 3, 30], [3, 3, 39]], 0x90a4ae, 0.3);
  pipe([[10, 3, 40], [16, 3, 40], [21, 3.4, 40]], 0x90a4ae);
  pipe([[31, 3.4, 40], [37, 3, 40], [40, 3, 40]], 0xc62828, 0.3);
  pipe([[6, 2, 44], [50, 2, 50], [84, 2, 40]], 0xa1887f, 0.4);
  pipe([[70, 2, 30], [82, 2, 33], [86, 2, 34]], 0xa1887f, 0.4);
  pipe([[103, 2, 40], [114, 1.5, 50], [118, 1.4, 54]], 0xa1887f, 0.45);
  pipe([[92, 4, 24], [92, 4, 18], [92, 5, 14]], 0x29b6f6, 0.35);
  pipe([[88, 4, 12], [40, 3, -2], [-40, 4, -8]], 0x29b6f6, 0.35);

  const ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
  renderer.domElement.addEventListener('mousemove', e => {
    const r = renderer.domElement.getBoundingClientRect();
    mouse.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(mouse, camera); const hit = ray.intersectObjects(pick)[0];
    if (hit && U[hit.object.userData.unit]) { const u = U[hit.object.userData.unit];
      tip.style.display = 'block'; tip.style.left = `${e.clientX - r.left + 14}px`; tip.style.top = `${e.clientY - r.top + 10}px`;
      tip.textContent = `${u.label}  [${(u.status || 'normal').toUpperCase()}]\n${u.info || ''}`; } else tip.style.display = 'none';
  });
  const ro = new ResizeObserver(() => { renderer.setSize(W(), H()); camera.aspect = W() / H(); camera.updateProjectionMatrix(); }); ro.observe(container);
  const v = new THREE.Vector3(); let t = 0, alive = true;
  (function loop() {
    if (!alive) return;
    t += 0.016; spinners.forEach(m => { m.rotation.x += 0.03; }); rakes.forEach(m => { m.rotation.y += 0.004; });
    bubbles.forEach(b => { b.position.y = b.userData.base + ((t + b.userData.ph) % 1.4) * 0.8; });
    halos.forEach(r => { r.material.opacity = 0.45 + 0.45 * Math.abs(Math.sin(t * 3)); });
    controls.update();
    labels.forEach(l => { v.copy(l.g.position); v.y += l.h; v.project(camera);
      l.el.style.left = `${(v.x + 1) / 2 * W()}px`; l.el.style.top = `${(1 - v.y) / 2 * H()}px`; l.el.style.display = v.z < 1 ? 'block' : 'none'; });
    renderer.render(scene, camera); requestAnimationFrame(loop);
  })();
  return () => { alive = false; ro.disconnect(); controls.dispose(); renderer.dispose(); scene.traverse(o => { o.geometry && o.geometry.dispose(); }); };
}
