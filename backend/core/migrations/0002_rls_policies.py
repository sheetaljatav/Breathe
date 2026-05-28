"""
Enable Postgres row-level security on every tenant-scoped table.

This is the SECOND of two independent tenant-isolation layers; the first is
TenantQuerySet at the ORM layer. RLS is here as defense in depth — to catch
the bug where an engineer forgets `.for_org()` or writes raw SQL.

Mechanism:
  1. ALTER TABLE ... ENABLE ROW LEVEL SECURITY
  2. ALTER TABLE ... FORCE ROW LEVEL SECURITY  ◄── applies even to the table
                                                   owner. Superusers still
                                                   bypass, which is why
                                                   production must use a
                                                   non-superuser role.
  3. CREATE POLICY tenant_isolation FOR ALL
     USING  (organization_id::text = current_setting('app.current_org_id', true))
     WITH CHECK (organization_id::text = current_setting('app.current_org_id', true))

The GUC `app.current_org_id` is set per-request by TenantRLSMiddleware. If it's
absent or empty, `current_setting(name, true)` returns NULL, and the comparison
`anything::text = NULL` is NULL → row excluded. So an anonymous or unscoped
request sees zero rows. That is the correct failure mode.

The list of tables here is the union across apps. When adding a new tenant
model, add an entry here in a follow-up migration with the same shape.
"""

from django.db import migrations


# Tables covered by the standard tenant policy:
# rows are visible iff organization_id = current_setting('app.current_org_id').
STANDARD_TABLES = [
    "audit_log",
    "ingestion_batch",
    "source_record",
    "parse_error",
    "activity_record",
    "plant_code",
]


def _enable_standard(table: str) -> str:
    return f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS tenant_isolation ON {table};
        CREATE POLICY tenant_isolation ON {table}
            FOR ALL
            USING (organization_id::text = current_setting('app.current_org_id', true))
            WITH CHECK (organization_id::text = current_setting('app.current_org_id', true));
    """


def _disable_standard(table: str) -> str:
    return f"""
        DROP POLICY IF EXISTS tenant_isolation ON {table};
        ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
    """


# membership is special: a user must be able to read their OWN memberships
# across orgs (powering the org switcher), even while their current request
# is pinned to one org. The OR-clause expresses exactly that: "row visible
# if it's in the current org, OR if it's your own membership row."
MEMBERSHIP_INSTALL = """
    ALTER TABLE membership ENABLE ROW LEVEL SECURITY;
    ALTER TABLE membership FORCE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation ON membership;
    CREATE POLICY tenant_isolation ON membership
        FOR ALL
        USING (
            organization_id::text = current_setting('app.current_org_id', true)
            OR user_id::text       = current_setting('app.current_user_id', true)
        )
        WITH CHECK (
            organization_id::text = current_setting('app.current_org_id', true)
        );
"""

MEMBERSHIP_UNINSTALL = """
    DROP POLICY IF EXISTS tenant_isolation ON membership;
    ALTER TABLE membership DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    """
    Depends on the initial migrations of every app whose tables are listed
    above. If you add a new tenant-scoped model in an app, append a new
    RunSQL pair in a follow-up migration rather than editing this one.
    """

    dependencies = [
        ("core", "0001_initial"),
        ("ingestion", "0001_initial"),
        ("emissions", "0001_initial"),
    ]

    operations = [
        *[migrations.RunSQL(sql=_enable_standard(t), reverse_sql=_disable_standard(t))
          for t in STANDARD_TABLES],
        migrations.RunSQL(sql=MEMBERSHIP_INSTALL, reverse_sql=MEMBERSHIP_UNINSTALL),
    ]
