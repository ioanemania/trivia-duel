from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.UserRegisterView.as_view(), name="user-register"),
    path("ranking/", views.UserRankingView.as_view(), name="user-ranking"),
]
