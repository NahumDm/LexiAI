from django.urls import path

from .views import GuestSessionView, LoginView, LogoutView, ProfileView, RefreshView, RegisterView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('guest-session/', GuestSessionView.as_view(), name='guest-session'),
    path('login/', LoginView.as_view(), name='login'),
    path('refresh/', RefreshView.as_view(), name='refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('profile/', ProfileView.as_view(), name='profile'),
]
