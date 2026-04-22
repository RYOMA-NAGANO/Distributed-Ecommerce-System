from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    """
    Log in with email (field still named username on the form) or legacy username.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        UserModel = get_user_model()
        username = username.strip()
        if not username:
            return None

        user = None
        if "@" in username:
            user = UserModel.objects.filter(email__iexact=username).first()
        else:
            user = UserModel.objects.filter(username__iexact=username).first()

        if user is None:
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
