from rest_framework import status, viewsets

from .models import User, Notification, Review, \
    Location, District, \
    Service, ServiceImage, ServicePromotion, \
    Post, PostImage, PostPromotion, Offer, Tag, Category, Vote

import api.models as models
from . import serializers

from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly

from .permissions import IsOwnerOrReadOnly, IsAdminUserOrReadOnly, IsOwner
from rest_framework.decorators import action
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django_filters import rest_framework as django_filters
from django.core.exceptions import PermissionDenied

from django.core.exceptions import ObjectDoesNotExist
from .paginations import MyPagination

from django.utils import timezone

from django.db.models import Q
from django.conf import settings
import json

"""
Channels
"""
from asgiref.sync import async_to_sync
from .consumers import broadcast_message, broadcast_deleted_message, notify_user


"""
Geocoder
"""
import geocoder

"""
Stripe
"""
import stripe

"""
For config view
"""
from saasrest import local_settings

"""
Email
"""
from django.template.loader import render_to_string
from django.core.mail import send_mail

from django.template.defaulttags import register
...
@register.filter
def get_item(dictionary, key):
    print('get_item')
    print(dictionary, key)
    print('_-----------------------------____')
    return dictionary.get(key, 'None')

"""
Views (TODO: split into files)
"""
class UserViewSet(viewsets.ModelViewSet):
    """
    """
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = serializers.UserSerializer
    permission_classes = (IsOwnerOrReadOnly, )

    @action(detail=False, methods=['get'])
    def me(self, request):
        user = User.objects.get(pk=request.user.pk)
        serializer = self.get_serializer(instance=user, many=False)
        return Response(serializer.data)

class LocationViewSet(viewsets.ModelViewSet):
    """
    """
    queryset = Location.objects.all().order_by('kind')
    serializer_class = serializers.LocationSerializer
    permission_classes = (IsAdminUserOrReadOnly, )
    filter_backends = (filters.SearchFilter, DjangoFilterBackend, )
    search_fields = ('name',)
    filter_fields = ()

    # create only for employee & customer.
    def perform_create(self, serializer):
        if self.request.user:
            serializer.save()
        else:
            raise PermissionDenied()

    @action(detail=False, methods=['get'], url_path='geo/(?P<geo_query>[^/]+)')
    def get_geo(self, request, geo_query):
        try:
            resp = geocoder.geonames(geo_query, country=['BG'], key='timadevelop', maxRows=10, lang='bg',
                                     featureClass=['P', 'A'], # adm and cities / village
                                     fuzzy=1.0)
                                     # isNameRequired=True)
                                     # name_startsWith=[geo_query],
        except:
            return Response(status=status.HTTP_404_NOT_FOUND)

        result = [r.json for r in resp]
        return Response(result)

class DistrictViewSet(viewsets.ModelViewSet):
    """
    """
    queryset = District.objects.all()
    serializer_class = serializers.DistrictSerializer
    permission_classes = (IsAuthenticated, IsAdminUserOrReadOnly, )
    filter_backends = (filters.SearchFilter, DjangoFilterBackend, )
    search_fields = ('name',)
    filter_fields = ()
    lookup_field = 'oblast'

    # create only for employee & customer.
    def perform_create(self, serializer):
        if self.request.user and self.request.user.is_admin:
            serializer.save()
        else:
            raise PermissionDenied()


class TagViewSet(viewsets.ModelViewSet):
    """
    """
    queryset = Tag.objects.all().order_by('-name')
    serializer_class = serializers.TagSerializer
    permission_classes = (IsAuthenticatedOrReadOnly, )
    filter_backends = (filters.SearchFilter, DjangoFilterBackend, )
    search_fields = ('name', )

    def perform_create(self, serializer):
        if self.request.user:
            serializer.save()
        else:
            raise PermissionDenied()

    @action(detail=False, methods=['get'], url_path='name/(?P<tag_name>[^/]+)')
    def get_tag_by_name(self, request, tag_name):
        try:
            tag = self.queryset.get(name=tag_name)
        except ObjectDoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = self.serializer_class(tag, many=False, context={'request': request})
        return Response(serializer.data)

