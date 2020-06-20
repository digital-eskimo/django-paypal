#!/usr/bin/env python
# -*- coding: utf-8 -*-

import datetime
import pprint
import time
import urllib
import requests

from django.conf import settings
from django.forms.models import fields_for_model
from django.utils.http import urlencode

from paypal.pro import signals
from paypal.pro.models import PayPalNVP
from paypal.pro.exceptions import PayPalFailure

TEST = settings.PAYPAL_TEST
USER = settings.PAYPAL_WPP_USER
PASSWORD = settings.PAYPAL_WPP_PASSWORD
SIGNATURE = settings.PAYPAL_WPP_SIGNATURE
VERSION = 74.0
BASE_PARAMS = dict(USER=USER , PWD=PASSWORD, SIGNATURE=SIGNATURE, VERSION=VERSION)
ENDPOINT = "https://api-3t.paypal.com/nvp"
SANDBOX_ENDPOINT = "https://api-3t.sandbox.paypal.com/nvp"
NVP_FIELDS = fields_for_model(PayPalNVP).keys()
# PayPal Edit IPN URL:
# https://www.sandbox.paypal.com/us/cgi-bin/webscr?cmd=_profile-ipn-notify
EXPRESS_ENDPOINT = "https://www.paypal.com/webscr?cmd=_express-checkout&%s"
SANDBOX_EXPRESS_ENDPOINT = \
    "https://www.sandbox.paypal.com/webscr?cmd=_express-checkout&%s"

API_METHODS = {
    'DoDirectPayment': {
        'defaults': {"paymentaction": "Sale"},
        'required': (
            'CREDITCARDTYPE', 'ACCT', 'EXPDATE', 'CVV2', 'IPADDRESS',
            'FIRSTNAME', 'LASTNAME', 'STREET', 'CITY', 'STATE', 'COUNTRYCODE',
            'ZIP', 'AMT'),
        'signal': signals.payment_was_successful,
        },
    'SetExpressCheckout': {
        'required': ('RETURNURL', 'CANCELURL', 'AMT'),
        'defaults': {'NOSHIPPING': '1'}
        },
    'GetExpressCheckoutDetails': {
        'required': ('TOKEN',)
        },
    'ManageRecurringPaymentsProfileStatus': {
        'required': ('PROFILEID', 'ACTION'),
        'signal': signals.recurring_status_change,
        },
    'DoExpressCheckoutPayment': {
        'defaults': {'PAYMENTACTION': 'Sale'},
        'required': ('RETURNURL', 'CANCELURL', 'AMT', 'TOKEN', 'PAYERID'),
        'signal': signals.payment_was_successful,
        },
    'GetTransactionDetails': {
        'required': ('TRANSACTIONID',),
        },
    'CreateRecurringPaymentsProfile': {
        'required': (
            'PROFILESTARTDATE', 'BILLINGPERIOD', 'BILLINGFREQUENCY', 'AMT'),
        'signal': signals.payment_profile_created,
        },
    'UpdateRecurringPaymentsProfile': {
        'required': ('PROFILEID',),
        },
    'GetRecurringPaymentsProfileDetails': {
        'required': ('PROFILEID',),
        },
    }

def paypal_time(time_obj=None):
    """Returns a time suitable for PayPal time fields."""
    if time_obj is None:
        time_obj = time.gmtime()
    return time.strftime(PayPalNVP.TIMESTAMP_FORMAT, time_obj)

def paypaltime2datetime(s):
    """Convert a PayPal time string to a DateTime."""
    return datetime.datetime(
        *(time.strptime(s, PayPalNVP.TIMESTAMP_FORMAT)[:6]))

def get_express_endpoint():
    return SANDBOX_EXPRESS_ENDPOINT if TEST else EXPRESS_ENDPOINT


class PayPalError(TypeError):
    """Error thrown when something be wrong."""


