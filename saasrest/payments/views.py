"""Payments views"""
import json

from django.conf import settings
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.template.defaulttags import register
from django.utils.translation import ugettext as _
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# pylint: disable=fixme, import-error
import stripe
from saas_core.utils import fix_django_headers

from .models import Coupon
from .serializers import CouponSerializer
from .utils import promote_service, send_confirmation_email, is_valid_payment_intent

from fb_ads import utils as fb_ads_utils

import logging
logger = logging.getLogger(__name__)

"""Filter for email template"""

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key, 'None')


class CouponViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Coupons viewset
    """
    queryset = Coupon.objects.all()
    serializer_class = CouponSerializer
    permission_classes = ()
    # filter_backends = (filters.SearchFilter, DjangoFilterBackend, )
    # search_fields = ()
    # filter_fields = ()

    def get_queryset(self):
        return self.queryset.filter(Q(user=self.request.user) | Q(user=None))

    def list(self, request, *args, **kwargs):
        self.queryset = self.queryset.filter(user=self.request.user)
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='redeem')
    def redeem(self, request, pk=None):
        """Redeem coupon"""
        coupon = self.get_object()
        if not coupon:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not coupon.valid:
            return Response({'detail': _("Coupon is not valid")}, status=status.HTTP_400_BAD_REQUEST)

        logger.info("Redeem a valid coupon request")

        payload = json.loads(request.body)
        reason = payload.get('reason')
        logger.info("Reason: {}".format(reason))
        if self.request.user:
            user_id = self.request.user.id
        else:
            logger.warning("Unauthanticated user trying to use a coupon")
            raise PermissionDenied()

        if coupon.user and coupon.user.id != user_id:
            logger.warning("Authenticated user #{} trying to use another's user (#{}) coupon".format(user_id, coupon.user.id))
            raise PermissionDenied()

        if reason == 'promote_service':
            logger.info("Coupon:reason:promote_service")
            model_id = payload.get('model_id', None)
            if not model_id:
                return Response({'detail': _("Provide service id")}, status=status.HTTP_400_BAD_REQUEST)
            model_id = int(model_id)
            
            service, service_promotion = promote_service(
                user_id, model_id, coupon.days, 'Coupon')

            coupon.redeem()
            # Send email
            # d = {'days': coupon.days, 'plan': 'Coupon'}
            # send_confirmation_email(
            #     service, service_promotion, {'metadata': d})

            return Response({'promoted_til': service_promotion.end_datetime}, status=status.HTTP_200_OK)

        elif reason == 'promote_post':
            # TODO
            pass

        return Response(status=status.HTTP_400_BAD_REQUEST)


class PaymentsViewSet(viewsets.ViewSet):
    """
    Main view
    """
    @action(
        detail=False,
        methods=['post'],
        url_path='create_new_intent',
        permission_classes=[IsAuthenticated, ])
    def create_new_intent(self, request):
        """Endpoint for new PaymentIntent creation"""
        body = json.loads(request.body.decode())
        amount = body.get('amount', None)
        currency = body.get('currency', None)
        metadata = body.get('metadata', None)

        plan = metadata.get('plan')
        days = metadata.get('days')
        reason = metadata.get('reason')

        if not plan or not days or not reason or not amount or not currency or not metadata:
            return Response({'detail': _("Request data is not complete")}, status=status.HTTP_400_BAD_REQUEST)

        try:
            plan = plan.lower()
            reason = reason.lower()
            currency = currency.lower()
        except:
            return Response({'detail': _("Wrong plan, reason or currency")}, status=status.HTTP_400_BAD_REQUEST)

        if not is_valid_payment_intent(plan, days, amount, currency, reason):
            return Response({'detail': _("Invalid request: plan, days, amount, currency and reason.")}, status=status.HTTP_400_BAD_REQUEST)

        stripe.api_key = settings.STRIPE_TEST_SECRET_KEY
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency,
            metadata=metadata
        )

        return Response(intent)

    @action(
        detail=False,
        methods=['post'],
        url_path='test_fb_ads',
        permission_classes=[])
    def test_fb_ads(self, request):
        # result = fb_ads_utils.facebookAdsManager.search_targeting_interests('cars')
        # result = fb_ads_utils.facebookAdsManager.create_campaign()

        # get ad set
        # result = fb_ads_utils.facebookAdsManager. create_ad_set(23843684809030061, 1000, 'cars')
        ad_sets = fb_ads_utils.facebookAdsManager.get_ad_sets()
        if len(ad_sets) > 0:
            ad_set = ad_sets[0]

        # create post
        post_id = fb_ads_utils.facebookAdsManager.create_post("Post from API 3")

        print('post_id: {}'.format(post_id))
        # advertise post
        ad = fb_ads_utils.facebookAdsManager.advertise_post(post_id, ad_set.get('id'))
        print(result)
        return Response(result)

    @action(
        detail=False,
        methods=['post'],
        url_path='update_intent',
        permission_classes=[IsAuthenticated, ])
    def update_intent(self, request):
        """Update payment intent endpoint"""
        body = json.loads(request.body.decode())
        intent_id = body.get('id', None)
        amount = body.get('amount', None)
        currency = body.get('currency', None)
        metadata = body.get('metadata', None)

        plan = metadata.get('plan')
        days = metadata.get('days')
        reason = metadata.get('reason')

        if not intent_id or not plan or not days or not reason or not amount or not currency or not metadata:
            return Response({'detail': _("Request data is not complete")}, status=status.HTTP_400_BAD_REQUEST)

        try:
            plan = plan.lower()
            reason = reason.lower()
            currency = currency.lower()
        except:
            return Response({'detail': _("Wrong plan, reason or currency")}, status=status.HTTP_400_BAD_REQUEST)

        if not is_valid_payment_intent(plan, days, amount, currency, reason):
            return Response({'detail': _("Invalid request: plan, days, amount, currency and reason.")}, status=status.HTTP_400_BAD_REQUEST)

        stripe.api_key = settings.STRIPE_TEST_SECRET_KEY
        intent = stripe.PaymentIntent.modify(
            intent_id,
            amount=amount,
            currency=currency,
            metadata=metadata
        )

        return Response(intent)

    @action(detail=False, methods=['post'], url_path='webhook')
    def webhook(self, request):
        """Stripe webhook"""
        # TODO: accept only stripe check
        payload = request.body
        headers = request.META

        sig_header = fix_django_headers(
            headers).get('stripe-signature', None)
        event = None

        logger.info("Stripe webhook")

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_ENDPOINT_SECRET
            )
        except ValueError:
            # invalid payload
            logger.warn('Stripe invalid payload')
            return Response({"detail": 'Invalid payload'}, status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError:
            # invalid signature
            logger.warn('Stripe invalid signature')
            return Response({"detail": 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

        event_dict = event.to_dict()
        if event_dict['type'] == "payment_intent.succeeded":
            intent = event_dict['data']['object']
            logger.info("Stripe WH: Succeeded payment intent with id {}".format(intent['id']))
            logger.info("Stripe WH: Succeeded payment intent metadata: {}".format(intent['metadata']))
            # Fulfill the customer's purchase
            self.process_succeeded_intent(intent)
        elif event_dict['type'] == "payment_intent.payment_failed":
            intent = event_dict['data']['object']
            if intent.get('last_payment_error'):
                error_message = intent['last_payment_error']['message']
            else:
                error_message = None

            logger.warn("Stripe WH: Failed payment intent: {}, error_message: {}".format(intent['id'], error_message))
            # TODO: Notify the customer that payment failed
        return Response(status=status.HTTP_200_OK)

    def process_succeeded_intent(self, intent):
        """Process Succeded paymentIntent"""
        metadata = intent['metadata']

        reason = metadata.get('reason', None)
        if not reason:
            logger.warn("No reason provided for successded payment intent with id {}".format(intent['id']))
            return

        if reason == 'promote_service':
            logger.info("PaymentIntent:reason:promote_service")
            metadata = intent['metadata']
            user_id = int(metadata.get('user_id', None))
            model_id = int(metadata.get('model_id', None))
            days = int(metadata.get('days', None))

            service, service_promotion = promote_service(
                user_id, model_id, days, intent['id'])
            # Send email
            logger.info("Sending confirmation email about service promotion")
            send_confirmation_email(service, service_promotion, intent)
        elif reason == 'promote_seek':
            # TODO
            pass
