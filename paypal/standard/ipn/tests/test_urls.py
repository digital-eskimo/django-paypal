from django.conf.urls import *
from paypal.standard.ipn import views

urlpatterns = [
    (r'^ipn/$', views.ipn),
]