class CategoryViewSet(TagViewSet):
    queryset = Category.objects.all().order_by('-name')
    serializer_class = serializers.CategorySerializer


class ServiceFilter(django_filters.FilterSet):

    class Meta:
        model = Service
        fields = ['title', 'description', 'tags', 'category', 'location__id', 'price', 'author__id']

    price = django_filters.RangeFilter()
    # default for CharFilter is to have exact lookup_type
    title = django_filters.CharFilter()
    description = django_filters.CharFilter()

    # tricky part - how to filter by related field?
    # but not by its foreign key (default)
    # `to_field_name` is crucial here
    # `conjoined=True` makes that, the more tags, the more narrow the search
    tags = django_filters.ModelMultipleChoiceFilter(
        queryset=Tag.objects.all(),
        to_field_name='name',
        conjoined=True,
        method='filter_tags'
    )

    category = django_filters.ModelMultipleChoiceFilter(
        queryset=Category.objects.all(),
        to_field_name='name',
        conjoined=True,
        method='filter_category'
    )


    def filter_tags(self, queryset, name, tags):
        if tags:
            q = queryset.distinct().filter(tags__in=tags)
            return q
        else:
            return queryset

    def filter_category(self, queryset, name, categories):
        if categories and len(categories) > 0:
            return queryset.filter(category=categories[0])
        else:
            return queryset


class ServiceViewSet(viewsets.ModelViewSet):
    """
    """
    queryset = Service.objects.all().order_by('-created_at')
    serializer_class = serializers.ServiceSerializer
    permission_classes = (IsOwnerOrReadOnly, )
    filter_backends = (filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter )
    ordering_fields = ('price', 'created_at', 'score')
    search_fields = ('title', 'description',)
    # filter_fields = ('author', 'author__id', 'location', 'tags__contain')
    filter_class = ServiceFilter

    # create only for employee & customer.
    def perform_create(self, serializer):
        if self.request.user:
            serializer.save(author=self.request.user)
        else:
            raise PermissionDenied()

    # read only
    @action(detail=False, methods=['get'])
    def my(self, request):
        if self.request.user:
            queryset = self.queryset.filter(author=self.request.user)
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = serializers.ServiceSerializer(page, many=True, context={'request': request})
                return self.get_paginated_response(serializer.data)

            serializer = serializers.ServiceSerializer(queryset, many=True, context={'request': request})
            return Response(serializer.data)
        else:
            raise PermissionDenied()

    def vote(self, request, pk, votetype):
        if self.request.user:
            current_service = self.get_object()
            if current_service.votes.filter(user=self.request.user).exists():
                return Response({'detail': 'Already voted'}, status=status.HTTP_400_BAD_REQUEST)
            vote = current_service.votes.create(activity_type=votetype, user=request.user)
            serializer = serializers.VoteSerializer(vote, many=False, context={'request': request})
            return Response(serializer.data)
        else:
            raise PermissionDenied()


    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, ])
    def upvote(self, request, pk=None):
        return self.vote(request, pk, Vote.UP_VOTE)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, ])
    def downvote(self, request, pk=None):
        return self.vote(request, pk, Vote.DOWN_VOTE)

