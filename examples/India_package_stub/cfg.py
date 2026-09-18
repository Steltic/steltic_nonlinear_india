# Stub cfg — replace with a real steltic_india job export.
# Geometry shown in metres; call snl.india_units.apply_metric_geometry before engine use.

jurisdiction = "india"
units = "metric"
metric = True
seismic_zone = "III"
soil_type = "II"
importance_factor = 1.0
R = 5.0  # response reduction — confirm via IS 1893 Table 9 LIVE RAG for the system

# Placeholder geometry (m) — not a real building
story_heights = [3.5, 3.5, 3.5]
bay_x = [6.0, 6.0]
bay_y = [5.0]

# Minimal load_plan shape (agent must fill LIVE RAG retrieval on a real job)
load_plan = {
    "jurisdiction": "india",
    "partial_factors_cite": "IS 800:2007 Table 4 — RETRIEVE LIVE",
    "retrieval": [
        {
            "stem": "IS_1893_Part_1_2016",
            "query": "7.11.1.1",
            "found": True,
            "cite": "7.11.1.1 storey drift 0.004 h",
        },
        {
            "stem": "IS_875_Part_2_1987",
            "query": "imposed loads",
            "found": False,
            "cite": "stub — retrieve LIVE on real job",
        },
    ],
    "combinations": [
        {"label": "1.5DL+1.5LL", "fD": 1.5, "fL": 1.5, "fLr": 0.0, "lateral": {}, "col_only": False,
         "cite": "IS 800:2007 Table 4 — stub"},
    ],
}

india_hazard = {
    "zone": "III",
    "soil": "II",
    "I": 1.0,
    "R": 5.0,
}
