from django.urls import path
from . import views

app_name = 'app'

urlpatterns = [
    path('', views.index_view, name='index'),
    path('api/chat/', views.api_chat_view, name='api_chat'),
    path('api/storage/', views.api_storage_list, name='api_storage_list'),
    path('api/storage/<str:filename>/', views.api_storage_file_content, name='api_storage_file_content'),
    path('api/reset-history/', views.api_reset_history, name='api_reset_history'),
]
