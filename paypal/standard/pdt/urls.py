from django.conf.urls import *
from paypal.standard.pdt import views

urlpatterns = [
    url(r'^$', views.pdt, name="paypal-pdt"),
]
