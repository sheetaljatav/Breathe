from rest_framework.pagination import CursorPagination

class DefaultCursorPagination(CursorPagination):
    # `-id` is monotonic (bigserial) and present on every model,
    # so it's a safe global default — same key AuditLog uses for Meta.ordering.
    ordering = "-id"
    page_size = 50