class ServicePromotionViewSet(viewsets.ModelViewSet):
    """
    """
    queryset = ServicePromotion.objects.all()
    serializer_class = serializers.ServicePromotionSerializer
    permission_classes = (IsAuthenticated, IsOwnerOrReadOnly, )
    filter_backends = (filters.SearchFilter, DjangoFilterBackend, )
    search_fields = ()
    filter_fields = ('author', 'author__id', 'service', 'service__id', 'transaction_id' )

    def perform_create(self, serializer):
        if self.request.user:
            serializer.save(author=self.request.user)
        else:
            raise PermissionDenied()

    def filter_promotion_queryset(self, queryset, request):
        category = request.GET.get('category')
        query = request.GET.get('q')
        author_id = request.GET.get('author_id')
        tags = request.GET.getlist('tags')
        #
        if author_id:
            queryset = queryset.filter(service__author__id=author_id)
        if category:
            # filter service category
            # Always change queryset
            queryset = queryset.filter(service__category__name=category)

        if tags:
            # at least one tag from tags
            # do not change queryset if there are no services with tags
            tmp_queryset = queryset.filter(service__tags__name__in=tags)
            if tmp_queryset.exists() or not category:
                queryset = tmp_queryset

        if query:
            # filter service title
            # do not change queryset if there are no services with similar title
            tmp_queryset = queryset.filter(service__title__contains=query)
            if tmp_queryset.exists() or (not tags and not category):
                queryset = tmp_queryset

        return queryset.order_by('?')

    def list(self, request):
        queryset = self.filter_promotion_queryset(self.queryset, request)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.serializer_class(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = self.serializer_class(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def get_queryset(self):
        user = self.request.user
        if not user or user.is_anonymous:
            return None
        # todo: Q
        return self.queryset.filter(author=user)

class ServiceImageViewSet(viewsets.ModelViewSet):
    """
    """
    queryset = ServiceImage.objects.all()
    serializer_class = serializers.ServiceImageSerializer
    permission_classes = (IsOwnerOrReadOnly, )

class OfferViewSet(viewsets.ModelViewSet):
    """
    Offers view set
    (request from employee to business, from employee to customer,
     from customer to business to connect them)
    """
    queryset = Offer.objects.all().order_by('-updated_at')
    serializer_class = serializers.OfferSerializer
    permission_classes = (IsOwnerOrReadOnly, )
    filter_backends = (filters.SearchFilter, DjangoFilterBackend)
    search_fields = ('title', 'text')
    filter_fields = ('author__id', 'post__id', 'author', 'post', 'answered', 'accepted', 'is_public')

    """
    NOTE: filters income and outcome actions too
    """
    def get_queryset(self):
        if self.request.user:
            if self.action == 'income':
                return self.queryset.filter(post__author=self.request.user)
            elif self.action == 'outcome':
                return self.queryset.filter(author=self.request.user)
            else:
                return self.queryset
        else:
            return self.queryset.filter(is_public=True)

    def perform_create(self, serializer):
        if serializer.is_valid(raise_exception=True):
            author = self.request.user
            current_offer = serializer.save(author=author)

            notification = Notification()
            notification.title = "New offer for post {}".format(current_offer.post)
            notification.text = current_offer.title
            notification.recipient = current_offer.post.author
            notification.redirect_url = '/offers/{}'.format(current_offer.id)
            # default notification datetime
            notification.save()

    """
    filtering:
        author__id, answered
    """
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsOwnerOrReadOnly,])
    def income(self, request):
        queryset = self.get_queryset()
        author_id = request.GET.get('author__id')
        answered = request.GET.get('answered')

        if author_id:
            queryset = queryset.filter(author=author_id)
        if answered != None:
            queryset = queryset.filter(answered=answered)

        queryset = queryset.order_by('-updated_at')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = serializers.OfferSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = serializers.OfferSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    """
    filtering:
        recipient__id, post__id, answered
    """
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsOwnerOrReadOnly,])
    def outcome(self, request):
        queryset = self.get_queryset()
        post__author__id = request.GET.get('recipient__id')
        post__id = request.GET.get('post__id')
        answered = request.GET.get('answered')

        if recipient__id:
            queryset = queryset.filter(post__author=recipient__id)
        if post__id:
            queryset = queryset.filter(post__id=post__id)
        if answered != None:
            queryset = queryset.filter(answered=answered)

        queryset = queryset.order_by('-updated_at')
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = serializers.OfferSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = serializers.OfferSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)


    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsOwnerOrReadOnly, ])
    def accept(self, request, pk=True):
        current_offer = self.get_object()

        serializer = serializers.OfferSerializer(data = current_offer, context={'request': request})
        serializer.is_valid()
        serializer.validate_on_answering()
        serializer.validate_on_accepting()

        result = self.process_answered_offer(current_offer, True)
        current_offer.delete()
        return Response({"accepted": result})

    """
    Rejecting request
    """
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsOwnerOrReadOnly, ])
    def reject(self, request, pk=True):
        current_offer = self.get_object()

        serializer = serializers.OfferSerializer(data = current_offer, context={'request': request})
        serializer.validate_on_answering()


        result = self.process_answered_offer(current_offer, True)
        current_offer.delete()
        return Response({"accepted": result})

    def process_answered_offer(self, is_accepted):
        notification = Notification()
        if is_accepted:
            notification.title = "User accepted your offer for post {}".format(current_offer.post)
            notification.redirect_url = '/offers/{}'.format(current_offer.id)
        else:
            notification.title = "User rejected your offer for post {}".format(current_offer.post)
            notification.redirect_url = '/posts/{}'.format(current_offer.post.id)

        notification.text = current_offer.title
        notification.recipient = current_offer.post.author
        # default notification datetime
        notification.save()

        return is_accepted



