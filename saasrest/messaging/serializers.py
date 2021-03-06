from rest_framework import serializers

import authentication.serializers

from .models import Conversation, Message

from django.utils.translation import ugettext as _

from saas_core.models import Image
from saas_core.serializers import ImageSerializer

class ConversationSerializer(serializers.HyperlinkedModelSerializer):

    notifications_count = serializers.SerializerMethodField()
    last_msg = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ('id', 'url', 'title', 'users', 'created_at', 'last_msg', 'updated_at', 'notifications_count', )
        required_fields = ('users', 'title')
        extra_kwargs = {field: {'required': True} for field in required_fields}

    def to_representation(self, instance):
        response = super().to_representation(instance)
        user = self.get_current_user()
        if (self.context['request']) and user:
            users = instance.users.exclude(id=user.id)
            response['users'] = authentication.serializers.serialize_simple_user(users=users, many=True, context=self.context)
        return response

    def get_notifications_count(self, instance):
        user = self.get_current_user()
        if not user:
            return 0
        return instance.notifications.filter(recipient=user).count()

    def get_last_msg(self, instance):
        try:
            msg = instance.messages.last()
            return msg.get_text()
        except:
            return instance.title

    def get_current_user(self):
        """Gets Current user from request"""
        user = None
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            user = request.user
            return user
        return None

    def validate_users(self, value):
        """Validate users field"""
        request = self.context.get("request")
        if not request or not hasattr(request, "user"):
            raise serializers.ValidationError(_("Login please"))

        user = request.user

        if len(value) != 2:
            raise serializers.ValidationError(_("2 Users required"))

        users = value
        request_user_is_in_users = False
        for u in users:
            if u.id == user.id:
                request_user_is_in_users = True

        if not request_user_is_in_users:
            raise serializers.ValidationError(
                "Users field must contain request user")

        q = Conversation.objects.all()
        for u in users:
            q = q.filter(users=u)

        if q.exists():
            raise serializers.ValidationError(_("Conversation exists"))

        return value

class MessageSerializer(serializers.HyperlinkedModelSerializer):
    """Message Serializer"""
    is_my_message = serializers.SerializerMethodField()
    images = ImageSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = ('id', 'url', 'author', 'author_id', 'conversation', 'text',
                  'created_at', 'updated_at', 'is_my_message', 'images')
        required_fields = ('conversation', 'text', )
        extra_kwargs = {field: {'required': True} for field in required_fields}
        read_only_fields = ('id', 'url', 'author',
                            'created_at', 'updated_at', 'is_my_message')

    def validate_conversation(self, value):
        user = self.get_current_user()

        is_in_conversation = value.users.all().filter(id=user.id).exists()
        if not is_in_conversation:
            raise serializers.ValidationError(_("You're not in conversation"))

        return value

    def validate_author(self, value):
        user = self.get_current_user()
        if user.id != value.id:
            raise serializers.ValidationError(_("Request user must be author"))

        return value

    def create(self, validated_data):
        message = super().create(validated_data)
        image_data = self.context.get('view').request.FILES
        for img in image_data.values():
            img = Image.objects.create(
                content_object=message, image=img)
        return message

    def update(self, instance, validated_data):
        message = super().update(instance, validated_data)
        image_data = self.context.get('view').request.FILES
        for img in image_data.values():
            img = Image.objects.create(
                content_object=message, image=img)
        return message

    def get_is_my_message(self, instance):
        """is my message field"""
        user = self.get_current_user()
        if not user:
            return False

        return instance.author.id == user.id

    def get_current_user(self):
        """get current user"""
        user = None
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            user = request.user
            return user
        return None

    def group_name(self, instance):
        """returns conversation group name"""
        return instance.conversation.id
