"""
Hand-written initial migration for emissions. See core/migrations/0001_initial.py
for the rationale.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import core.tenancy


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CanonicalUnit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=24, unique=True)),
                ("label", models.CharField(max_length=64)),
                ("dimension", models.CharField(choices=[
                    ("energy", "Energy"), ("volume", "Volume"), ("mass", "Mass"),
                    ("distance", "Distance"), ("passenger_distance", "Passenger-distance"),
                    ("count", "Count"), ("currency", "Currency"),
                ], max_length=24)),
            ],
            options={"db_table": "canonical_unit", "ordering": ("dimension", "code")},
        ),
        migrations.CreateModel(
            name="EmissionCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=64, unique=True)),
                ("label", models.CharField(max_length=128)),
                ("scope", models.IntegerField(choices=[
                    (1, "Scope 1 (direct)"),
                    (2, "Scope 2 (purchased energy)"),
                    (3, "Scope 3 (indirect / value chain)"),
                ])),
                ("ghg_protocol_ref", models.CharField(blank=True, max_length=128)),
                ("default_unit", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="+", to="emissions.canonicalunit")),
            ],
            options={"db_table": "emission_category", "ordering": ("scope", "code")},
        ),
        migrations.CreateModel(
            name="EmissionFactor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("region", models.CharField(max_length=16)),
                ("year", models.IntegerField()),
                ("kg_co2e_per_unit", models.DecimalField(decimal_places=6, max_digits=18)),
                ("source", models.CharField(max_length=128)),
                ("effective_from", models.DateField()),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("category", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="factors", to="emissions.emissioncategory")),
                ("unit", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="+", to="emissions.canonicalunit")),
            ],
            options={
                "db_table": "emission_factor",
                "ordering": ("category", "region", "-year"),
                "unique_together": {("category", "region", "year", "unit")},
            },
        ),
        migrations.AddIndex(
            model_name="emissionfactor",
            index=models.Index(
                fields=["category", "region", "year"],
                name="emissions_e_categor_d5ad8d_idx"),
        ),
        migrations.CreateModel(
            name="PlantCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=8)),
                ("facility_name", models.CharField(max_length=200)),
                ("country", models.CharField(max_length=2)),
                ("organization", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="plant_codes", to="core.organization")),
            ],
            options={
                "db_table": "plant_code",
                "unique_together": {("organization", "code")},
            },
        ),
        migrations.CreateModel(
            name="Airport",
            fields=[
                ("iata", models.CharField(max_length=3, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=128)),
                ("city", models.CharField(max_length=64)),
                ("country", models.CharField(max_length=2)),
                ("latitude", models.DecimalField(decimal_places=6, max_digits=9)),
                ("longitude", models.DecimalField(decimal_places=6, max_digits=9)),
            ],
            options={"db_table": "airport"},
        ),
        migrations.CreateModel(
            name="ActivityRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("activity_date", models.DateField()),
                ("period_start", models.DateField(blank=True, null=True)),
                ("period_end", models.DateField(blank=True, null=True)),
                ("value", models.DecimalField(decimal_places=6, max_digits=18)),
                ("emissions_kg_co2e", models.DecimalField(blank=True, decimal_places=3, max_digits=18, null=True)),
                ("facility_code", models.CharField(blank=True, max_length=32)),
                ("notes", models.TextField(blank=True)),
                ("review_state", models.CharField(choices=[
                    ("pending", "Pending review"), ("flagged", "Flagged"),
                    ("approved", "Approved"), ("rejected", "Rejected"),
                    ("locked", "Locked for audit"),
                ], default="pending", max_length=16)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("version", models.IntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("category", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="+", to="emissions.emissioncategory")),
                ("emission_factor", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="+", to="emissions.emissionfactor")),
                ("organization", models.ForeignKey(
                    db_index=True, on_delete=django.db.models.deletion.PROTECT,
                    related_name="+", to="core.organization")),
                ("reviewed_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to=settings.AUTH_USER_MODEL)),
                ("source_record", models.OneToOneField(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="activity", to="ingestion.sourcerecord")),
                ("unit", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="+", to="emissions.canonicalunit")),
            ],
            options={
                "db_table": "activity_record",
                "ordering": ("-activity_date", "-id"),
            },
            managers=[("objects", core.tenancy.TenantManager())],
        ),
        migrations.AddIndex(
            model_name="activityrecord",
            index=models.Index(
                fields=["organization", "review_state", "-activity_date"],
                name="ar_queue_idx"),
        ),
        migrations.AddIndex(
            model_name="activityrecord",
            index=models.Index(
                fields=["organization", "category", "activity_date"],
                name="ar_reporting_idx"),
        ),
        migrations.AddIndex(
            model_name="activityrecord",
            index=models.Index(
                fields=["organization", "facility_code", "activity_date"],
                name="ar_facility_idx"),
        ),
    ]