class NotificationViewSet(viewsets.ModelViewSet):
    """
    """
    queryset = Notification.objects.all().order_by('-created_at')
    serializer_class = serializers.NotificationSerializer
    permission_classes = (IsAuthenticated, IsOwnerOrReadOnly, )
    filter_backends = (filters.SearchFilter, DjangoFilterBackend, )
    search_fields = ('recipient__first_name', 'recipient__last_name', 'title', 'text')
    # filter_fields = ('recipient__id')

    # read only
    def get_queryset(self):
        return self.queryset.filter(recipient=self.request.user)

class ReviewViewSet(viewsets.ModelViewSet):
    """
    """
    queryset = Review.objects.all()
    serializer_class = serializers.ReviewSerializer
    permission_classes = (IsAuthenticated, IsOwnerOrReadOnly, )
    filter_backends = (filters.SearchFilter, DjangoFilterBackend, )
    search_fields = ('title', 'text')
    filter_fields = ('recipient__id', 'author__id', 'service__id')

    # read only
    # def get_queryset(self):
    #     return self.queryset

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

class OfferViewSet(viewsets.ModelViewSet):
    """
    Offers view set
    (request from employee to business, from employee to customer,
     from customer to business to connect them)
    """
    queryset = Offer.objects.all().order_by('-updated_at')
    serializer_class = serializers.OfferSerializer
    permission_classes = (IsOwnerOrReadOnly, )
    filter_backends = (filters.SearchFilter, DjangoFilterBackend)
    search_fields = ('title', 'text')
    filter_fields = ('author__id', 'post__id', 'author', 'post', 'answered', 'accepted', 'is_public')

    """
    NOTE: filters income and outcome actions too
    """
    def get_queryset(self):
        if self.request.user:
            if self.action == 'income':
                return self.queryset.filter(post__author=self.request.user)
            elif self.action == 'outcome':
                return self.queryset.filter(author=self.request.user)
            else:
                return self.queryset
        else:
            return self.queryset.filter(is_public=True)

    def perform_create(self, serializer):
        if serializer.is_valid(raise_exception=True):
            author = self.request.user
            current_offer = serializer.save(author=author)

            notification = Notification()
            notification.title = "New offer for post {}".format(current_offer.post)
            notification.text = current_offer.title
            notification.recipient = current_offer.post.author
            notification.redirect_url = '/offers/{}'.format(current_offer.id)
            # default notification datetime
            notification.save()

    """
    filtering:
        author__id, answered
    """
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsOwnerOrReadOnly,])
    def income(self, request):
        queryset = self.get_queryset()
        author_id = request.GET.get('author__id')
        answered = request.GET.get('answered')

        if author_id:
            queryset = queryset.filter(author=author_id)
        if answered != None:
            queryset = queryset.filter(answered=answered)

        queryset = queryset.order_by('-updated_at')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = serializers.OfferSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = serializers.OfferSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    """
    filtering:
        recipient__id, post__id, answered
    """
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsOwnerOrReadOnly,])
    def outcome(self, request):
        queryset = self.get_queryset()
        post__author__id = request.GET.get('recipient__id')
        post__id = request.GET.get('post__id')
        answered = request.GET.get('answered')

        if recipient__id:
            queryset = queryset.filter(post__author=recipient__id)
        if post__id:
            queryset = queryset.filter(post__id=post__id)
        if answered != None:
            queryset = queryset.filter(answered=answered)

        queryset = queryset.order_by('-updated_at')
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = serializers.OfferSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = serializers.OfferSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)


    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsOwnerOrReadOnly, ])
    def accept(self, request, pk=True):
        current_offer = self.get_object()

        serializer = serializers.OfferSerializer(data = current_offer, context={'request': request})
        serializer.is_valid()
        serializer.validate_on_answering()
        serializer.validate_on_accepting()

        result = self.process_answered_offer(current_offer, True)
        current_offer.delete()
        return Response({"accepted": result})

    """
    Rejecting request
    """
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsOwnerOrReadOnly, ])
    def reject(self, request, pk=True):
        current_offer = self.get_object()

        serializer = serializers.OfferSerializer(data = current_offer, context={'request': request})
        serializer.validate_on_answering()


        result = self.process_answered_offer(current_offer, True)
        current_offer.delete()
        return Response({"accepted": result})

    def process_answered_offer(self, is_accepted):
        notification = Notification()
        if is_accepted:
            notification.title = "User accepted your offer for post {}".format(current_offer.post)
            notification.redirect_url = '/offers/{}'.format(current_offer.id)
        else:
            notification.title = "User rejected your offer for post {}".format(current_offer.post)
            notification.redirect_url = '/posts/{}'.format(current_offer.post.id)

        notification.text = current_offer.title
        notification.recipient = current_offer.post.author
        # default notification datetime
        notification.save()

        return is_accepted



