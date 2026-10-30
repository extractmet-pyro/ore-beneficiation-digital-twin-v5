"""Size-and-liberation state for the ore-beneficiation twin.

Every stream is described by a **(size class x liberation class)** mass matrix:

* 36 geometric (sqrt 2) size classes from 1.4 um to 250 mm — wide enough to carry run-of-mine
  lumps, jig feed, spiral feed and the ultrafine slimes that report to the desliming cyclones;
* 15 liberation (composition) classes ``g`` = mass fraction of the particle that is iron mineral,
  from free gangue (g = 0) to free iron oxide (g = 1).

For a **gravity and magnetic** plant this state matrix is the whole game. Particle **density**
follows directly from the liberation class — a free hematite grain is 5.15 SG, a free quartz grain
2.65 — so jigs, spirals and tables separate on exactly the axis the matrix tracks, and they do it
with a size-dependent sharpness. Magnetic susceptibility follows the same axis, so the WHIMS works
off the same state. Nothing has to be re-derived from a bulk assay at any point in the circuit.

Two secondary compositions ride along as stream scalars: the goethite share of the iron minerals
and the clay/alumina share of the gangue. The second one matters here more than in a magnetite
plant: ochreous clay is what the rotary scrubber is installed to remove.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# ---- size grid -------------------------------------------------------------------------------
N_CLASSES = 36
TOP_SIZE_UM = 250_000.0            # run-of-mine top size (250 mm)
SIZES_UM: np.ndarray = np.round(TOP_SIZE_UM / (2.0 ** 0.5) ** np.arange(N_CLASSES), 3)
GEO_MEAN_UM: np.ndarray = np.sqrt(SIZES_UM * np.concatenate([SIZES_UM[1:], [SIZES_UM[-1] / 2 ** 0.5]]))

# ---- liberation grid -------------------------------------------------------------------------
N_BINS = 15
#: liberation-class grade: the end members are exactly free gangue (0) and free iron mineral (1)
G: np.ndarray = np.linspace(0.0, 1.0, N_BINS)

# ---- mineral constants -----------------------------------------------------------------------
SG_HEM, SG_GOE, SG_QZ, SG_AL = 5.15, 4.10, 2.65, 2.55
FE_HEM, FE_GOE, FE_AL = 0.6994, 0.6285, 0.020
SIO2_QZ, SIO2_AL = 1.0, 0.45
AL2O3_AL, AL2O3_GOE = 0.39, 0.010
LOI_HEM, LOI_GOE, LOI_AL = 0.005, 0.10, 0.14
SG_WATER = 1.0


def particle_sg(goethite_share: float = 0.12, alumina_share: float = 0.18) -> np.ndarray:
    """Specific gravity of a particle in each liberation class (harmonic mixing by volume).

    This is the separating property for every gravity unit in the plant. With free hematite at
    5.15 and free quartz at 2.65 the concentration criterion (5.15-1)/(2.65-1) = 2.5 says the
    separation is easy down to fine sizes — which is why a jig-spiral-table plant works at all
    on this ore, and why the fines that gravity cannot hold are sent to the WHIMS instead.
    """
    sg_iron = (1 - goethite_share) * SG_HEM + goethite_share * SG_GOE
    sg_gangue = (1 - alumina_share) * SG_QZ + alumina_share * SG_AL
    inv = G / sg_iron + (1.0 - G) / sg_gangue
    return 1.0 / inv


def concentration_criterion(sg_heavy: float, sg_light: float, sg_fluid: float = SG_WATER) -> float:
    """Taggart concentration criterion. > 2.5 separates readily to 75 um, 1.5-2.5 to ~1 mm."""
    return (sg_heavy - sg_fluid) / max(sg_light - sg_fluid, 1e-6)


def rosin_rammler(p80_um: float, n: float = 0.85) -> np.ndarray:
    """Mass fraction retained in each size class for a Rosin-Rammler distribution with this P80."""
    x63 = max(p80_um, 1e-3) / (-np.log(0.2)) ** (1.0 / n)
    passing = 1.0 - np.exp(-((SIZES_UM / x63) ** n))
    passing[0] = 1.0                                  # oversize is carried in the top class
    lower = np.concatenate([passing[1:], [0.0]])
    retained = np.clip(passing - lower, 0.0, None)
    s = retained.sum()
    return retained / s if s > 0 else retained


def p_passing(size_frac: np.ndarray, pct: float = 80.0) -> float:
    """Size (um) at which ``pct`` % of the mass passes (log-linear interpolation)."""
    passing = np.cumsum(size_frac[::-1])[::-1]        # passing[i] = fraction finer than SIZES_UM[i]
    target = pct / 100.0
    for i in range(len(SIZES_UM) - 1, 0, -1):
        if passing[i - 1] >= target >= passing[i]:
            y0, y1 = passing[i], passing[i - 1]
            if y1 <= y0:
                return float(SIZES_UM[i])
            x0, x1 = np.log(SIZES_UM[i]), np.log(SIZES_UM[i - 1])
            return float(np.exp(x0 + (target - y0) / (y1 - y0) * (x1 - x0)))
    return float(SIZES_UM[-1])


def pct_passing_size(size_frac: np.ndarray, size_um: float) -> float:
    """% of the mass finer than ``size_um``."""
    frac = 0.0
    for i, upper in enumerate(SIZES_UM):
        lower = SIZES_UM[i + 1] if i + 1 < len(SIZES_UM) else 0.0
        if upper <= size_um:
            frac += size_frac[i]
        elif lower < size_um < upper:
            frac += size_frac[i] * float(np.log(size_um / max(lower, 1e-6)) / np.log(upper / max(lower, 1e-6)))
    return 100.0 * float(np.clip(frac, 0.0, 1.0))


def magnetic_susceptibility(goethite_share: float = 0.12) -> np.ndarray:
    """Relative mass susceptibility of each liberation class (hematite = 1.0).

    Hematite and goethite are weakly paramagnetic, which is why this plant needs a *high*
    intensity separator (1.0-1.5 T) where a magnetite plant would use a drum at 0.1 T. Goethite
    responds a little more strongly than hematite; quartz not at all.
    """
    per_iron = (1 - goethite_share) * 1.0 + goethite_share * 1.18
    return G * per_iron


#: complete liberation is never reached — micro-inclusions, goethite rims and clay intergrowths
#: leave a residue of composite particles at every size. Without this ceiling a gravity circuit
#: separates pure hematite from pure quartz and reports concentrate grades no plant achieves.
MAX_LIBERATION = 0.90


def liberation_curve(d50_um: float, steepness: float = 2.6,
                     max_liberation: float = MAX_LIBERATION) -> np.ndarray:
    """Fraction of material liberated at each size class (mineralogical banding scale ``d50``)."""
    return max_liberation / (1.0 + (GEO_MEAN_UM / max(d50_um, 1.0)) ** steepness)


@dataclass
class Stream:
    """Process stream: tonnage, (size x liberation) mass matrix, water and secondary mineralogy."""

    solids_tph: float
    m: np.ndarray                      # (N_CLASSES, N_BINS) mass fractions, sums to 1
    water_tph: float = 0.0
    goethite_share: float = 0.22       # of the iron minerals
    alumina_share: float = 0.18        # clay / ochre share of the gangue
    name: str = ""

    # ---- size ---------------------------------------------------------------------------------
    @property
    def size_frac(self) -> np.ndarray:
        return self.m.sum(axis=1)

    @property
    def p80_um(self) -> float:
        return p_passing(self.size_frac, 80.0)

    @property
    def p50_um(self) -> float:
        return p_passing(self.size_frac, 50.0)

    @property
    def minus_45um_pct(self) -> float:
        return pct_passing_size(self.size_frac, 45.0)

    @property
    def minus_10um_pct(self) -> float:
        return pct_passing_size(self.size_frac, 10.0)

    # ---- composition --------------------------------------------------------------------------
    @property
    def iron_mineral_frac(self) -> float:
        return float((self.m * G[None, :]).sum())

    @property
    def liberation_pct(self) -> float:
        """Mass fraction of the iron minerals present in essentially liberated particles (g > 0.9)."""
        iron = self.m * G[None, :]
        tot = iron.sum()
        return float(100.0 * iron[:, G >= 0.999].sum() / max(tot, 1e-12))

    def assay(self) -> dict[str, float]:
        gsh, ash = self.goethite_share, self.alumina_share
        iron = self.iron_mineral_frac
        gangue = 1.0 - iron
        fe = iron * ((1 - gsh) * FE_HEM + gsh * FE_GOE) + gangue * ash * FE_AL
        sio2 = gangue * ((1 - ash) * SIO2_QZ + ash * SIO2_AL)
        al2o3 = gangue * ash * AL2O3_AL + iron * gsh * AL2O3_GOE
        loi = iron * ((1 - gsh) * LOI_HEM + gsh * LOI_GOE) + gangue * ash * LOI_AL
        return {"fe_pct": 100 * fe, "sio2_pct": 100 * sio2, "al2o3_pct": 100 * al2o3, "loi_pct": 100 * loi,
                "p_pct": 0.040 + 0.03 * max(1.0 - fe / 0.62, 0.0)}

    @property
    def sg(self) -> float:
        gsh, ash = self.goethite_share, self.alumina_share
        iron = self.iron_mineral_frac
        sg_iron = (1 - gsh) * SG_HEM + gsh * SG_GOE
        sg_gangue = (1 - ash) * SG_QZ + ash * SG_AL
        inv = iron / sg_iron + (1 - iron) / sg_gangue
        return float(1.0 / inv) if inv > 0 else 3.5

    @property
    def particle_sg(self) -> np.ndarray:
        """SG of each liberation class for this stream's mineralogy — the gravity separating axis."""
        return particle_sg(self.goethite_share, self.alumina_share)

    @property
    def sg_spread(self) -> tuple[float, float]:
        """(lightest, heaviest) particle SG present in meaningful quantity."""
        sgp = self.particle_sg
        w = self.m.sum(axis=0)
        present = np.where(w > 1e-5)[0]
        if present.size == 0:
            return (SG_QZ, SG_HEM)
        return (float(sgp[present[0]]), float(sgp[present[-1]]))

    def sg_distribution(self, edges: np.ndarray | None = None) -> dict[str, list[float]]:
        """Washability-style mass split by particle density — the float-and-sink curve."""
        sgp = self.particle_sg
        w = self.m.sum(axis=0)
        iron = (self.m * G[None, :]).sum(axis=0)
        if edges is None:
            edges = np.array([2.40, 2.75, 3.10, 3.45, 3.80, 4.15, 4.50, 4.80, 5.25])
        mass, grade, mids = [], [], []
        for lo, hi in zip(edges[:-1], edges[1:]):
            sel = (sgp >= lo) & (sgp < hi)
            mm = float(w[sel].sum())
            mass.append(100.0 * mm)
            g = float(iron[sel].sum() / mm) if mm > 1e-9 else 0.0
            fe_per_iron = (1 - self.goethite_share) * FE_HEM + self.goethite_share * FE_GOE
            grade.append(100.0 * g * fe_per_iron)
            mids.append(float((lo + hi) / 2))
        return {"sg_mid": mids, "mass_pct": mass, "fe_pct": grade}

    @property
    def plus_10mm_pct(self) -> float:
        return 100.0 - pct_passing_size(self.size_frac, 10_000.0)

    @property
    def minus_150um_pct(self) -> float:
        return pct_passing_size(self.size_frac, 150.0)

    @property
    def blaine(self) -> float:
        """Blaine specific surface (cm2/g) — pellet-feed fineness specification."""
        shape = 1.75
        area = float(np.sum(self.size_frac * (6.0 * shape / (self.sg * np.maximum(GEO_MEAN_UM, 3.0) * 1e-4))))
        return area * 0.42

    @property
    def fe_tph(self) -> float:
        return self.solids_tph * self.assay()["fe_pct"] / 100.0

    @property
    def sio2_tph(self) -> float:
        return self.solids_tph * self.assay()["sio2_pct"] / 100.0

    # ---- slurry -------------------------------------------------------------------------------
    @property
    def solids_pct(self) -> float:
        tot = self.solids_tph + self.water_tph
        return 100.0 * self.solids_tph / tot if tot > 0 else 0.0

    @property
    def slurry_m3_h(self) -> float:
        return self.solids_tph / self.sg + self.water_tph

    @property
    def pulp_density_t_m3(self) -> float:
        v = self.slurry_m3_h
        return (self.solids_tph + self.water_tph) / v if v > 0 else 1.0

    # ---- helpers ------------------------------------------------------------------------------
    def copy(self, **kw) -> "Stream":
        d = {"solids_tph": self.solids_tph, "m": self.m.copy(), "water_tph": self.water_tph,
             "goethite_share": self.goethite_share, "alumina_share": self.alumina_share, "name": self.name}
        d.update(kw)
        return Stream(**d)

    def with_solids(self, tph: float) -> "Stream":
        return self.copy(solids_tph=tph)

    def summary(self) -> dict[str, float]:
        a = self.assay()
        return {"solids_tph": round(self.solids_tph, 2), "water_m3_h": round(self.water_tph, 1),
                "solids_pct": round(self.solids_pct, 2), "p80_um": round(self.p80_um, 2),
                "minus_45um_pct": round(self.minus_45um_pct, 2), "minus_10um_pct": round(self.minus_10um_pct, 2),
                "plus_10mm_pct": round(self.plus_10mm_pct, 2), "minus_150um_pct": round(self.minus_150um_pct, 2),
                "blaine_cm2_g": round(self.blaine, 0), "fe_pct": round(a["fe_pct"], 2),
                "sio2_pct": round(a["sio2_pct"], 2), "al2o3_pct": round(a["al2o3_pct"], 2),
                "loi_pct": round(a["loi_pct"], 2), "fe_tph": round(self.fe_tph, 2),
                "liberation_pct": round(self.liberation_pct, 1), "sg": round(self.sg, 2)}


