import re
import random
from django.http import JsonResponse
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from .models import UserProfile
from django.contrib.auth.decorators import login_required
from simulation.models import Simulation
from evaluation.models import ProgressReport
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from .models import UserProfile as Profile  

# ─── Password Validator ───────────────────────────────────────────────────────

def validate_password(password):
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not re.search(r'[A-Za-z]', password):
        return "Password must contain at least one letter."
    if not re.search(r'[0-9]', password):
        return "Password must contain at least one number."
    if not re.search(r'[@#]', password):
        return "Password must contain at least one special character (@ or #)."
    return None


# ─── Landing ──────────────────────────────────────────────────────────────────

def landing_page(request):
    return render(request, "index.html")


# ─── Email Check API ──────────────────────────────────────────────────────────

def check_email_exists(request):
    email = request.GET.get('email', None)
    data = {
        'exists': User.objects.filter(email__iexact=email).exists()
    }
    return JsonResponse(data)


# ─── Signup ───────────────────────────────────────────────────────────────────

def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == "POST":
        data = request.POST

        if data['password'] != data['confirm_password']:
            return render(request, 'signup.html', {'error': 'Passwords do not match.'})

        password_error = validate_password(data['password'])
        if password_error:
            return render(request, 'signup.html', {'error': password_error})

        if User.objects.filter(username=data['username']).exists():
            return render(request, 'signup.html', {'error': 'Username already taken.'})

        if User.objects.filter(email=data['email']).exists():
            return render(request, 'signup.html', {'error': 'Email already registered.'})

        otp = str(random.randint(100000, 999999))

        request.session['pending_user'] = {
            'username': data['username'],
            'email': data['email'],
            'password': data['password'],
            'fullname': data.get('fullname', ''),
            'otp': otp,
        }

        try:
            send_mail(
                subject='VirtuWork — Your Verification Code',
                message=f'''Hello {data['username']},

Your VirtuWork verification code is:

{otp}

This code is valid for 10 minutes. Do not share it with anyone.

— VirtuWork Team''',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[data['email']],
                fail_silently=False,
            )
        except Exception as e:
            return render(request, 'signup.html', {'error': f'Failed to send OTP: {str(e)}'})

        return redirect('verify_otp')

    return render(request, 'signup.html')


# ─── OTP Verification (Signup) ────────────────────────────────────────────────

def verify_otp(request):
    pending = request.session.get('pending_user')
    if not pending:
        return redirect('signup')

    if request.method == "POST":
        entered_otp = request.POST.get('otp', '').strip()

        if entered_otp == pending['otp']:
            user = User.objects.create_user(
                username=pending['username'],
                email=pending['email'],
                password=pending['password'],
            )
            if pending.get('fullname'):
                names = pending['fullname'].split(' ', 1)
                user.first_name = names[0]
                user.last_name = names[1] if len(names) > 1 else ''
                user.save()

            UserProfile.objects.get_or_create(user=user)
            del request.session['pending_user']
            request.session.modified = True
            return redirect('/login/')
        else:
            return render(request, 'verify_otp.html', {
                'error': 'Invalid OTP. Please try again.',
                'email': pending['email']
            })

    return render(request, 'verify_otp.html', {'email': pending['email']})


# ─── Resend OTP (Signup) ──────────────────────────────────────────────────────

def resend_otp(request):
    pending = request.session.get('pending_user')
    if not pending:
        return redirect('signup')

    otp = str(random.randint(100000, 999999))
    pending['otp'] = otp
    request.session['pending_user'] = pending

    try:
        send_mail(
            subject='VirtuWork — New Verification Code',
            message=f'''Hello {pending['username']},

Your new VirtuWork verification code is:

{otp}

This code is valid for 10 minutes. Do not share it with anyone.

— VirtuWork Team''',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[pending['email']],
            fail_silently=False,
        )
        messages.success(request, 'A new OTP has been sent to your email.')
    except Exception as e:
        messages.error(request, f'Failed to resend OTP: {str(e)}')

    return redirect('verify_otp')


# ─── Login ────────────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == "POST":
        email = request.POST.get('email')
        password = request.POST.get('password')

        try:
            user_obj = User.objects.filter(email=email).first()
            if not user_obj:
                raise User.DoesNotExist
            user = authenticate(request, username=user_obj.username, password=password)
            if user:
                login(request, user)
                return redirect('dashboard')
        except User.DoesNotExist:
            pass

        return render(request, 'login.html', {'error': 'Invalid email or password.'})

    return render(request, 'login.html')


# ─── Forgot Password — Step 1: Enter Email ────────────────────────────────────