class NotificationViewSet(viewsets.ModelViewSet):
    """
    """
    queryset = Notification.objects.all()
    serializer_class = serializers.NotificationSerializer
    permission_classes = (IsAuthenticated, IsOwnerOrReadOnly, )
    filter_backends = (filters.SearchFilter, DjangoFilterBackend, )
    search_fields = ('recipient__first_name', 'recipient__last_name', 'title', 'text')
    # filter_fields = ('recipient__id')

    # read only
    def get_queryset(self):
        return self.queryset.filter(recipient=self.request.user)

class ReviewViewSet(viewsets.ModelViewSet):
    """
    """
    queryset = Review.objects.all()
    serializer_class = serializers.ReviewSerializer
    permission_classes = (IsAuthenticated, IsOwnerOrReadOnly, )
    filter_backends = (filters.SearchFilter, DjangoFilterBackend, )
    search_fields = ('title', 'text')
    filter_fields = ('recipient__id', 'author__id', 'service__id')

    # read only
    # def get_queryset(self):
    #     return self.queryset

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

        return None

class VoteViewSet(viewsets.ModelViewSet):
    """
    """
    queryset = Vote.objects.all()
    serializer_class = serializers.VoteSerializer
    permission_classes = (IsOwnerOrReadOnly, )



"""
Messages
"""
class MessageImageViewSet(viewsets.ModelViewSet):
    """
    """
    queryset = models.MessageImage.objects.all()
    serializer_class = serializers.MessageImageSerializer
    permission_classes = (IsAuthenticated, IsOwner, )


    def get_queryset(self):
        if self.request.user:
            return self.queryset.filter(conversation__users__in=[self.request.user])
        else:
            raise PermissionDenied()

class MessageViewSet(viewsets.ModelViewSet):
    """
    """
    queryset = models.Message.objects.all()
    serializer_class = serializers.MessageSerializer
    permission_classes = (IsAuthenticated, IsOwner, )
    filter_backends = (filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter )
    ordering_fields = ('created_at', )
    search_fields = ('text')
    filter_fields = ('conversation__id',)

    def perform_create(self, serializer):
        if self.request.user:
            msg = serializer.save(author=self.request.user)
            # serializer_1 = self.serializer_class(msg, many=False, )
            async_to_sync(broadcast_message)(msg, serializer.data)
        else:
            raise PermissionDenied()

    def perform_destroy(self, instance):
        conversationId = instance.conversation.id
        msgId = instance.id
        instance.delete()
        async_to_sync(broadcast_deleted_message)(conversationId, msgId)
    def get_queryset(self):
        if self.request.user:
            return self.queryset.filter(conversation__users__in=[self.request.user])
        else:
            raise PermissionDenied()