# ---------------------------------------------------------------------------------------------
def _bin_distribution(mean_g: float, liberated: float, kappa: float = 14.0) -> np.ndarray:
    """Composition distribution within one size class: liberated fraction at the extremes,
    the remainder as a Beta density with the same mean."""
    mg = float(np.clip(mean_g, 1e-3, 1 - 1e-3))
    a, b = kappa * mg, kappa * (1 - mg)
    dens = np.zeros(N_BINS)
    inner = G[1:-1]
    dens[1:-1] = inner ** (a - 1) * (1 - inner) ** (b - 1)   # composites occupy the interior classes
    dens = dens / max(dens.sum(), 1e-12)
    # keep the composite mean equal to the class assay (the Beta mean is distorted by truncation)
    mean_inner = float((dens * G).sum())
    if mean_inner > mg:
        shift = (mean_inner - mg) / max(mean_inner, 1e-9)
        dens_shift = dens * (1 - shift)
        dens = dens_shift
        dens[0] += 1.0 - dens.sum()
    elif mean_inner < mg:
        shift = (mg - mean_inner) / max(1.0 - mean_inner, 1e-9)
        dens = dens * (1 - shift)
        dens[-1] += 1.0 - dens.sum()
    w = (1 - liberated) * dens
    w[-1] += liberated * mg
    w[0] += liberated * (1 - mg)
    return w / max(w.sum(), 1e-12)


