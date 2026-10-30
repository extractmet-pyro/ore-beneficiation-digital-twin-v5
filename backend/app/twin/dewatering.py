"""Thickening, magnetic thickening (desliming) and slurry pipeline transport."""
from __future__ import annotations

import numpy as np

from app.twin.psd import G, GEO_MEAN_UM, N_BINS, Stream, split


def thickener(feed: Stream, *, diameter_m: float, depth_m: float, target_underflow_solids_pct: float,
              flocculant_g_t: float, rake_torque_rating_knm: float, name: str = "thickener",
              ) -> tuple[Stream, Stream, dict]:
    """High-rate thickener (Coe & Clevenger / Yoshioka solids-flux analysis).

    Settling velocity follows a Richardson-Zaki hindered-settling form with a flocculant response;
    the achievable underflow density is limited by the resulting solids flux, and overflow clarity
    (TSS) degrades with rise rate and with the ultrafine content of the feed.
    """
    area = np.pi * (diameter_m / 2.0) ** 2
    sg = feed.sg
    phi_f = (feed.solids_tph / sg) / max(feed.slurry_m3_h, 1e-6)
    d50 = max(feed.p50_um, 1.0)
    floc = float(np.clip(flocculant_g_t, 0.0, 120.0))
    # unhindered settling velocity of the flocs (m/h)
    v0 = 3.6 * (0.55 + 0.035 * floc) * (d50 / 30.0) ** 0.55 * ((sg - 1.0) / 3.0) ** 0.7
    v0 = float(np.clip(v0, 0.4, 26.0))
    phi_u_target = (target_underflow_solids_pct / 100.0) / (target_underflow_solids_pct / 100.0
                                                            + (1 - target_underflow_solids_pct / 100.0) * sg)
    # the Yoshioka construction is evaluated between the feed and the target underflow concentration
    phis = np.linspace(max(phi_f, 0.01), max(phi_u_target * 0.985, phi_f + 0.02), 260)
    flux = phis * v0 * (1 - phis) ** 5.2          # batch flux curve (m/h x phi)
    # limiting flux for the target underflow concentration (Yoshioka construction)
    with np.errstate(divide="ignore", invalid="ignore"):
        lim = np.nanmin(np.where(phis < phi_u_target, flux / np.maximum(phi_u_target - phis, 1e-6) * phi_u_target, np.inf))
    limiting_flux = float(np.clip(lim, 1e-4, 50.0))                      # m/h of volume fraction
    required_area = (feed.solids_tph / sg) / max(limiting_flux, 1e-6)
    overload = required_area / max(area, 1e-6)
    achieved_uf_pct = float(target_underflow_solids_pct if overload <= 1.0
                            else target_underflow_solids_pct * float(np.clip(1.0 - 0.32 * (overload - 1.0), 0.55, 1.0)))
    rise_rate = (feed.water_tph - feed.solids_tph * (100 - achieved_uf_pct) / max(achieved_uf_pct, 1e-6)) / max(area, 1e-6)
    rise_rate = float(np.clip(rise_rate, 0.0, 30.0))
    ultrafine_pct = float(100.0 * feed.size_frac[GEO_MEAN_UM < 10.0].sum())
    tss = float(np.clip(12.0 + 26.0 * max(rise_rate - 4.5, 0.0) ** 1.25 + 1.6 * ultrafine_pct - 0.55 * floc, 4.0, 900.0))
    # solids lost to the overflow follow the TSS and the fine end of the PSD
    of_solids = tss * 1e-6 * max(feed.water_tph, 0.0) * 1000.0 / 1000.0 * 1.0  # t/h  (mg/L x m3/h -> kg/h -> t/h)
    of_solids = float(np.clip(tss * max(feed.water_tph, 0.0) / 1e6, 0.0, 0.4 * feed.solids_tph))
    fines_bias = np.clip(np.exp(-GEO_MEAN_UM / 9.0), 0.0, 1.0)
    w = fines_bias * feed.size_frac
    w = w / max(w.sum(), 1e-12)
    rec_of = np.minimum(np.where(feed.size_frac > 1e-9, of_solids * w / np.maximum(feed.size_frac * feed.solids_tph, 1e-9), 0.0), 0.9)
    # liberated silica slimes are lost preferentially to the overflow (the coarse-grade bins settle)
    bin_bias = np.clip(1.35 - 0.75 * G, 0.4, 1.6)[None, :]
    rec_matrix = np.clip(rec_of[:, None] * bin_bias, 0.0, 0.95)
    overflow, underflow = split(feed, rec_matrix, water_split=0.0,
                                names=(f"{name}_overflow", f"{name}_underflow"), alumina_bias=1.3)
    uf_water = underflow.solids_tph * (100 - achieved_uf_pct) / max(achieved_uf_pct, 1e-6)
    underflow.water_tph = uf_water
    overflow.water_tph = max(feed.water_tph - uf_water, 0.0)
    torque = float(np.clip(0.55 * rake_torque_rating_knm * (achieved_uf_pct / 65.0) ** 2.4 * (1 + 0.35 * max(overload - 1, 0)),
                           0.0, 1.6 * rake_torque_rating_knm))
    bed = float(np.clip(0.9 + 1.7 * (overload if overload < 2 else 2.0) * (achieved_uf_pct / 65.0), 0.3, depth_m * 0.95))
    info = {"diameter_m": diameter_m, "area_m2": round(area, 1), "feed_tph": round(feed.solids_tph, 1),
            "feed_solids_pct": round(feed.solids_pct, 2), "flocculant_g_t": round(floc, 1),
            "target_underflow_solids_pct": round(target_underflow_solids_pct, 1),
            "underflow_solids_pct": round(achieved_uf_pct, 2), "limiting_flux_tph_m2": round(limiting_flux * sg, 3),
            "required_area_m2": round(required_area, 1), "area_utilisation_pct": round(100 * overload, 1),
            "rise_rate_m_h": round(rise_rate, 2), "overflow_tss_mg_l": round(tss, 1),
            "solids_to_overflow_tph": round(overflow.solids_tph, 3), "bed_level_m": round(bed, 2),
            "rake_torque_knm": round(torque, 1), "rake_torque_pct": round(100 * torque / max(rake_torque_rating_knm, 1e-6), 1),
            "overflow_m3_h": round(overflow.water_tph, 1), "underflow_m3_h": round(underflow.slurry_m3_h, 1),
            "settling_velocity_m_h": round(v0, 2), "ultrafines_minus10um_pct": round(ultrafine_pct, 1),
            "flocculant_kg_h": round(floc * feed.solids_tph / 1000.0, 2)}
    return underflow, overflow, info


