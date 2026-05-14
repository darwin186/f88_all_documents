from django.urls import path
from . import views

urlpatterns = [
    path('', views.workshift_register_view, name='workshift_register'),
    path('tasks/', views.workshift_tasks_view, name='workshift_tasks'),
    path('report/', views.workshift_report_view, name='workshift_report'),
    path('report/export/', views.workshift_report_export_view, name='workshift_report_export'),
    path('policy/', views.workshift_policy_view, name='workshift_policy'),
]
