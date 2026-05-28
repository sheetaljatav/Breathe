from django.urls import path

from . import views

urlpatterns = [
    path("batches/", views.BatchListView.as_view(), name="batches-list"),
    path("batches/<int:pk>/", views.BatchDetailView.as_view(), name="batches-detail"),
    path("ingest/upload", views.UploadView.as_view(), name="ingest-upload"),
    path("ingest/paste", views.PasteView.as_view(), name="ingest-paste"),
]