class ConversationViewSet(viewsets.ModelViewSet):
    """
    """
    queryset = models.Conversation.objects.all()
    serializer_class = serializers.ConversationSerializer
    permission_classes = (IsAuthenticated, IsOwner, )
    filter_backends = (filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter )
    ordering_fields = ('created_at', 'updated_at')
    search_fields = ('title', 'users__first_name', 'users__last_name')

    def get_queryset(self):
        if self.request.user:
            return self.queryset.filter(users__in=[self.request.user])
        else:
            raise PermissionDenied()

    @action(detail=False, methods=['get'], url_path='get_by_user_id/(?P<uid>\d+)')
    def get_by_users_ids(self, request, uid):
        if request.user.id == int(uid):
            return Response(status=status.HTTP_400_BAD_REQUEST)

        q = self.queryset.filter(users=request.user.id).filter(users=uid)
        if q.exists():
            serializer = serializers.ConversationSerializer(q.first(), many=False, context={'request': request})
            return Response(serializer.data)

        return Response(status=status.HTTP_404_NOT_FOUND)




class FeedbackViewSet(viewsets.ModelViewSet):
    """
    """
    queryset = models.Feedback.objects.all()
    serializer_class = serializers.FeedbackSerializer
    permission_classes = (IsAuthenticated, IsOwnerOrReadOnly, )
    filter_backends = (filters.SearchFilter, DjangoFilterBackend, )

    # read only
    def get_queryset(self):
        if self.request.user:
            return self.queryset.filter(author=self.request.user)
        else:
            raise PermissionDenied()

    def perform_create(self, serializer):
        if self.request.user:
            serializer.save(author=self.request.user)
        else:
            raise PermissionDenied()


def fix_django_headers(meta):
    """
    Fix this nonsensical API:
    https://docs.djangoproject.com/en/1.11/ref/request-response/
    https://code.djangoproject.com/ticket/20147
    """
    ret = {}
    for k, v in meta.items():
        if k.startswith("HTTP_"):
            k = k[len("HTTP_") :]
        elif k not in ("CONTENT_LENGTH", "CONTENT_TYPE"):
            # Skip CGI garbage
            continue
        ret[k.lower().replace("_", "-")] = v
    return ret


