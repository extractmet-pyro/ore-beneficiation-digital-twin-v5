"""Model metadata: what the twin is, what it assumes, and how it is validated."""
from __future__ import annotations

from app.control.identification import CVS, MVS
from app.core.config import get_settings
from app.models.domain import EconomicsConfig, FlowsheetConfig, OperatingConfig, OreConfig
from app.twin.constraints import CONSTRAINTS
from app.twin.objectives import OBJECTIVES
from app.twin.soft_sensors import SOFT_SENSORS

MODELS = [
    {"unit": "Crushing", "model": "Whiten classification-breakage with a t10 appearance function",
     "reference": "Whiten (1972); Napier-Munn et al., Mineral Comminution Circuits (1996)",
     "inputs": ["CSS", "A x b", "feed size distribution"], "outputs": ["product PSD", "power"]},
    {"unit": "Screens and trommel", "model": "Whiten partition curve with a true-undersize efficiency term",
     "reference": "Napier-Munn et al. (1996)", "inputs": ["aperture", "loading"],
     "outputs": ["oversize / undersize split", "screening efficiency"]},
    {"unit": "Rotary scrubber", "model": "First-order attrition of the clay coating over the drum "
                                         "residence time, with the detached clay re-reporting to the fines "
                                         "and the scrubbed lumps re-binned to a higher grade",
     "reference": "Wills & Finch, Mineral Processing Technology, 8th ed. (2016), ch. 2",
     "inputs": ["drum speed", "water", "pulp density", "clay type"],
     "outputs": ["clay removal", "lump alumina", "fines generation", "power"]},
    {"unit": "Jig (lump and fines)",
     "model": "Tromp density partition about a cut density set by the bed condition, with a probable "
              "error that degrades steeply below about 3 mm",
     "reference": "Burt, Gravity Concentration Technology (1984); Rong & Lyman (1985)",
     "inputs": ["stroke", "frequency", "bed depth", "hutch water", "loading"],
     "outputs": ["cut density", "Ep by size", "yield", "concentrate grade"]},
    {"unit": "Screw classifier",
     "model": "Hindered-settling classification with a per-density cut size from the equal-settling ratio",
     "reference": "Gaudin (1939); Wills & Finch (2016), ch. 9",
     "inputs": ["overflow rate", "weir height", "screw speed", "slope"],
     "outputs": ["cut size", "sand / slime split", "overflow grade"]},
    {"unit": "Hydrocyclone", "model": "Plitt d50c with a Whiten efficiency curve and water bypass",
     "reference": "Plitt (1976); Nageswararao (1995)", "inputs": ["geometry", "pressure", "feed density"],
     "outputs": ["partition curve", "overflow PSD", "underflow density"]},
    {"unit": "Spiral concentrator",
     "model": "Flowing-film density separation with two splitter positions giving three products, over a "
              "size window of roughly 2 mm to 75 um",
     "reference": "Burt (1984); Holland-Batt (1995)",
     "inputs": ["splitter positions", "wash water", "feed density", "loading per start"],
     "outputs": ["concentrate", "middling", "tailing", "Ep by size"]},
    {"unit": "Shaking table",
     "model": "Asymmetric-deck density separation, the sharpest Ep in the plant but only on a narrow, "
              "closely sized, deslimed feed",
     "reference": "Burt (1984); Wills & Finch (2016), ch. 10",
     "inputs": ["deck slope", "stroke", "frequency", "wash water", "cut position"],
     "outputs": ["concentrate", "middling", "tailing"]},
    {"unit": "WHIMS",
     "model": "Magnetic / drag / gravity force balance at the matrix surface, giving a capture window in "
              "both particle susceptibility and particle size",
     "reference": "Svoboda, Magnetic Techniques for the Treatment of Materials (2004); Oberteuffer (1974)",
     "inputs": ["field intensity", "matrix type", "gap", "loading", "wash water"],
     "outputs": ["magnetic concentrate grade", "Fe recovery", "alumina rejection"]},
    {"unit": "Thickening", "model": "Yoshioka / Coe & Clevenger solids-flux with flocculant response",
     "reference": "Yoshioka et al. (1957); Talmage & Fitch (1955)",
     "inputs": ["feed rate", "flocculant", "area"], "outputs": ["underflow density", "overflow TSS", "rake torque"]},
    {"unit": "Supervisory control",
     "model": "FOPDT identification from the twin + condensed DMC with soft zone constraints",
     "reference": "Cutler & Ramaker (1980); Maciejowski (2002)",
     "inputs": ["gain matrix", "residence and transport times", "zones", "limits"],
     "outputs": ["move plan", "predicted trajectories", "DCS hand-over"]},
    {"unit": "Machine learning",
     "model": "Gradient-boosted soft sensors, hybrid twin-residual correction, isolation-forest anomaly "
              "detection, PSI drift monitoring",
     "reference": "Friedman (2001); Liu, Ting & Zhou (2008)",
     "inputs": ["set-point and ore features"], "outputs": ["quality prediction", "anomaly score", "drift status"]},
]