class PayPalWPP(object):
    """
    Wrapper class for the PayPal Website Payments Pro.

    Website Payments Pro Integration Guide:
    https://cms.paypal.com/cms_content/US/en_US/files/developer/
    PP_WPP_IntegrationGuide.pdf

    Name-Value Pair API Developer Guide and Reference:
    https://cms.paypal.com/cms_content/US/en_US/files/developer/
    PP_NVPAPI_DeveloperGuide.pdf
    """
    def __init__(self, request=None, params=BASE_PARAMS):
        """Required - USER / PWD / SIGNATURE / VERSION"""
        self.request = request # can be None if necessary
        if TEST:
            self.endpoint = SANDBOX_ENDPOINT
        else:
            self.endpoint = ENDPOINT
        self.signature_values = params
        self.signature = urlencode(self.signature_values) + "&"

    def doDirectPayment(self, params):
        """Call PayPal DoDirectPayment method."""
        nvp_obj = self.api_call('DoDirectPayment', params)
        # @@@ Could check cvv2match / avscode are both 'X' or '0'
        # qd = django.http.QueryDict(nvp_obj.response)
        # if qd.get('cvv2match') not in ['X', '0']:
        #   nvp_obj.set_flag("Invalid cvv2match: %s" % qd.get('cvv2match')
        # if qd.get('avscode') not in ['X', '0']:
        #   nvp_obj.set_flag("Invalid avscode: %s" % qd.get('avscode')
        return nvp_obj

    def setExpressCheckout(self, params):
        """
        Initiates an Express Checkout transaction.
        Optionally, the SetExpressCheckout API operation can set up billing
        agreements for reference transactions and recurring payments.
        Returns a NVP instance - check for token and payerid to continue!
        """
        if self._is_recurring(params):
            params = self._recurring_setExpressCheckout_adapter(params)
        return self.api_call('SetExpressCheckout', params)

    def doExpressCheckoutPayment(self, params):
        """
        Check the dude out:
        """
        if self._is_recurring(params):
            return wpp.createRecurringPaymentsProfile(params)
        nvp = self.api_call('DoExpressCheckoutPayment', params)
        return nvp

    def createRecurringPaymentsProfile(self, params, direct=False):
        """
        Set direct to True to indicate that this is being called as a
        directPayment. Returns True PayPal successfully creates the profile
        otherwise False.
        """
        extra_requirements = ('TOKEN',) if not direct else (
            'CREDITCARDTYPE', 'ACCT', 'EXPDATE', 'FIRSTNAME', 'LASTNAME')

        return self.api_call(
            'CreateRecurringPaymentsProfile', params,
            extra_requirements=extra_requirements)

    def api_call(self, method, params, extra_requirements=None):
        assert method in API_METHODS
        params['METHOD'] = method
        nvp = self._fetch(params, extra_requirements=extra_requirements)
        if nvp.flag:
            raise PayPalFailure(nvp.flag_info)
        signal = API_METHODS[method].get('signal', None)
        if signal:
            signal.send(self, params=params, nvp=nvp)
        return nvp

    def getExpressCheckoutDetails(self, params):
        return self.api_call('GetExpressCheckoutDetails', params)

    def setCustomerBillingAgreement(self, params):
        raise DeprecationWarning

    def getTransactionDetails(self, params):
        return self.api_call('GetTransactionDetails', params)

    def massPay(self, params):
        raise NotImplementedError

    def getRecurringPaymentsProfileDetails(self, params):
        return self.api_call('GetRecurringPaymentsProfileDetails', params)

    def updateRecurringPaymentsProfile(self, params):
        return self.api_call('UpdateRecurringPaymentsProfile', params)

    def billOutstandingAmount(self, params):
        raise NotImplementedError

    def manageRecurringPaymentsProfileStatus(
        self, params, fail_silently=False):
        """
        Requires `PROFILEID` and `ACTION` params.
        ACTION must be either "Cancel", "Suspend", or "Reactivate".
        """
        try:
            nvp = self.api_call('ManageRecurringPaymentsProfileStatus', params)
        except PayPalFailure as e:
            if not(fail_silently and e.message == (
                'Invalid profile status for cancel action; '
                'profile should be active or suspended')):
                raise
        else:
            if params['ACTION'] == 'Cancel':
                signals.recurring_cancel.send(self, params=params, nvp=nvp)
            elif params['ACTION'] == 'Suspend':
                signals.recurring_suspend.send(self, params=params, nvp=nvp)
            elif params['ACTION'] == 'Reactivate':
                signals.recurring_reactivate.send(self, params=params, nvp=nvp)
            return nvp

    def refundTransaction(self, params):
        raise NotImplementedError

    def _is_recurring(self, params):
        """Returns True if the item passed is a recurring transaction."""
        return 'BILLINGFREQUENCY' in params

    def _recurring_setExpressCheckout_adapter(self, params):
        """
        The recurring payment interface to SEC is different than the recurring
        payment interface to ECP. This adapts a normal call to look like a
        SEC call.
        """
        params['L_BILLINGTYPE0'] = "RecurringPayments"
        params['L_BILLINGAGREEMENTDESCRIPTION0'] = params['DESC']

        REMOVE = (
            'BILLINGFREQUENCY', 'BILLINGPERIOD', 'PROFILESTARTDATE', 'DESC')

        for k in params.keys():
            if k in REMOVE:
                del params[k]

        return params

    def _fetch(
        self, params, required=None, defaults=None, extra_requirements=None):
        """Make the NVP request and store the response."""
        if required is None or defaults is None:
            assert params['METHOD'] in API_METHODS
            if required is None:
                required = API_METHODS[params['METHOD']].get('required', ())
            if defaults is None:
                defaults = API_METHODS[params['METHOD']].get('defaults', {})
        required += extra_requirements or ()
        defaults.update(params)
        pp_params = self._check_and_update_params(required, defaults)
        pp_string = self.signature + urlencode(pp_params)
        response = self._request(pp_string)
        response_params = self._parse_response(response)

        if getattr(settings, 'PAYPAL_DEBUG', settings.DEBUG):
            print('PayPal Request:')
            pprint.pprint(defaults)
            print('\nPayPal Response:')
            pprint.pprint(response_params)

        # Gather all NVP parameters to pass to a new instance.
        nvp_params = {}
        merge = {}
        merge.update(defaults)
        merge.update(response_params)
        for key, value in merge.items():
            if key.lower() in NVP_FIELDS:
                nvp_params[str(key.lower())] = value

        # PayPal timestamp has to be formatted.
        if 'timestamp' in nvp_params:
            nvp_params['timestamp'] = paypaltime2datetime(
                nvp_params['timestamp'])

        nvp_obj = PayPalNVP(**nvp_params)
        nvp_obj.init(self.request, params, response_params)
        nvp_obj.save()
        return nvp_obj

    def _request(self, data):
        """Moved out to make testing easier."""
        return requests.get(self.endpoint, data).content

    def _check_and_update_params(self, required, params):
        """
        Ensure all required parameters were passed to the API call and format
        them correctly.
        """
        for r in required:
            if r not in params:
                raise PayPalError("Missing required param: %s" % r)

        # Upper case all the parameters for PayPal.
        return (dict((k.upper(), v) for k, v in params.iteritems()))

    def _parse_response(self, response):
        """Turn the PayPal response into a dict"""
        response_tokens = {}
        for kv in response.split('&'):
            key, value = kv.split("=")
            response_tokens[key] = urllib.unquote(value)
        return response_tokens