class PaymentsViewSet(viewsets.ViewSet):
    """
    """
    @action(detail=False, methods=['post'], url_path='create_new_intent', permission_classes = [IsAuthenticated, ])
    def create_new_intent(self, request):
        body = json.loads(request.body.decode())
        amount = body.get('amount', None)
        currency = body.get('currency', None)
        metadata = body.get('metadata', None)
        if not amount or not currency:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        stripe.api_key = settings.STRIPE_TEST_SECRET_KEY
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency,
            metadata=metadata
        )

        return Response(intent)

    def send_confirmation_email(self, service, service_promotion, intent):
        msg_plain = render_to_string('templates/email.txt', {'service': service, 'service_promotion': service_promotion})
        msg_html = render_to_string('templates/completed_order_email.html', {'service': service, 'service_promotion': service_promotion, 'intent': intent})

        try:
            send_mail(
                'Completed order',
                msg_plain,
                settings.EMAIL_HOST_USER,
                ['timadevelop@gmail.com'],
                fail_silently=False,
                html_message=msg_html
            )
        except:
            return False

        return True


    @action(detail=False, methods=['post'], url_path='send_email', permission_classes = [IsAuthenticated, ])
    def send_email(self, request):
        body = json.loads(request.body.decode())
        amount = body.get('amount', None)
        currency = body.get('currency', None)
        metadata = body.get('metadata', None)

        msg_plain = render_to_string('templates/email.txt', {'text': 'waaat'})
        msg_html = render_to_string('templates/email_1.html', {'text': 'superduper'})
        try:
            send_mail(
                'Subject here',
                msg_plain,
                settings.EMAIL_HOST_USER,
                ['recipient@gmail.com'],
                fail_silently=False,
                html_message=msg_html
            )
        except:
            return Response({'success': 'false'})


        return Response({'success': 'true'})

    @action(detail=False, methods=['post'], url_path='update_intent', permission_classes = [IsAuthenticated, ])
    def update_intent(self, request):
        body = json.loads(request.body.decode())
        id = body.get('id', None)
        amount = body.get('amount', None)
        currency = body.get('currency', None)
        metadata = body.get('metadata', None)

        if not id:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        stripe.api_key = settings.STRIPE_TEST_SECRET_KEY
        intent = stripe.PaymentIntent.modify(
            id,
            amount=amount,
            currency=currency,
            metadata=metadata
        )

        return Response(intent)

    @action(detail=False, methods=['post'], url_path='webhook')
    def webhook(self, request):
        payload = request.body
        headers = request.META

        sig_header = fix_django_headers(request.META).get('stripe-signature', None)
        event = None

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_ENDPOINT_SECRET
            )
        except ValueError as e:
            # invalid payload
            print('invalid payload')
            return Response({"detail": 'Invalid payload'}, status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError as e:
            # invalid signature
            print('invalid sign')
            return Response({"detail": 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

        event_dict = event.to_dict()
        if event_dict['type'] == "payment_intent.succeeded":
            intent = event_dict['data']['object']
            print("Succeeded: ", intent['id'])
            print("Succeeded: ", intent['metadata'])
            self.process_succeeded_intent(intent)
            # Fulfill the customer's purchase
        elif event_dict['type'] == "payment_intent.payment_failed":
            intent = event_dict['data']['object']
            if intent.get('last_payment_error'):
                error_message = intent['last_payment_error']['message']
            else:
                error_message = None

            print("Failed: ", intent['id'], error_message)
            # Notify the customer that payment failed
        return Response(status=status.HTTP_200_OK)

    def process_succeeded_intent(self, intent):
        metadata = intent['metadata']

        reason = metadata.get('reason', None)
        if not reason:
            print('strange!')
            # TODO
            return

        if reason == 'promote_service':
            service, service_promotion = self.promote_service(intent)
            # Send email
            self.send_confirmation_email(service, service_promotion, intent)
        elif reason == 'promote_post':
            # TODO
            pass

    def promote_service(self, intent):
        metadata = intent['metadata']

        print('yeas~!')
        user_id = int(metadata.get('user_id', None))
        model = metadata.get('model', None)
        model_id = int(metadata.get('model_id', None))
        plan = metadata.get('plan', None)
        days = int(metadata.get('days', None))

        user = None
        if user_id:
            try:
                user = models.User.objects.get(id=user_id)
            except Exception as e:
                print('error getting user', e)

        serivce = None
        try:
            service = models.Service.objects.get(id=model_id)
        except:
            print('error getting service')
            return

        if not service:
            return


        if service.promotions.exists():
            print('update old promotion')
            service_promotion = service.promotions.first()
            # add days
            service_promotion.end_datetime = service_promotion.end_datetime + timezone.timedelta(days=days)
            service_promotion.stripe_payment_intents.append(intent['id'])
            service_promotion.save()
            print('success')
        else:
            print('create new promotion')
            end_datetime = timezone.now() + timezone.timedelta(days=days)
            service_promotion = models.ServicePromotion.objects.create(
                author=user, service=service, \
                stripe_payment_intents=[intent['id']], \
                end_datetime=end_datetime)
            print('success')

        return service, service_promotion


class ConfigViewSet(viewsets.ViewSet):
    """
    """
    @action(detail=False, methods=['get'], url_path='get_configuration', permission_classes = [])
    def get_configuration(self, request):
        resp = {
            'API_CLIENT_ID': local_settings.API_CLIENT_ID,
            'API_CLIENT_SECRET': local_settings.API_CLIENT_SECRET,
            'STRIPE_PUBLIC_KEY': local_settings.STRIPE_TEST_PUBLIC_KEY,
        }

        return Response(resp)


