#!/usr/bin/env python
# -*- coding: utf-8 -*-
import requests
from ..models import PayPalStandardBase
from . import signals

class PayPalIPN(PayPalStandardBase):
    """Logs PayPal IPN interactions."""
    format = "<IPN: %s %s>"

    class Meta:
        db_table = "paypal_ipn"
        verbose_name = "PayPal IPN"

    def _postback(self):
        """Perform PayPal Postback validation."""
        return requests.get(
            self.get_endpoint(), "cmd=_notify-validate&%s" % self.query
        ).content

    def _verify_postback(self):
        if self.response != "VERIFIED":
            self.set_flag("Invalid postback. (%s)" % self.response)

    def send_signals(self):
        """Shout for the world to hear whether a txn was successful."""
        # Transaction signals:
        if self.is_transaction():
            if self.flag:
                signals.payment_was_flagged.send(sender=self)
            else:
                signals.payment_was_successful.send(sender=self)

        # Note that e.g. recurring_payment will send above and below
        if self.is_recurring_create():
            signals.recurring_create.send(sender=self)
        elif self.is_recurring_payment():
            signals.recurring_payment.send(sender=self)
        elif self.is_recurring_cancel():
            signals.recurring_cancel.send(sender=self)
        elif self.is_subscription_cancellation():
            signals.subscription_cancel.send(sender=self)
        elif self.is_subscription_signup():
            signals.subscription_signup.send(sender=self)
        elif self.is_subscription_end_of_term():
            signals.subscription_eot.send(sender=self)
        elif self.is_subscription_modified():
            signals.subscription_modify.send(sender=self)
