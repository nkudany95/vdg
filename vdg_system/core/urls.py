from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile, name='profile'),
    path('change-password/', views.change_password, name='change_password'),
    path('chatbot/', views.chatbot, name='chatbot'),
    path('notifications/', views.notifications, name='notifications'),
    path('manage/notifications/', views.manage_notifications, name='manage_notifications'),
    path('manage/meetings/', views.manage_meetings, name='manage_meetings'),
    path('committee/', views.committee, name='committee'),
    path('system/settings/', views.system_settings, name='system_settings'),
    path('login-history/', views.login_history, name='login_history'),
    path('audit-logs/', views.audit_logs, name='audit_logs'),
]
