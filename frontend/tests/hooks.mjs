// ESM resolve hook: map the browser import-map specifiers to the vendored files for Node tests.
export async function resolve(spec, ctx, next) {
  if (spec === 'three') return next(new URL('../vendor/three.module.min.js', import.meta.url).href, ctx);
  if (spec === 'three/addons/OrbitControls.js') return next(new URL('../vendor/OrbitControls.js', import.meta.url).href, ctx);
  return next(spec, ctx);
}
