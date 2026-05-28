from django.contrib import admin

from .models import AuditLog, Membership, Organization


@admin.register(Organization)
class OrgAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "created_at")
    list_filter = ("role", "organization")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "organization", "actor_user", "action", "target_type", "target_id")
    list_filter = ("action", "organization", "target_type")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