def slurry_pipeline(stream: Stream, *, length_m: float, diameter_m: float, static_head_m: float,
                    installed_kw: float, pump_type: str = "positive_displacement") -> dict:
    """Product/tailings slurry line: Durand deposition velocity, friction head and pump power."""
    q = max(stream.slurry_m3_h, 1e-6) / 3600.0
    area = np.pi * (diameter_m / 2.0) ** 2
    v = q / max(area, 1e-9)
    cv = (stream.solids_tph / stream.sg) / max(stream.slurry_m3_h, 1e-6)
    d50_m = max(stream.p50_um, 1.0) * 1e-6
    fl = 1.0 + 0.55 * np.log10(max(d50_m / 1e-4, 1e-3)) + 0.6 * cv
    v_dep = float(np.clip(fl * np.sqrt(2 * 9.81 * diameter_m * (stream.sg - 1.0)), 0.6, 6.0))
    rho = stream.pulp_density_t_m3 * 1000.0
    mu = 0.001 * (1.0 + 2.5 * cv + 10.05 * cv ** 2) * (1.0 + 0.0025 * max(stream.solids_pct - 55, 0) ** 2)
    re = rho * v * diameter_m / max(mu, 1e-6)
    f = 0.316 / max(re, 1e3) ** 0.25 if re < 1e5 else 0.0032 + 0.221 / re ** 0.237
    h_f = f * (length_m / max(diameter_m, 1e-6)) * v ** 2 / (2 * 9.81)
    total_head = h_f + static_head_m
    eff = 0.88 if pump_type == "positive_displacement" else 0.68
    power = rho * 9.81 * q * total_head / 1000.0 / eff
    return {"velocity_m_s": round(v, 2), "deposition_velocity_m_s": round(v_dep, 2),
            "velocity_margin": round(v / max(v_dep, 1e-6), 2), "flow_m3_h": round(q * 3600, 1),
            "solids_pct": round(stream.solids_pct, 1), "cv_pct": round(100 * cv, 1),
            "friction_head_m": round(h_f, 1), "static_head_m": static_head_m, "total_head_m": round(total_head, 1),
            "power_kw": round(power, 1), "installed_kw": installed_kw,
            "power_utilisation_pct": round(100 * power / max(installed_kw, 1e-6), 1),
            "pump_type": pump_type, "length_m": length_m, "diameter_m": diameter_m,
            "wear_index": round(float(np.clip(v ** 3 * cv * 12.0, 0, 100)), 2)}
