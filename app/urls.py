from django.urls import path
from . import views

app_name = 'app'

urlpatterns = [
    path('', views.index_view, name='index'),
    path('api/chat/', views.api_chat_view, name='api_chat'),
    path('api/whatsapp-simulator/', views.api_whatsapp_simulator_view, name='api_whatsapp_simulator'),
    path('api/storage/', views.api_storage_list, name='api_storage_list'),
    path('api/storage/<str:filename>/', views.api_storage_file_content, name='api_storage_file_content'),
    path('api/reset-history/', views.api_reset_history, name='api_reset_history'),
    path('api/lotes/update/', views.api_lote_update_view, name='api_lote_update'),
    
    # Endpoints de Hojas de Cálculo & Google Drive
    path('api/sheets/download/', views.api_sheets_download_view, name='api_sheets_download'),
    path('api/sheets/download/<str:crop_name>/', views.api_sheets_download_view, name='api_crop_sheets_download'),
    path('api/sheets/live-data/', views.api_sheets_live_data_view, name='api_sheets_live_data'),
    path('api/sheets/csv/<str:module_name>/', views.api_sheets_csv_view, name='api_sheets_csv'),
    path('api/sheets/sync/', views.api_sheets_sync_now_view, name='api_sheets_sync_now'),
]
