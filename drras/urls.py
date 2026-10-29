from django.urls import path, include
from operations import views
urlpatterns=[path('',views.page,name='home'),path('<str:page>.html',views.page,name='page'),path('api/',include('operations.urls'))]