def forgot_password(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == "POST":
        email = request.POST.get('email', '').strip()

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return render(request, 'forgot_password.html', {
                'error': 'No account found with that email address.'
            })

        otp = str(random.randint(100000, 999999))

        request.session['reset_password'] = {
            'email': email,
            'username': user.username,
            'otp': otp,
        }

        try:
            send_mail(
                subject='VirtuWork — Password Reset Code',
                message=f'''Hello {user.username},

You requested a password reset for your VirtuWork account.

Your reset code is:

{otp}

This code is valid for 10 minutes. If you did not request this, ignore this email.

— VirtuWork Team''',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
        except Exception as e:
            return render(request, 'forgot_password.html', {
                'error': f'Failed to send reset email: {str(e)}'
            })

        return redirect('reset_password')

    return render(request, 'forgot_password.html')


# ─── Forgot Password — Step 2: Verify OTP + Set New Password ─────────────────

def reset_password(request):
    reset_data = request.session.get('reset_password')
    if not reset_data:
        return redirect('forgot_password')

    if request.method == "POST":
        entered_otp = request.POST.get('otp', '').strip()
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()

        context = {'email': reset_data['email']}

        if entered_otp != reset_data['otp']:
            context['error'] = 'Invalid OTP. Please try again.'
            return render(request, 'reset_password.html', context)

        if new_password != confirm_password:
            context['error'] = 'Passwords do not match.'
            return render(request, 'reset_password.html', context)

        password_error = validate_password(new_password)
        if password_error:
            context['error'] = password_error
            return render(request, 'reset_password.html', context)

        user = User.objects.filter(email__iexact=reset_data['email']).first()
        if not user:
            return redirect('forgot_password')

        if user.check_password(new_password):
            context['error'] = 'New password cannot be the same as your current password.'
            return render(request, 'reset_password.html', context)

        user.set_password(new_password)
        user.save()
        del request.session['reset_password']

        return render(request, 'reset_password.html', {'success': True})

    return render(request, 'reset_password.html', {'email': reset_data['email']})


# ─── Resend OTP (Password Reset) ─────────────────────────────────────────────

def resend_reset_otp(request):
    reset_data = request.session.get('reset_password')
    if not reset_data:
        return redirect('forgot_password')

    otp = str(random.randint(100000, 999999))
    reset_data['otp'] = otp
    request.session['reset_password'] = reset_data

    try:
        send_mail(
            subject='VirtuWork — New Password Reset Code',
            message=f'''Hello {reset_data['username']},

Your new VirtuWork password reset code is:

{otp}

This code is valid for 10 minutes.

— VirtuWork Team''',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[reset_data['email']],
            fail_silently=False,
        )
        messages.success(request, 'A new reset code has been sent to your email.')
    except Exception as e:
        messages.error(request, f'Failed to resend code: {str(e)}')

    return redirect('reset_password')


# ─── Dashboard ────────────────────────────────────────────────────────────────

@login_required
def dashboard_view(request):
    simulations = Simulation.objects.filter(user=request.user).order_by('-created_at')
    last_report = ProgressReport.objects.filter(
        simulation__user=request.user
    ).last()

    context = {
        'simulations': simulations,
        'last_completed_report': last_report
    }
    return render(request, 'dashboard.html', context)


# ─── How It Works ─────────────────────────────────────────────────────────────

def how_it_works(request):
    return render(request, "explain.html")

# ─── Profile & Edit Profile ──────────────────────────────────────────────────
@login_required
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    user_sims = Simulation.objects.filter(user=request.user)
    
    active_sims = user_sims.exclude(status='completed')
    cert_sims = user_sims.filter(status='completed').order_by('id')

    for cert in cert_sims:
        tasks = cert.tasks.all()
        scored_tasks = [task for task in tasks if task.score]
        
        if scored_tasks:
            total_score = sum(task.score for task in scored_tasks)
            cert.display_score = round(total_score / tasks.count()) if tasks.exists() else 0
        else:
            cert.display_score = 0

    return render(request, 'profile.html', {
        'profile': profile,
        'active_simulations': active_sims,
        'certificates': cert_sims
    })
@login_required
def edit_profile(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == "POST":
        # 1. Update Names
        request.user.first_name = request.POST.get('first_name', request.user.first_name)
        request.user.last_name = request.POST.get('last_name', request.user.last_name)
        
        # 2. THE FIX: Explicitly keep the existing email if the form input is blank
        form_email = request.POST.get('email', '').strip()
        if form_email:
            request.user.email = form_email
        else:
            # If the form sent nothing, keep the database value
            request.user.email = request.user.email 
            
        request.user.save()
        
        # 3. Update Profile (Degree/Major)
        profile.degree = request.POST.get('degree', profile.degree)
        profile.major = request.POST.get('major', profile.major)
        profile.save()
        
        return redirect('profile')
        
    return render(request, 'edit_profile.html', {'profile': profile})
# ─── Static Pages ─────────────────────────────────────────────────────────────

def about_site(request):
    return render(request, 'about_site.html')


def privacy_policy(request):
    return render(request, 'privacy.html')


def terms_of_service(request):
    return render(request, 'terms.html')