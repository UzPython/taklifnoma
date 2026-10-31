from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('templates/', views.templates_list_view, name='templates_list'),
    path('my-invitations/', views.my_invitations_view, name='my_invitations'),
    path('create/', views.create_view, name='create_invitation'),
    path('success/<uuid:pk>/', views.success_view, name='success_invitation'),
    path('invitation/<uuid:pk>/', views.invitation_detail_view, name='invitation_detail'),
    path('invitation/<uuid:pk>/delete/', views.delete_invitation_view, name='delete_invitation'),
    path('invitation/<uuid:pk>/like/', views.like_invitation, name='like_invitation'),
]
