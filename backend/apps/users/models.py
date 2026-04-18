# backend/apps/users/models.py

import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    """
    Custom manager where phone_number is the unique identifier
    instead of username.
    """

    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError('Phone number is required')

        phone_number = self._normalize_phone(phone_number)
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if not extra_fields.get('is_staff'):
            raise ValueError('Superuser must have is_staff=True')
        if not extra_fields.get('is_superuser'):
            raise ValueError('Superuser must have is_superuser=True')

        return self.create_user(phone_number, password, **extra_fields)

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """
        Normalize phone to E.164 format (254XXXXXXXXX).
        Accepts: 0712345678, +254712345678, 254712345678
        """
        phone = phone.strip().replace(' ', '').replace('-', '')

        if phone.startswith('+'):
            phone = phone[1:]

        if phone.startswith('0'):
            phone = '254' + phone[1:]

        if not phone.startswith('254'):
            phone = '254' + phone

        return phone


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model using phone number as the primary identifier.
    No username, no email required — just a phone number.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    phone_number = models.CharField(
        max_length=15,
        unique=True,
        db_index=True,
        help_text="Phone number in E.164 format e.g. 254712345678"
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return self.phone_number

    def get_short_name(self):
        return self.phone_number