def make_feed(solids_tph: float, water_tph: float, f80_um: float, fe_pct: float, sio2_pct: float,
              al2o3_pct: float, liberation_d50_um: float, goethite_share: float = 0.22,
              rr_n: float = 0.80, name: str = "feed") -> Stream:
    """Build a ROM stream from the assay, the size distribution and the liberation (banding) scale."""
    size = rosin_rammler(f80_um, rr_n)
    fe, sio2, al = fe_pct / 100.0, sio2_pct / 100.0, al2o3_pct / 100.0
    fe_per_iron = (1 - goethite_share) * FE_HEM + goethite_share * FE_GOE
    iron = float(np.clip(fe / fe_per_iron, 0.02, 0.97))
    gangue = 1.0 - iron
    alumina_share = float(np.clip(al / max(gangue * AL2O3_AL, 1e-6), 0.0, 0.6))
    lib = liberation_curve(liberation_d50_um)
    m = np.zeros((N_CLASSES, N_BINS))
    for i in range(N_CLASSES):
        m[i] = size[i] * _bin_distribution(iron, lib[i])
    return Stream(solids_tph, m / max(m.sum(), 1e-12), water_tph, goethite_share, alumina_share, name)


def blend(streams: list[Stream], name: str = "") -> Stream:
    """Mass-weighted combination of streams (water is additive)."""
    streams = [s for s in streams if s is not None]
    if not streams:
        return Stream(0.0, np.zeros((N_CLASSES, N_BINS)), 0.0, name=name)
    solids = sum(s.solids_tph for s in streams)
    water = sum(s.water_tph for s in streams)
    if solids <= 1e-9:
        base = streams[0].copy(solids_tph=0.0, water_tph=water, name=name)
        return base
    m = sum(s.m * s.solids_tph for s in streams) / solids
    iron_mass = sum(s.solids_tph * s.iron_mineral_frac for s in streams)
    gang_mass = sum(s.solids_tph * (1 - s.iron_mineral_frac) for s in streams)
    goe = sum(s.solids_tph * s.iron_mineral_frac * s.goethite_share for s in streams) / max(iron_mass, 1e-9)
    al = sum(s.solids_tph * (1 - s.iron_mineral_frac) * s.alumina_share for s in streams) / max(gang_mass, 1e-9)
    return Stream(solids, m / max(m.sum(), 1e-12), water, goe, al, name)


