from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import CustomUser, Profile, Role


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
	list_display = ('name', 'code', 'is_system_role', 'updated_at')
	search_fields = ('name', 'code')
	list_filter = ('is_system_role',)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
	list_display = ('user', 'full_name', 'organization', 'updated_at')
	search_fields = ('user__email', 'full_name', 'organization')


@admin.register(CustomUser)
class CustomUserAdmin(DjangoUserAdmin):
	model = CustomUser
	ordering = ('email',)
	list_display = ('email', 'username', 'is_staff', 'is_active', 'is_verified', 'is_premium')
	list_filter = ('is_staff', 'is_active', 'is_verified', 'is_premium', 'role')
	search_fields = ('email', 'username', 'first_name', 'last_name')
	fieldsets = (
		(None, {'fields': ('email', 'password')}),
		('Identity', {'fields': ('username', 'first_name', 'last_name', 'role')}),
		('Status', {'fields': ('is_verified', 'is_premium', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
		('Important dates', {'fields': ('last_login', 'date_joined')}),
	)
	add_fieldsets = (
		(None, {
			'classes': ('wide',),
			'fields': ('email', 'username', 'password1', 'password2', 'role', 'is_active', 'is_staff'),
		}),
	)
