from django.urls import path

from . import views

urlpatterns = [
    path("orgs/", views.OrgListView.as_view(), name="orgs-list"),
    path("orgs/current/", views.CurrentOrgView.as_view(), name="orgs-current"),
]