def split(stream: Stream, recovery: np.ndarray, water_split: float,
          names: tuple[str, str] = ("product", "reject"),
          goethite_bias: float = 1.0, alumina_bias: float = 1.0) -> tuple[Stream, Stream]:
    """Split a stream with a (size x liberation) recovery matrix into (recovered, rejected).

    ``goethite_bias`` < 1 means goethite reports less strongly than hematite to the recovered
    stream (weaker magnetic response); ``alumina_bias`` > 1 means alumina-bearing slimes follow
    the recovered stream more than free quartz does.
    """
    r = np.clip(recovery, 0.0, 1.0)
    m1 = stream.m * r
    m2 = stream.m - m1
    f1, f2 = m1.sum(), m2.sum()
    iron_in = stream.iron_mineral_frac
    iron_1 = float((m1 * G[None, :]).sum())
    gang_1 = float(f1 - iron_1)
    gsh, ash = stream.goethite_share, stream.alumina_share
    # secondary mineral re-partition (first-order bias model, mass conserved)
    goe_rec = gsh * goethite_bias / max(gsh * goethite_bias + (1 - gsh), 1e-9)
    al_rec = ash * alumina_bias / max(ash * alumina_bias + (1 - ash), 1e-9)
    s1 = Stream(stream.solids_tph * f1, m1 / max(f1, 1e-12), stream.water_tph * water_split,
                float(np.clip(goe_rec, 0.0, 0.95)), float(np.clip(al_rec, 0.0, 0.95)), names[0])
    iron_total = stream.solids_tph * iron_in
    iron_p = stream.solids_tph * iron_1
    goe_total = iron_total * gsh
    goe_p = iron_p * s1.goethite_share
    goe_r = max(goe_total - goe_p, 0.0) / max(iron_total - iron_p, 1e-9)
    gang_total = stream.solids_tph * (1 - iron_in)
    gang_p = stream.solids_tph * gang_1
    al_total = gang_total * ash
    al_p = gang_p * s1.alumina_share
    al_r = max(al_total - al_p, 0.0) / max(gang_total - gang_p, 1e-9)
    s2 = Stream(stream.solids_tph * f2, m2 / max(f2, 1e-12), stream.water_tph * (1 - water_split),
                float(np.clip(goe_r, 0.0, 0.95)), float(np.clip(al_r, 0.0, 0.95)), names[1])
    return s1, s2


