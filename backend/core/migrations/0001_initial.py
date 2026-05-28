"""
Hand-written initial migration for core.

Rationale: we ship 0002_rls_policies and 0003_audit_immutability as authored
migrations that depend on 0001_initial existing. If we relied on
`python manage.py makemigrations` to generate 0001, the migration graph couldn't
be built before that command runs (0002's dependency on a nonexistent 0001
becomes a dummy node and the autodetector fails). Pre-generating 0001 here
makes the workflow `python manage.py migrate` only — no makemigrations needed
on first deploy.

When models are later modified, `makemigrations core` will produce 0004_*,
0005_*, etc., on top of this.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import core.tenancy


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Organization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("slug", models.SlugField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "organization", "ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="Membership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(
                    choices=[("analyst", "Analyst"), ("admin", "Admin")], max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="memberships", to="core.organization")),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="memberships", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "membership",
                "unique_together": {("organization", "user")},
            },
        ),
        migrations.AddIndex(
            model_name="membership",
            index=models.Index(fields=["user", "organization"], name="membership_user_id_eb1e5f_idx"),
        ),
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("request_id", models.CharField(db_index=True, max_length=64)),
                ("action", models.CharField(choices=[
                    ("CREATED", "Created"), ("UPDATED", "Updated"), ("APPROVED", "Approved"),
                    ("FLAGGED", "Flagged"), ("REJECTED", "Rejected"), ("LOCKED", "Locked"),
                    ("UNLOCKED", "Unlocked"), ("REPARSED", "Re-parsed"), ("LOGGED_IN", "Logged in"),
                ], max_length=24)),
                ("target_type", models.CharField(max_length=64)),
                ("target_id", models.BigIntegerField()),
                ("before", models.JSONField(blank=True, null=True)),
                ("after", models.JSONField(blank=True, null=True)),
                ("reason", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("actor_user", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="+", to="core.organization")),
            ],
            options={"db_table": "audit_log", "ordering": ("-id",)},
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["organization", "target_type", "target_id", "-created_at"],
                name="auditlog_target_idx"),
        ),
    ]
