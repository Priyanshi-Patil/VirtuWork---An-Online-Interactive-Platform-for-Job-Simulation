from django.urls import path
from core import views as core_views
from simulation import views as sim_views
from django.contrib.auth import views as auth_views
from simulation import views


urlpatterns = [
    path('', core_views.landing_page, name='landing'),
    path('signup/', core_views.signup_view, name='signup'),
    path('verify-otp/', core_views.verify_otp, name='verify_otp'),
    path('resend-otp/', core_views.resend_otp, name='resend_otp'),
    path('login/', core_views.login_view, name='login'),
    path('forgot-password/', core_views.forgot_password, name='forgot_password'),
    path('reset-password/', core_views.reset_password, name='reset_password'),
    path('resend-reset-otp/', core_views.resend_reset_otp, name='resend_reset_otp'),
    path('dashboard/', core_views.dashboard_view, name='dashboard'),
    path('how-it-works/', core_views.how_it_works, name='how_it_works'),

    # Simulation routes
    path('simulation/create/', sim_views.create_simulation, name='create_simulation'),
    path('simulation/delete/<int:sim_id>/', sim_views.delete_simulation, name='delete_simulation'),
    path('simulation/resume/<int:sim_id>/', sim_views.resume_simulation, name='resume_simulation'),
    path('simulation/chat/<int:simulation_id>/', sim_views.simulation_chat, name='simulation_chat'),
    path('simulation/send-message/', sim_views.send_message, name='send_message'),
    path('simulation/initiate-ai/<int:simulation_id>/', sim_views.initiate_ai_logic, name='initiate_ai'),
    path('simulation/submit-task/', sim_views.submit_task, name='submit_task'),
    path('simulation/end-simulation-report/<int:simulation_id>/', sim_views.end_simulation_report, name='end_simulation_report'),
    path('simulation/check-ready/<int:simulation_id>/', sim_views.check_simulation_ready, name='check_simulation_ready'),

    # Profile
    path('profile/', core_views.profile_view, name='profile'),
    path('edit-profile/', core_views.edit_profile, name='edit_profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),

    # Certificates
    path('certificate/<int:simulation_id>/', sim_views.certificate_view, name='certificate'),
    path('certificate/download/<int:sim_id>/', sim_views.download_certificate_pdf, name='download_certificate'),
    path('verify/<int:simulation_id>/', sim_views.verify_certificate, name='verify_certificate'),

    # Auth
    path('logout/', auth_views.LogoutView.as_view(next_page='landing'), name='logout'),

    # API
    path('api/check-email/', core_views.check_email_exists, name='check_email'),
    path('send-message-ajax/', sim_views.send_message_ajax, name='send_message_ajax'),

    #
    path('about/', core_views.about_site, name='about_site'),
    path('privacy/', core_views.privacy_policy, name='privacy'),
    path('terms/', core_views.terms_of_service, name='terms'),
    path('simulation/<int:simulation_id>/download-dataset/', sim_views.download_project_dataset, name='download_dataset'),
]