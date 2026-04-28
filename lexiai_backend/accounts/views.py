from __future__ import annotations

from rest_framework import generics, permissions
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView

from .serializers import AccountProfileSerializer, EmailTokenObtainPairSerializer, RegisterSerializer


class RegisterView(generics.CreateAPIView):
	serializer_class = RegisterSerializer
	permission_classes = [permissions.AllowAny]


class LoginView(TokenObtainPairView):
	serializer_class = EmailTokenObtainPairSerializer
	permission_classes = [permissions.AllowAny]


class RefreshView(TokenRefreshView):
	permission_classes = [permissions.AllowAny]


class LogoutView(TokenBlacklistView):
	permission_classes = [permissions.IsAuthenticated]


class ProfileView(generics.RetrieveUpdateAPIView):
	serializer_class = AccountProfileSerializer
	permission_classes = [permissions.IsAuthenticated]

	def get_object(self):
		return self.request.user
