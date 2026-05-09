from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView

from .models import Profile
from .serializers import AccountProfileSerializer, EmailTokenObtainPairSerializer, RegisterSerializer

User = get_user_model()


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


class GuestSessionView(APIView):
	"""
	Create an ephemeral authenticated guest user and return JWT pair (same shape as login).
	Frontend enforces guest query limits in sessionStorage.
	"""

	permission_classes = [permissions.AllowAny]

	def post(self, request):
		uid = uuid.uuid4().hex[:16]
		email = f'guest_{uid}@guest.lexiai.local'
		username = f'guest_{uid}'
		user = User.objects.create_user(
			email=email,
			username=username,
			first_name='Guest',
			last_name='User',
		)
		Profile.objects.get_or_create(user=user, defaults={'full_name': 'Guest User'})
		refresh = RefreshToken.for_user(user)
		payload = {
			'access': str(refresh.access_token),
			'refresh': str(refresh),
			'user': AccountProfileSerializer(user).data,
		}
		return Response(payload, status=status.HTTP_200_OK)
