from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer

import api.models as models
import api.serializers as serializers

@database_sync_to_async
def get_notifications(user, conversation, notified):
    return models.Notification.objects.filter(recipient=user).filter(conversation=conversation).filter(notified=notified)

@database_sync_to_async
def create_notification(recipient, conversation, title, text, redirect_url):
    return models.Notification.objects.create(recipient=recipient, conversation=conversation,\
                                              title=title, text=text, redirect_url=redirect_url)

async def broadcast_message(msg, serializer_data):
    group_name = 'chat_%s' % msg.conversation.id
    channel_layer = get_channel_layer()
    content = {
        "type": "new_message",
        "payload": serializer_data,
    }
    await channel_layer.group_send(group_name, {
        "type": "notify",
        "content": content,
    })
    # create notification if user if offlie
    for user in msg.conversation.users.exclude(id=msg.author.id).all():
        if user.online < 1:
            q = await get_notifications(user, msg.conversation, False)
            if not q.exists():
                await create_notification(recipient=user, conversation=msg.conversation,\
                                          title="New Message",\
                                          text="New message from {}".format(msg.author),\
                                          redirect_url="/messages/c/{}".format(msg.conversation.id))
        else:
            n = await create_notification(recipient=user, conversation=msg.conversation,\
                                    title="New Message from {}".format(msg.author.first_name),\
                                    text="{}".format(msg.text),\
                                    redirect_url="/messages/c/{}".format(msg.conversation.id))
            # s = serializers.NotificationSerializer(n, many=False, context={'request': None})
            # await notify_user(user.id, s.data)

async def broadcast_deleted_message(conversationId, msgId):
    group_name = 'chat_%s' % conversationId
    channel_layer = get_channel_layer()
    content = {
        "type": "deleted_message",
        "payload": msgId,
    }
    await channel_layer.group_send(group_name, {
        "type": "notify",
        "content": content,
    })



async def send_group_notification(group_name, notification):
    channel_layer = get_channel_layer()
    content = {
        "type": "notification",
        "payload": notification,
    }
    await channel_layer.group_send(group_name, {
        "type": "notify",
        "content": content,
    })

async def notify_user(user_id, notification_serializer_data):
    channel_layer = get_channel_layer()
    await send_group_notification('user_%s' % user_id, notification_serializer_data)

class ChatConsumer(AsyncJsonWebsocketConsumer):
    user_token = None
    room_group_name = None

    user_room_group = None

    @database_sync_to_async
    def change_user_online_status(self, n):
        if self.user:
            self.user.online = self.user.online + n
            self.user.save(update_fields=['online'])


    @database_sync_to_async
    def get_conversation(self, id):
        try:
            conv = models.Conversation.objects.get(id=id)
            return conv
        except:
            return None

    @database_sync_to_async
    def get_notification(self, id):
        try:
            result = models.Notification.objects.get(id=id)
            return result
        except:
            return None

    @database_sync_to_async
    def set_notification_notified(self, id):
        try:
            result = models.Notification.objects.get(id=id)
            if getattr(result, 'conversation', None):
                result.delete()
                return None
            else:
                result.notified = True
                result.save(update_fields=['notified'])
                return result
        except:
            return None

    async def connect(self):
        self.user = self.scope["user"]

        if "token" in self.scope:
            self.user_token = self.scope["token"]

        # guard
        if not self.user or self.user.is_anonymous:
            await self.close()
        else:
            try:
                protocol = self.scope['subprotocols'][0]
                self.user_room_group = 'user_%s' % self.user.id
                await self.channel_layer.group_add(
                    self.user_room_group,
                    self.channel_name
                )
                # print('connected to room {}, {}'.format(self.user_room_group, self.channel_name))
                await self.accept(protocol)
                await self.notify_using_channel_layer({
                    "type": "connected",
                    "payload": None
                })
                await self.change_user_online_status(1)
            except:
                await self.close()

    async def join_room(self, room_name):
        await self.leave_group()

        # Join room group
        # print('join room {}'.format(room_name))
        self.room_name = room_name

        self.conversation = await self.get_conversation(self.room_name)

        if not self.conversation or not self.conversation.users.filter(id=self.user.id).exists():
            await self.close()
        else:
            self.room_group_name = 'chat_%s' % self.room_name

            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            # print('connected to room {}'.format(self.room_group_name))
            content = {
                "type": "joined_room",
                "payload": {
                    "room_name": room_name
                },
            }
            await self.notify_using_channel_layer(content)


    async def receive_json(self, content, **kwargs):
        """
        This handles data sent over the wire from the client.

        We need to validate that the received data is of the correct
        form. You can do this with a simple DRF serializer.

        We then need to use that validated data to confirm that the
        global/ng user (available in self.scope["user"] because of
        the use of channels.auth.AuthMiddlewareStack in routing) is
        allowed to subscribe to the requested object.
        """
        # message = content['message']
        print('got')
        print(content)
        if content['type'] == 'join_room_request':
            payload = content["payload"]
            room_name = payload["room_name"]
            await self.join_room(room_name)
        elif content['type'] == 'leave_room':
            await self.leave_group()
        elif content['type'] == 'notification_ack':
            payload = content["payload"]
            await self.notification_ack(payload)

        # serializer = self.get_serializer(data=content)
        # if not serializer.is_valid():
        #     return
        # # Define this method on your serializer:
        # group_name = serializer.get_group_name()
        # # The AsyncJsonWebsocketConsumer parent class has a
        # # self.groups list already. It uses it in cleanup.
        # self.groups.append(group_name)
        # # This actually subscribes the requesting socket to the
        # # named group:
        # await self.channel_layer.group_add(
        #     group_name,
        #     self.channel_name,
        # )

    async def notification_ack(self, payload):
        notification_id = payload["notification_id"]
        if notification_id:
            await self.set_notification_notified(notification_id)

    async def disconnect(self, close_code):
        await self.change_user_online_status(-1)
        await self.leave_group()

    async def leave_group(self):
        # Leave room group
        if self.room_group_name and self.channel_name:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def notify_using_channel_layer(self, content):
        await self.channel_layer.send(self.channel_name, {
            "type": "notify",
            "content": content,
        })

    async def notify(self, event):
        """
        This handles calls elsewhere in this codebase that look
        like:

            channel_layer.group_send(group_name, {
                'type': 'notify',  # This routes it to this handler.
                'content': json_message,
            })

        Don't try to directly use send_json or anything; this
        decoupling will help you as things grow.
        """
        await self.send_json(event["content"])
