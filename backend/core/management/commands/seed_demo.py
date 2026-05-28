"""
Seed reference data + two demo orgs + a few demo users.

Idempotent: safe to re-run. Uses get_or_create against natural keys (slug,
code, etc.) rather than IDs.

What gets seeded:
  Reference (global):
    * CanonicalUnit: kWh, MWh-as-input handled via converter, L, kg, t, km,
      passenger_km, room_nights, usd
    * EmissionCategory: 8 GHG-Protocol categories spanning Scopes 1/2/3
    * EmissionFactor: one per (category, region, year) with cited source
    * Airport: 30 majors with lat/lon
  Per-org:
    * Acme Corp (slug=acme) + Globex (slug=globex)
    * PlantCode entries per org
    * Memberships: analyst@<org>.test (password 'breathe'), admin@<org>.test
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from core.models import Membership, MembershipRole, Organization
from emissions.models import (
    Airport,
    CanonicalUnit,
    EmissionCategory,
    EmissionFactor,
    PlantCode,
    Scope,
    UnitDimension,
)


UNITS = [
    ("kWh", "Kilowatt-hour", UnitDimension.ENERGY),
    ("L", "Liter", UnitDimension.VOLUME),
    ("kg", "Kilogram", UnitDimension.MASS),
    ("km", "Kilometer", UnitDimension.DISTANCE),
    ("passenger_km", "Passenger-kilometer", UnitDimension.PASSENGER_DISTANCE),
    ("room_nights", "Room-nights", UnitDimension.COUNT),
    ("usd", "USD spend", UnitDimension.CURRENCY),
]


# (code, label, scope, default_unit_code, ghg_ref)
CATEGORIES = [
    ("stationary_fuel_diesel", "Stationary combustion — Diesel",     Scope.SCOPE_1, "L",            "GHG Protocol Scope 1, fuel combustion"),
    ("stationary_fuel_petrol", "Stationary combustion — Petrol",     Scope.SCOPE_1, "L",            "GHG Protocol Scope 1, fuel combustion"),
    ("mobile_fuel_diesel",     "Mobile combustion — Diesel",         Scope.SCOPE_1, "L",            "GHG Protocol Scope 1, fleet"),
    ("purchased_electricity",  "Purchased electricity",              Scope.SCOPE_2, "kWh",          "GHG Protocol Scope 2, location-based"),
    ("business_travel_air",    "Business travel — Air",              Scope.SCOPE_3, "passenger_km", "GHG Protocol Scope 3, Cat 6"),
    ("business_travel_lodging","Business travel — Lodging",          Scope.SCOPE_3, "room_nights",  "GHG Protocol Scope 3, Cat 6"),
    ("business_travel_ground", "Business travel — Ground transport", Scope.SCOPE_3, "km",           "GHG Protocol Scope 3, Cat 6"),
    ("purchased_goods_spend",  "Purchased goods & services (spend)", Scope.SCOPE_3, "usd",          "GHG Protocol Scope 3, Cat 1"),
]


# (category_code, region, year, unit_code, kg_co2e_per_unit, source)
FACTORS = [
    ("stationary_fuel_diesel",  "global", 2025, "L",            Decimal("2.687"),  "DEFRA 2024 GHG Conversion Factors"),
    ("stationary_fuel_petrol",  "global", 2025, "L",            Decimal("2.315"),  "DEFRA 2024 GHG Conversion Factors"),
    ("mobile_fuel_diesel",      "global", 2025, "L",            Decimal("2.687"),  "DEFRA 2024 GHG Conversion Factors"),
    ("purchased_electricity",   "US",     2025, "kWh",          Decimal("0.371"),  "EPA eGRID 2023, US average"),
    ("purchased_electricity",   "DE",     2025, "kWh",          Decimal("0.380"),  "Umweltbundesamt 2024"),
    ("purchased_electricity",   "global", 2025, "kWh",          Decimal("0.475"),  "IEA 2024 global average"),
    ("business_travel_air",     "global", 2025, "passenger_km", Decimal("0.158"),  "DEFRA 2024, short-haul economy"),
    ("business_travel_lodging", "global", 2025, "room_nights",  Decimal("13.300"), "Cornell Hotel Sustainability Benchmarking 2023"),
    ("business_travel_ground",  "global", 2025, "km",           Decimal("0.171"),  "DEFRA 2024, average car"),
    ("purchased_goods_spend",   "global", 2025, "usd",          Decimal("0.450"),  "EPA USEEIO v2.0.1 (spend-based, generic)"),
]


# IATA → (name, city, country, lat, lon)
AIRPORTS = [
    ("ATL", "Hartsfield-Jackson Atlanta International", "Atlanta",        "US",  33.6407,  -84.4277),
    ("LAX", "Los Angeles International",                "Los Angeles",    "US",  33.9416, -118.4085),
    ("ORD", "O'Hare International",                     "Chicago",        "US",  41.9742,  -87.9073),
    ("DFW", "Dallas/Fort Worth International",          "Dallas",         "US",  32.8998,  -97.0403),
    ("JFK", "John F. Kennedy International",            "New York",       "US",  40.6413,  -73.7781),
    ("SFO", "San Francisco International",              "San Francisco",  "US",  37.6213, -122.3790),
    ("SEA", "Seattle-Tacoma International",             "Seattle",        "US",  47.4502, -122.3088),
    ("BOS", "Logan International",                      "Boston",         "US",  42.3656,  -71.0096),
    ("LHR", "Heathrow",                                  "London",         "GB",  51.4700,   -0.4543),
    ("LGW", "Gatwick",                                   "London",         "GB",  51.1537,   -0.1821),
    ("CDG", "Charles de Gaulle",                         "Paris",          "FR",  49.0097,    2.5479),
    ("FRA", "Frankfurt am Main",                         "Frankfurt",      "DE",  50.0379,    8.5622),
    ("MUC", "Franz Josef Strauss",                       "Munich",         "DE",  48.3538,   11.7861),
    ("AMS", "Schiphol",                                  "Amsterdam",      "NL",  52.3105,    4.7683),
    ("MAD", "Adolfo Suarez Madrid-Barajas",              "Madrid",         "ES",  40.4719,   -3.5626),
    ("FCO", "Leonardo da Vinci",                          "Rome",           "IT",  41.8003,   12.2389),
    ("ZRH", "Zurich",                                     "Zurich",         "CH",  47.4581,    8.5555),
    ("DXB", "Dubai International",                        "Dubai",          "AE",  25.2532,   55.3657),
    ("DOH", "Hamad International",                        "Doha",           "QA",  25.2731,   51.6080),
    ("SIN", "Singapore Changi",                           "Singapore",      "SG",   1.3644,  103.9915),
    ("HKG", "Hong Kong International",                    "Hong Kong",      "HK",  22.3080,  113.9185),
    ("NRT", "Narita International",                       "Tokyo",          "JP",  35.7720,  140.3929),
    ("HND", "Tokyo Haneda",                               "Tokyo",          "JP",  35.5494,  139.7798),
    ("ICN", "Incheon International",                      "Seoul",          "KR",  37.4602,  126.4407),
    ("PEK", "Beijing Capital",                            "Beijing",        "CN",  40.0801,  116.5846),
    ("PVG", "Shanghai Pudong",                            "Shanghai",       "CN",  31.1443,  121.8083),
    ("SYD", "Kingsford Smith",                            "Sydney",         "AU", -33.9399,  151.1753),
    ("BLR", "Kempegowda International",                   "Bangalore",      "IN",  13.1989,   77.7068),
    ("BOM", "Chhatrapati Shivaji Maharaj",                "Mumbai",         "IN",  19.0896,   72.8656),
    ("DEL", "Indira Gandhi International",                "Delhi",          "IN",  28.5562,   77.1000),
]


PLANTS = {
    "acme":   [("1000", "Acme Düsseldorf Plant", "DE"),
               ("1100", "Acme Stuttgart Plant",  "DE"),
               ("2000", "Acme Chicago Plant",    "US"),
               ("2100", "Acme Atlanta Plant",    "US")],
    "globex": [("4000", "Globex Singapore HQ",   "SG"),
               ("4100", "Globex Tokyo Office",   "JP")],
}


DEMO_USERS = [
    # (org_slug, email, password, role)
    ("acme",   "analyst@acme.test",   "breathe", MembershipRole.ANALYST),
    ("acme",   "admin@acme.test",     "breathe", MembershipRole.ADMIN),
    ("globex", "analyst@globex.test", "breathe", MembershipRole.ANALYST),
]


class Command(BaseCommand):
    help = "Seed reference data and demo orgs/users. Idempotent."

    @transaction.atomic
    def handle(self, *args, **opts) -> None:
        # Seeding writes Memberships + PlantCodes across multiple orgs without
        # a request context (so the RLS GUC isn't set per-org). FORCE RLS on
        # those tables would block every INSERT. We disable row-security for
        # the duration of this transaction. SET LOCAL is auto-rolled-back at
        # commit; it does not leak to other sessions or other transactions.
        with connection.cursor() as cur:
            cur.execute("SET LOCAL row_security = off")

        units = {}
        for code, label, dimension in UNITS:
            u, _ = CanonicalUnit.objects.get_or_create(
                code=code, defaults={"label": label, "dimension": dimension}
            )
            units[code] = u
        self.stdout.write(f"units: {len(units)}")

        cats = {}
        for code, label, scope, unit_code, ghg in CATEGORIES:
            c, _ = EmissionCategory.objects.get_or_create(
                code=code,
                defaults={"label": label, "scope": scope,
                          "default_unit": units[unit_code], "ghg_protocol_ref": ghg},
            )
            cats[code] = c
        self.stdout.write(f"categories: {len(cats)}")

        for cat_code, region, year, unit_code, kg, source in FACTORS:
            EmissionFactor.objects.get_or_create(
                category=cats[cat_code], region=region, year=year, unit=units[unit_code],
                defaults={"kg_co2e_per_unit": kg, "source": source,
                          "effective_from": date(year, 1, 1)},
            )
        self.stdout.write(f"factors: {EmissionFactor.objects.count()}")

        for iata, name, city, country, lat, lon in AIRPORTS:
            Airport.objects.get_or_create(
                iata=iata,
                defaults={"name": name, "city": city, "country": country,
                          "latitude": lat, "longitude": lon},
            )
        self.stdout.write(f"airports: {Airport.objects.count()}")

        # Demo orgs
        orgs = {}
        for slug, name in [("acme", "Acme Corp"), ("globex", "Globex Industries")]:
            o, _ = Organization.objects.get_or_create(slug=slug, defaults={"name": name})
            orgs[slug] = o
        self.stdout.write(f"orgs: {len(orgs)}")

        for slug, plants in PLANTS.items():
            for code, name, country in plants:
                PlantCode.objects.get_or_create(
                    organization=orgs[slug], code=code,
                    defaults={"facility_name": name, "country": country},
                )

        User = get_user_model()
        for slug, email, password, role in DEMO_USERS:
            u, created = User.objects.get_or_create(
                username=email,
                defaults={"email": email, "first_name": email.split("@")[0].title()},
            )
            if created:
                u.set_password(password)
                u.save()
            Membership.objects.get_or_create(
                organization=orgs[slug], user=u, defaults={"role": role}
            )

        self.stdout.write(self.style.SUCCESS("seed_demo complete."))
