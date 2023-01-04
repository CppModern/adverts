import datetime

from django.contrib.auth.models import (
    BaseUserManager, AbstractBaseUser
)
from django.db import models


class MyUserManager(BaseUserManager):
    def create_user(self, telegram_id, fname, username, password=None,):
        """
        Creates and saves a User with the given telegram_id, date of
        birth and password.
        """
        if not telegram_id:
            raise ValueError('Users must have Telegram ID')

        user = self.model(
            telegram_id=telegram_id,
            fname=fname,
            username=username or ""
        )

        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, telegram_id, fname, username, password=None):

        user = self.create_user(
            telegram_id,
            fname=fname,
            password=password,
            username=username
        )
        user.is_admin = True
        user.save(using=self._db)
        return user


class MyUser(AbstractBaseUser):
    telegram_id = models.CharField(
        verbose_name="user id (telegram)",
        max_length=20,
        unique=True, primary_key=True, default="1000"
    )
    date_added = models.DateField(default=datetime.date.today)
    is_active = models.BooleanField(default=True)
    fname = models.CharField(max_length=100, blank=True)
    username = models.CharField(max_length=200, blank=True, default="")
    is_admin = models.BooleanField(default=False)
    balance = models.FloatField(default=float)
    status = models.CharField(choices=(("regular", "Regular"), ("vip", "VIP")), max_length=20, default="regular")
    discount = models.FloatField(default=0.0)
    banned = models.BooleanField(default=False)

    objects = MyUserManager()

    USERNAME_FIELD = 'telegram_id'
    REQUIRED_FIELDS = ['fname', 'username']

    def __str__(self):
        return self.username or f"{self.fname} [{self.telegram_id}]"

    def has_perm(self, perm, obj=None):
        """Does the user have a specific permission?"""
        return True

    def has_module_perms(self, app_label):
        """Does the user have permissions to view the app `app_label`?"""
        # Simplest possible answer: Yes, always
        return True

    @property
    def is_staff(self):
        """Is the user a member of staff?"""
        # Simplest possible answer: All admins are staff
        return self.is_admin
