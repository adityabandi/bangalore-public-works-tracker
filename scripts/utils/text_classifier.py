"""Classify BBMP work order descriptions into categories using keyword matching."""

# Keywords ordered by specificity — first match wins
CATEGORY_KEYWORDS = {
    "roads": [
        "road", "resurfacing", "asphalting", "bituminous", "tar road",
        "wbm", "footpath", "median", "divider", "speed breaker", "speed-breaker",
        "pothole", "blacktopping", "white topping", "white-topping", "milling",
        "carriageway", "pavement", "kerb", "curb", "grade separator",
        "flyover", "underpass", "junction improvement", "signal",
        "bc and sdbc", "bm and sdbc", "laying of road",
    ],
    "drainage": [
        "drain", "rajakaluve", "raja kaluve", "swd", "stormwater", "storm water",
        "culvert", "sluice", "desilting", "retaining wall", "nala", "nallah",
        "revetment", "flood", "catchpit", "manhole cover",
    ],
    "buildings": [
        "building", "community hall", "bhavan", "office construction",
        "renovation of", "repair of building", "compound wall", "toilet",
        "rest room", "crematorium", "park", "playground", "stadium",
        "market", "library", "anganwadi",
    ],
    "lighting": [
        "street light", "streetlight", "led light", "high mast",
        "electrical work", "illumination", "decorative light",
    ],
    "swm": [
        "solid waste", "garbage", "auto tipper", "compactor",
        "waste management", "swm", "dry waste", "wet waste",
        "segregation", "compost",
    ],
    "water": [
        "water supply", "borewell", "bore well", "pipeline", "water line",
        "sewage", "ugd", "stp", "sewerage", "overhead tank", "sump",
        "water purif", "ro plant", "drinking water",
    ],
    "surveillance": [
        "cctv", "camera", "surveillance",
    ],
}


def classify_work(name_of_work: str) -> str:
    """Classify a work description into a category.

    Returns one of: roads, drainage, buildings, lighting, swm, water,
    surveillance, other
    """
    if not name_of_work:
        return "other"

    text = str(name_of_work).lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return category

    return "other"
