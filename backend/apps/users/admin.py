# backend/apps/users/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('phone_number', 'is_active', 'is_staff', 'date_joined')
    list_filter = ('is_active', 'is_staff')
    search_fields = ('phone_number',)
    ordering = ('-date_joined',)

    fieldsets = (
        (None, {'fields': ('phone_number', 'password')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('date_joined', 'last_login')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone_number', 'password1', 'password2', 'is_active', 'is_staff'),
        }),
    )
    readonly_fields = ('date_joined', 'last_login')