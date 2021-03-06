from allauth.account.adapter import DefaultAccountAdapter


class CustomUserAccountAdapter(DefaultAccountAdapter):

    def save_user(self, request, user, form, commit=True):
        """
        Saves a new `User` instance using information provided in the
        signup form.
        """
        from allauth.account.utils import user_field

        user = super().save_user(request, user, form, False)
        user_field(user, 'role', request.data.get('role', ''))
        user_field(user, 'phone', request.data.get('phone', ''))
        user_field(user, 'bio', request.data.get('bio', ''))
        user_field(user, 'uid', request.data.get('uid', ''))
        user.save()
        return user