ASSUMPTIONS = [
    "Steady state at each solve; dynamics are supplied separately by the FOPDT layer used for control.",
    "Mineralogy is represented by hematite, goethite, quartz and a clay / alumina gangue.",
    "Particle density is derived from the liberation class, so every gravity unit separates on the "
    "axis the state matrix already tracks.",
    "Liberation is bounded below 100 %: micro-inclusions and goethite rims leave a residue of "
    "composite particles at every size, which is why no separator in the model returns a pure product.",
    "Clay is carried in two forms — discrete shale particles and a surface coating on the lumps — and "
    "only the coating can be scrubbed off.",
    "Water is balanced around the plant boundary: fresh make-up is what is lost in product moisture, "
    "to the tailings pond and to evaporation, less pond reclaim.",
    "Prices follow a 62 % Fe index with separate lump and pellet-feed premiums and an alumina penalty "
    "above a contractual free allowance.",
]

VALIDATION = [
    {"check": "Solids and iron balance closure around every node", "target": "> 99.5 %", "method": "twin balance"},
    {"check": "Washability (float-and-sink) of the feed against laboratory heavy-liquid separation",
     "target": "within 2 % mass in each density fraction", "method": "HLS test work"},
    {"check": "Jig partition curve and Ep against a tracer survey", "target": "Ep within 0.05 SG",
     "method": "density-tracer survey"},
    {"check": "Spiral concentrate grade and yield at the surveyed splitter positions",
     "target": "within 1.5 % Fe", "method": "plant survey"},
    {"check": "Lump alumina response to scrubber duty", "target": "within 0.3 % Al2O3",
     "method": "scrubber step test"},
    {"check": "WHIMS Fe recovery against a Davis-tube / bench WHIMS series", "target": "within 3 %",
     "method": "bench test work"},
    {"check": "Classifier cut size against a sized-assay survey", "target": "within 15 %", "method": "survey"},
    {"check": "MPC closed-loop lump-alumina zone error vs open loop", "target": "> 40 % reduction",
     "method": "simulation study"},
]


class MetadataService:
    def metadata(self) -> dict:
        s = get_settings()
        return {"name": s.APP_NAME, "model_version": s.MODEL_VERSION, "environment": s.APP_ENV,
                "commodity": "Iron ore — hematite / goethite with a clay-bearing gangue",
                "flowsheet": "Crushing -> rotary scrubber -> lump jig (lump ore) -> screw classifier -> "
                             "fines jig + tertiary recrush -> cyclones -> spirals -> shaking tables "
                             "(sinter fines) -> desliming cyclones -> WHIMS (pellet-plant feed) -> "
                             "tailings thickener and water recovery",
                "unit_models": MODELS, "assumptions": ASSUMPTIONS, "validation": VALIDATION,
                "soft_sensors": SOFT_SENSORS,
                "state_representation": {"size_classes": 36, "liberation_classes": 15,
                                         "top_size_um": 250000, "series": "sqrt(2) geometric",
                                         "separating_property": "particle density, derived from the "
                                                                "liberation class (2.65 to 5.15 SG)"},
                "control": {"mvs": len(MVS), "cvs": len(CVS), "formulation": "condensed DMC, soft constraints"},
                "counts": {"constraints": len(CONSTRAINTS), "objectives": len(OBJECTIVES)}}

    def config_schema(self) -> dict:
        return {"flowsheet": FlowsheetConfig.model_json_schema(), "ore": OreConfig.model_json_schema(),
                "operating": OperatingConfig.model_json_schema(), "economics": EconomicsConfig.model_json_schema(),
                "defaults": {"flowsheet": FlowsheetConfig().model_dump(), "ore": OreConfig().model_dump(),
                             "operating": OperatingConfig().model_dump(), "economics": EconomicsConfig().model_dump()}}

    def constraints(self) -> list[dict]:
        return [c.as_dict() for c in CONSTRAINTS]

    def objectives(self) -> list[dict]:
        return [o.as_dict() for o in OBJECTIVES]


_service: MetadataService | None = None


def get_metadata_service() -> MetadataService:
    global _service
    if _service is None:
        _service = MetadataService()
    return _service
