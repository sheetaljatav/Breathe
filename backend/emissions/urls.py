from django.urls import path

from . import views

urlpatterns = [
    path("activities/", views.QueueView.as_view(), name="activities-list"),
    path("activities/<int:pk>/", views.ActivityDetailView.as_view(), name="activities-detail"),
    path("activities/<int:pk>/approve", views.ApproveView.as_view(), name="activities-approve"),
    path("activities/<int:pk>/flag", views.FlagView.as_view(), name="activities-flag"),
    path("activities/<int:pk>/reject", views.RejectView.as_view(), name="activities-reject"),
    path("activities/<int:pk>/lock", views.LockView.as_view(), name="activities-lock"),
    path("activities/<int:pk>/unlock", views.UnlockView.as_view(), name="activities-unlock"),
    path("overview", views.OverviewView.as_view(), name="overview"),
    path("settings/factors", views.FactorListView.as_view(), name="factors-list"),
    path("settings/lookups", views.LookupsView.as_view(), name="lookups"),
    path("settings/units", views.UnitsView.as_view(), name="units"),
]
