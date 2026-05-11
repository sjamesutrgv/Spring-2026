# mycalendar/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.show_calendar, name='calendar-home'),
    path('<int:year>/<int:month>/', views.show_calendar, name='calendar-specific'),
    # NEW PATH: Routes traffic when a specific day is clicked
    path('<int:year>/<int:month>/<int:day>/', views.daily_events, name='daily-events'),

    #Login Urls
    path('login/', auth_views.LoginView.as_view(
        template_name='mycalendar/login.html'
    ), name='login'),
    
    path('logout/', auth_views.LogoutView.as_view(
        next_page='calendar-home'  
    ), name='logout'),
    
    path('signup/', views.signup, name='signup'),
    
    path('events/create/', views.create_event, name='create_event'),
    path('events/mine/', views.my_events, name='my_events'),
    path('events/<int:event_id>/register/', views.toggle_event_registration, name='toggle_event_registration'),
    path('profile/', views.profile, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),

]
