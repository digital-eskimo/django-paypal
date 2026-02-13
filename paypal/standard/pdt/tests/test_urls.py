from django.conf.urls import *
from paypal.standard.pdt import views

urlpatterns = [
    (r'^pdt/$', views.pdt),
]
