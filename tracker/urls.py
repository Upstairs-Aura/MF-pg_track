from django.urls import path
from . import views

urlpatterns = [
    path("", views.homepage, name="homepage"),
    path("login/", views.login_page, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("location/<int:location_id>/", views.location_detail, name="location_detail"),
    path("location/<int:location_id>/<str:heading_slug>/", views.task_list, name="task_list"),
    path("location/<int:location_id>/<str:heading_slug>/add/", views.add_task, name="add_task"),
    path("task/<int:task_id>/", views.task_detail, name="task_detail"),
    path("task/<int:task_id>/add-action-point/", views.add_action_point, name="add_action_point"),
    path("archive/", views.archive, name="archive"),
    path("archive/<int:snapshot_id>/", views.archive_detail, name="archive_detail"),
    path("location/add/", views.add_location, name="add_location"),
    path("api/online/", views.online_status, name="online_status"),
    path("completed/", views.completed_projects, name="completed_projects"),
    path("location/<int:location_id>/archive/", views.archive_location, name="archive_location"),
    path("location/<int:location_id>/restore/", views.restore_location, name="restore_location"),
    path("location/<int:location_id>/add-deliverable/", views.add_deliverable, name="add_deliverable"),
]