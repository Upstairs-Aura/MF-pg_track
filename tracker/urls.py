from django.urls import path
from . import views

urlpatterns = [
    path("", views.homepage, name="homepage"),
    path("login/", views.login_page, name="login"),
    path("location/<int:location_id>/", views.location_detail, name="location_detail"),
    path("location/<int:location_id>/<str:heading_slug>/", views.task_list, name="task_list"),
    path("task/<int:task_id>/", views.task_detail, name="task_detail"),
    path("archive/", views.archive, name="archive"),
]
from django.urls import path
from . import views

urlpatterns = [
    path("", views.homepage, name="homepage"),
    path("login/", views.login_page, name="login"),
    path("logout/", views.logout_view, name="logout"),   # ← add this
    path("location/<int:location_id>/", views.location_detail, name="location_detail"),
    path("location/<int:location_id>/<str:heading_slug>/", views.task_list, name="task_list"),
    path("task/<int:task_id>/", views.task_detail, name="task_detail"),
    path("archive/", views.archive, name="archive"),
]