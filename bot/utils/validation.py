"""Input validation helpers."""
from __future__ import annotations

import re

NAME_RE = re.compile(r"^[\u0600-\u06FF\u0750-\u077FA-Za-z\u00C0-\u017F\s.\-_']{1,64}$")
CITY_RE = re.compile(r"^[\u0600-\u06FF\u0750-\u077FA-Za-z\u00C0-\u017F\s.\-']{1,64}$")

PERSIAN_CITIES = [
    "تهران", "مشهد", "اصفهان", "کرج", "شیراز", "اهواز", "تبریز",
    "قم", "کرمان", "ارومیه", "رشت", "زاهدان", "اراک", "همدان",
    "کرمانشاه", "یزد", "اردبیل", "بندرعباس", "قزوین", "زنجان",
    "ساری", "گرگان", "نوشهر", "بجنورد", "ایلام", "خرم‌آباد",
    "سنندج", "سمنان", "شهرکرد", "بوشهر", "بیرجند", "ماسول",
]


def validate_name(name: str) -> bool:
    return bool(NAME_RE.match(name.strip()))

def validate_bio(bio: str) -> bool:
    bio = bio.strip()
    return 1 <= len(bio) <= 500

def validate_age(age_str: str) -> bool:
    try:
        a = int(age_str.strip())
        return 13 <= a <= 120
    except Exception:
        return False

def validate_city(city: str) -> bool:
    return bool(CITY_RE.match(city.strip()))

def normalize_city(city: str) -> str:
    """If a known Persian city is mentioned, return its canonical form."""
    c = city.strip()
    for known in PERSIAN_CITIES:
        if known in c or c in known:
            return known
    return c
