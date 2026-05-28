"""
Make audit_log INSERT-only at the database layer.

Why triggers instead of REVOKE on the table:
  REVOKE works per-role. In dev, the app commonly runs as superuser (which
  bypasses REVOKE), so the protection wouldn't be testable. A BEFORE UPDATE /
  DELETE trigger that RAISE EXCEPTIONs applies to *every* role, including
  superuser — except a session that explicitly disables triggers, which is
  itself a privileged operation and a deliberate, auditable act.

Why this exists in addition to the model-layer `save()` and `delete()` guards:
  Defense in depth. Future engineers will write raw SQL. They will use
  `objects.update(...)`. They will forget. Three layers means three things
  must fail before audit history is rewritten.
"""

from django.db import migrations


SQL_INSTALL = """
    CREATE OR REPLACE FUNCTION audit_log_block_modify() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION
            'audit_log is append-only (action=%, target=%.% id=%)',
            COALESCE(OLD.action, '?'),
            COALESCE(OLD.target_type, '?'), '', COALESCE(OLD.target_id, 0)
            USING ERRCODE = 'insufficient_privilege';
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log;
    CREATE TRIGGER audit_log_no_update
        BEFORE UPDATE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_block_modify();

    DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_log;
    CREATE TRIGGER audit_log_no_delete
        BEFORE DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_block_modify();
"""

SQL_UNINSTALL = """
    DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log;
    DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_log;
    DROP FUNCTION IF EXISTS audit_log_block_modify();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0002_rls_policies")]
    operations = [migrations.RunSQL(sql=SQL_INSTALL, reverse_sql=SQL_UNINSTALL)]
