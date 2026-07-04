"""CAMEO root-code theme groupings.

CAMEO is a political-event taxonomy (statements, appeals, protests, assaults…)
— it has no consumer-news topics like sports or tech, so the category filter
groups its 20 root codes into six honest themes. Served to the frontend via
GET /themes so there is a single source of truth.
"""

CAMEO_THEMES: dict[str, dict] = {
    "diplomacy": {
        "label": "Diplomacy & Statements",
        "codes": ["01", "02", "03", "04", "05"],
    },
    "cooperation": {
        "label": "Cooperation & Aid",
        "codes": ["06", "07", "08"],
    },
    "disputes": {
        "label": "Disputes & Demands",
        "codes": ["09", "10", "11", "12"],
    },
    "protest": {
        "label": "Protest & Dissent",
        "codes": ["14"],
    },
    "coercion": {
        "label": "Coercion & Threats",
        "codes": ["13", "15", "16", "17"],
    },
    "conflict": {
        "label": "Conflict & Violence",
        "codes": ["18", "19", "20"],
    },
}


def codes_for_themes(themes: list[str]) -> list[str]:
    """Union of root codes for the given theme keys. Raises on unknown keys."""
    codes: list[str] = []
    for theme in themes:
        if theme not in CAMEO_THEMES:
            raise KeyError(theme)
        codes.extend(CAMEO_THEMES[theme]["codes"])
    return sorted(set(codes))
