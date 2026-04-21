from django.db import models
from django.core.exceptions import ValidationError

class User(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    x = models.IntegerField(null=True, blank=True)
    y = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "users"

    def __str__(self):
        return f"{self.username} <{self.email}>"
