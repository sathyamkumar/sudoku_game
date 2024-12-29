from django.urls import path
from . import views

urlpatterns = [
    path('api/room/create/', views.create_room, name='create_room'),
    path('api/room/', views.get_room, name='get_room'),
]