def uplift_grade(row: np.ndarray, factor: float) -> np.ndarray:
    """Re-bin one size class after a fraction of its gangue has been stripped off.

    Scrubbing removes a clay coating from a lump. The lump gets lighter and *richer*: its iron
    content is unchanged but its mass has fallen, so its grade rises by ``factor`` = 1/(1 - c).
    Mass at the new grade is shared between the two neighbouring liberation bins so that both
    the mass and the iron units in the row are conserved exactly.
    """
    f = float(max(factor, 1.0))
    if f <= 1.0 + 1e-12:
        return row
    out = np.zeros_like(row)
    for b, w in enumerate(row):
        if w <= 1e-15:
            continue
        g_new = min(G[b] * f, 1.0)
        mass = w * (G[b] / g_new) if g_new > 1e-12 else w     # mass shrinks, iron units are kept
        if g_new <= G[0]:
            # a barren shale lump gets no richer for being scrubbed — it simply loses the same
            # fraction of its mass as everything else
            out[0] += w / f
            continue
        hi = int(np.searchsorted(G, g_new, side="left"))
        hi = min(max(hi, 1), N_BINS - 1)
        lo = hi - 1
        span = G[hi] - G[lo]
        frac = 0.0 if span <= 1e-12 else float((g_new - G[lo]) / span)
        out[lo] += mass * (1.0 - frac)
        out[hi] += mass * frac
    return out


def apply_liberation(m: np.ndarray, lib: np.ndarray) -> np.ndarray:
    """Move newly broken material towards the liberation level of its (finer) size class.

    For each size class the mass sitting in intermediate composition bins is partly transferred to
    the two extreme bins (free iron mineral / free gangue), conserving both mass and mean grade.
    Material that was already liberated stays liberated — this is what gives the twin a memory of
    upgrading through successive grind-and-separate stages.
    """
    out = m.copy()
    for i in range(m.shape[0]):
        row = out[i]
        tot = row.sum()
        if tot <= 1e-12:
            continue
        current = (row[0] + row[-1]) / tot
        target = float(lib[i])
        if target <= current + 1e-6:
            continue
        alpha = (target - current) / max(1.0 - current, 1e-9)
        mid = row.copy()
        mid[0] = mid[-1] = 0.0
        moved = alpha * mid
        mass = moved.sum()
        if mass <= 1e-12:
            continue
        mean_g = float((moved * G).sum() / mass)
        row -= moved
        row[-1] += mass * mean_g
        row[0] += mass * (1.0 - mean_g)
        out[i] = np.clip(row, 0.0, None)
    s = out.sum()
    return out / s if s > 0 else out
