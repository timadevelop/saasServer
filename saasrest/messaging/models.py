"""Models"""
from django.db import models

from authentication.models import User

from django.utils.translation import ugettext as _

from saas_core.images_compression import compress_image

class Conversation(models.Model):
    """Conversation"""
    title = models.TextField(max_length=30, blank=False)
    # related messages field
    # TODO: rm from users current user on response
    users = models.ManyToManyField(User, related_name="conversations")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Message(models.Model):
    """Message"""
    author = models.ForeignKey(
        User,
        null=False,
        on_delete=models.CASCADE,
        related_name='messages')

    conversation = models.ForeignKey(
        Conversation,
        null=False,
        on_delete=models.CASCADE,
        related_name='messages')

    text = models.TextField(max_length=1000, blank=True)
    # related images field

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_text(self):
        # TODO: rm null
        if not self.text or self.text == 'null':
            return "{} {}".format(self.author.first_name, _("sent you attachment"))
        else:
            print(self.text)
            return self.text


class MessageImage(models.Model):
    """Message Image"""
    message = models.ForeignKey(Message,
                                on_delete=models.CASCADE,
                                null=False,
                                related_name='images')
    image = models.ImageField(upload_to='images/messages/%Y/%m/%d')

    def save(self, *args, **kwargs):
        """Compress on save"""
        if not self.id:
            self.image = compress_image(self.image)
        super().save(*args, **kwargs)
