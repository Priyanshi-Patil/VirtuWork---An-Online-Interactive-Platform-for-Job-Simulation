from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.contrib.auth.models import User
import traceback
import random
import json
import threading
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from .models import Simulation, Task
from evaluation.models import TaskSubmission
from .agents import *
from django.shortcuts import get_object_or_404, redirect
from agents.models import Conversation, Message
from django.http import JsonResponse, HttpResponse
from .agents import TaskEvaluatorAgent
import asyncio
from playwright.async_api import async_playwright
from django.core.mail import send_mail
from .dataset_utils import get_dataset_for_project
from django.conf import settings


# ─── OTP: Send ────────────────────────────────────────────────────────────────

def send_otp(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error'}, status=405)
    try:
        data  = json.loads(request.body)
        email = data.get('email', '').strip().lower()
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    otp = str(random.randint(100000, 999999))
    request.session['otp_code']  = otp
    request.session['otp_email'] = email
    request.session.modified     = True

    print(f'[DEV OTP] {email} → {otp}')

    return JsonResponse({'status': 'sent'})


# ─── OTP: Verify + Create Account ────────────────────────────────────────────

def verify_otp(request):
    if request.method != 'POST':
        return redirect('signup')

    entered  = request.POST.get('otp', '').strip()
    email    = request.POST.get('email', '').strip().lower()
    fullname = request.POST.get('fullname', '').strip()
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')

    stored_otp   = request.session.get('otp_code', '')
    stored_email = request.session.get('otp_email', '').lower()

    if not stored_otp or entered != stored_otp or email != stored_email:
        return render(request, 'signup.html', {
            'otp_error': 'Invalid or expired code. Please try again.'
        })

    if User.objects.filter(email=email).exists():
        return render(request, 'signup.html', {'otp_error': 'Email already registered.'})
    if User.objects.filter(username=username).exists():
        return render(request, 'signup.html', {'otp_error': 'Username already taken.'})

    parts = fullname.split(' ', 1)
    user  = User.objects.create_user(
        username=username, email=email, password=password,
        first_name=parts[0], last_name=parts[1] if len(parts) > 1 else ''
    )

    request.session.pop('otp_code',  None)
    request.session.pop('otp_email', None)
    login(request, user)
    return redirect('dashboard')


# ─── Email availability check ─────────────────────────────────────────────────

def check_email(request):
    email  = request.GET.get('email', '').strip()
    exists = User.objects.filter(email=email).exists()
    return JsonResponse({'exists': exists})


# ─── Static pages ─────────────────────────────────────────────────────────────

def about_site(request):
    return render(request, 'about_site.html')

def privacy_policy(request):
    return render(request, 'privacy.html')

def terms_of_service(request):
    return render(request, 'terms.html')


# ─── Background AI worker ─────────────────────────────────────────────────────

def _run_ai_setup(simulation_id):
    """
    Runs in a background thread. Calls ThinkerAgent + PlannerAgent
    and marks sim.status = 'ready' when done, or 'error' on failure.
    Uses a fresh DB connection safe for threading.
    """
    import django
    from django.db import connection

    try:
        sim = Simulation.objects.get(id=simulation_id)

        # Mark as processing so the poll knows it started
        sim.status = 'processing'
        sim.save()

        # Step 1: Thinker designs project
        thinker      = ThinkerAgent()
        project_info = thinker.generate_project(sim.role_title, "User technical background")
        if not project_info:
            raise Exception("ThinkerAgent returned no data.")

        sim.project_title = project_info.get('title', f'{sim.role_title} Project')
        sim.description   = project_info.get('description', 'A professional simulation project.')
        names             = project_info.get('agents', {})
        sim.hr_name       = names.get('hr_name',     'Sarah')
        sim.peer_name     = names.get('peer_name',   'Alex')
        sim.client_name   = names.get('client_name', 'Michael')
        sim.save()

        # Step 2: Planner creates tasks
        planner = PlannerAgent()
        planner.create_subtasks(sim)

        # Step 3: Setup conversations + HR greeting
        for role in ['HR', 'PEER', 'CLIENT']:
            Conversation.objects.get_or_create(
                simulation=sim, agent_type=role,
                defaults={'session_id': f"sim_{sim.id}_{role.lower()}"}
            )

        hr_conv = Conversation.objects.get(simulation=sim, agent_type='HR')
        intro_text = (
            f"Hello! I'm {sim.hr_name}, your HR lead. "
            f"Welcome to the '{sim.project_title}' project simulation. "
            f"I'm here to guide you through onboarding and answer any administrative questions."
        )
        Message.objects.create(conversation=hr_conv, sender="HR", text=intro_text)

        # Mark as ready
        sim.status = 'ongoing'
        sim.save()
        print(f"[AI Setup] Simulation {simulation_id} ready.")

    except Exception as e:
        traceback.print_exc()
        try:
            sim = Simulation.objects.get(id=simulation_id)
            sim.status = 'error'
            sim.save()
        except Exception:
            pass
    finally:
        connection.close()


# ─── Simulation management ────────────────────────────────────────────────────

@login_required
def delete_simulation(request, sim_id):
    if request.method == "POST":
        simulation = get_object_or_404(Simulation, id=sim_id, user=request.user)
        simulation.delete()
    return redirect('dashboard')


@login_required
def resume_simulation(request, sim_id):
    return redirect('simulation_chat', simulation_id=sim_id)


@login_required
def create_simulation(request):
    if request.method == "POST":
        role = request.POST.get('job_role')
        edu  = request.POST.get('education')

        sim = Simulation.objects.create(
            user=request.user,
            role_title=role,
            status='ongoing'
        )

        # Start AI setup in background thread immediately
        t = threading.Thread(target=_run_ai_setup, args=(sim.id,), daemon=True)
        t.start()

        # Return loading page instantly — no waiting
        return render(request, 'loading.html', {'simulation_id': sim.id})


@login_required
def check_simulation_ready(request, simulation_id):
    """
    Polled by the loading page every 3 seconds.
    Returns JSON with the current status.
    """
    sim = get_object_or_404(Simulation, id=simulation_id, user=request.user)
    tasks_count = sim.tasks.count()

    if sim.status == 'error':
        return JsonResponse({'status': 'error', 'message': 'Setup failed. Please try again.'})

    if tasks_count > 0 and sim.project_title:
        return JsonResponse({'status': 'ready'})

    return JsonResponse({'status': 'processing'})


@login_required
def initiate_ai_logic(request, simulation_id):
    """
    Kept for backwards compatibility.
    Now just triggers background thread if not already running.
    """
    sim = get_object_or_404(Simulation, id=simulation_id, user=request.user)

    if sim.tasks.count() > 0:
        return JsonResponse({'status': 'success'})

    t = threading.Thread(target=_run_ai_setup, args=(sim.id,), daemon=True)
    t.start()

    return JsonResponse({'status': 'success'})


@login_required
def simulation_chat(request, simulation_id):
    sim = get_object_or_404(Simulation, id=simulation_id, user=request.user)

    # Safety check — replace generic names with Marathi names
    marathi_hr     = ['Anjali', 'Snehal', 'Tanvi', 'Sayali', 'Swanandi', 'Madhura', 'Pooja', 'Ashwini', 'Shravani']
    marathi_peer   = ['Aditya', 'Rohan', 'Prathamesh', 'Sahil', 'Karan', 'Satyarth', 'Siddharth', 'Pranay']
    marathi_client = ['Mr. Deshmukh', 'Mr. Patil', 'Mr. Kulkarni', 'Mr. Joshi', 'Mr. Jadhav', 'Mr. Shinde', 'Mr. Pawar']

    updated = False
    if sim.hr_name in [None, 'Sarah', 'HR']:
        sim.hr_name = random.choice(marathi_hr)
        updated = True
    if sim.peer_name in [None, 'Alex', 'Peer']:
        sim.peer_name = random.choice(marathi_peer)
        updated = True
    if sim.client_name in [None, 'Michael', 'Client']:
        sim.client_name = random.choice(marathi_client)
        updated = True
    if updated:
        sim.save()

    tasks           = sim.tasks.all().order_by('order')
    current_task    = tasks.filter(is_completed=False).first()
    completed_tasks = tasks.filter(is_completed=True).order_by('-order')

    hr_conv, _ = Conversation.objects.get_or_create(
        simulation=sim, agent_type='HR',
        defaults={'session_id': f"sim_{sim.id}_hr"}
    )
    peer_conv, _ = Conversation.objects.get_or_create(
        simulation=sim, agent_type='PEER',
        defaults={'session_id': f"sim_{sim.id}_peer"}
    )
    client_conv, _ = Conversation.objects.get_or_create(
        simulation=sim, agent_type='CLIENT',
        defaults={'session_id': f"sim_{sim.id}_client"}
    )

    conv_dict = {'hr': hr_conv, 'peer': peer_conv, 'client': client_conv}
    messages_qs   = Message.objects.filter(conversation__simulation=sim).order_by('timestamp')
    tasks_loading = tasks.count() == 0 and sim.status == 'ongoing'

    context = {
        'sim':            sim,
        'conversations':  conv_dict,
        'messages':       messages_qs,
        'current_task':   current_task,
        'completed_tasks': completed_tasks,
        'agent_list':     ['hr', 'peer', 'client'],
        'tasks_loading':  tasks_loading,
    }
    return render(request, 'simulation_chat.html', context)


@login_required
def send_message(request):
    if request.method == "POST":
        conv_id   = request.POST.get('conversation_id')
        user_text = request.POST.get('text')

        conv = get_object_or_404(Conversation, id=conv_id, simulation__user=request.user)
        sim  = conv.simulation

        Message.objects.create(conversation=conv, sender="User", text=user_text)
        agent       = ConversationAgent(role_type=conv.agent_type)
        ai_response = agent.get_response(sim, user_text)
        Message.objects.create(conversation=conv, sender=conv.agent_type, text=ai_response)

        if conv.messages.count() % 10 == 0:
            summarizer = SummarizerAgent()
            summarizer.summarize_chat(conv)

        return redirect('simulation_chat', simulation_id=sim.id)


@login_required
def submit_task(request):
    if request.method == "POST":
        sim_id   = request.POST.get('simulation_id')
        task_id  = request.POST.get('task_id')
        zip_file = request.FILES.get('project_zip')

        simulation = get_object_or_404(Simulation, id=sim_id, user=request.user)
        task       = get_object_or_404(Task, id=task_id, simulation=simulation)

        # ZIP validation — don't count attempt if not a zip
        if not zip_file or not zip_file.name.endswith('.zip'):
            messages.error(request, 'Please upload a valid ZIP file. Your attempt was not counted.')
            return redirect('simulation_chat', simulation_id=sim_id)

        task.attempts += 1
        task.save()

        if not simulation.expected_output_template:
            thinker = ThinkerAgent()
            simulation.expected_output_template = thinker.generate_task_solution(
                simulation.project_title, task.instruction
            )
            simulation.save()

        evaluator   = TaskEvaluatorAgent()
        result_text = evaluator.evaluate(simulation, task, zip_file)

        try:
            score    = int(''.join(filter(str.isdigit, result_text.split('|')[0])))
            feedback = result_text.split('|')[1].replace('FEEDBACK:', '').strip()
        except Exception:
            score, feedback = 0, "Evaluation parsing failed."

        is_last_attempt = (task.attempts >= 3)
        passed          = (score >= 70)
        peer_conv       = Conversation.objects.filter(simulation=simulation, agent_type='PEER').first()

        if passed:
            task.is_completed = True
            msg_text = f"Great work! Your submission for '{task.title}' passed with {score}%. {feedback}"
        elif not passed and not is_last_attempt:
            msg_text = (
                f"I've reviewed your submission for '{task.title}'. Score: {score}%. "
                f"Feedback: {feedback}. You have {3 - task.attempts} attempts left."
            )
        else:
            task.is_completed = True
            msg_text = (
                f"I've reviewed your third attempt for '{task.title}'. Score: {score}%. "
                f"Feedback: {feedback}. Here is the expected solution:\n\n"
                f"{simulation.expected_output_template}\n\nLet's move to the next task."
            )
            simulation.expected_output_template = ""
            simulation.save()

        TaskSubmission.objects.create(
            task=task, zip_file=zip_file,
            attempt_number=task.attempts, score=score,
            feedback=feedback, is_success=(score >= 70)
        )
        task.score    = score
        task.feedback = feedback
        task.save()

        if peer_conv:
            Message.objects.create(conversation=peer_conv, sender="PEER", text=msg_text)

        return redirect('simulation_chat', simulation_id=sim_id)


@login_required
def send_message_ajax(request):
    conv_id = request.POST.get('conversation_id')
    text    = request.POST.get('text')
    conv    = get_object_or_404(Conversation, id=conv_id, simulation__user=request.user)
    sim     = conv.simulation

    Message.objects.create(conversation=conv, sender="User", text=text)
    agent       = ConversationAgent(role_type=conv.agent_type)
    ai_response = agent.get_response(sim, text)
    Message.objects.create(conversation=conv, sender=conv.agent_type, text=ai_response)

    current_task   = sim.tasks.filter(is_completed=False).order_by('order').first()
    task_updated   = False
    all_tasks_done = False

    if current_task and not current_task.requires_submission:
        keywords = ['understand', 'understood', 'done', 'proceed', 'clear', 'ready', 'okay']
        if any(word in text.lower() for word in keywords):
            current_task.is_completed = True
            current_task.score        = 100
            current_task.attempts     = 1
            current_task.save()

            current_task = sim.tasks.filter(is_completed=False).order_by('order').first()
            task_updated = True

            if current_task:
                ai_response = (
                    f"Excellent! Since you're clear on that, let's move to: '{current_task.title}'. "
                    f"Check the Project Overview for instructions."
                )
            else:
                all_tasks_done = True
                sim.status     = 'completed'
                sim.save()
                ai_response = (
                    f"Congratulations! You have successfully completed all milestones for the "
                    f"'{sim.project_title}' project. Your final performance report is now ready."
                )

            last_msg = Message.objects.filter(conversation=conv).last()
            if last_msg:
                last_msg.text = ai_response
                last_msg.save()

    return JsonResponse({
        'ai_message':     ai_response,
        'task_updated':   task_updated,
        'all_tasks_done': all_tasks_done,
        'new_task': {
            'title':               current_task.title if current_task else "Project Completed",
            'instruction':         current_task.instruction if current_task else "All milestones completed.",
            'requires_submission': current_task.requires_submission if current_task else False,
            'id':                  current_task.id if current_task else None
        } if current_task else None
    })


@login_required
def end_simulation_report(request, simulation_id):
    sim   = get_object_or_404(Simulation, id=simulation_id, user=request.user)
    tasks = sim.tasks.all()

    if tasks.exists():
        total_score   = sum(task.score for task in tasks if task.score)
        overall_score = round(total_score / tasks.count())
    else:
        overall_score = 0

    is_newly_completed = False
    if not sim.final_report_data or request.GET.get('refresh') == 'true':
        if sim.status != 'completed':
            is_newly_completed = True
        sim.status = 'completed'
        perf_agent  = PerformanceAgent()
        report_data = perf_agent.generate_final_report(sim)
        sim.final_report_data = report_data
        sim.save()

    if is_newly_completed:
        try:
            send_mail(
                subject=f"Congratulations! You've completed your {sim.role_title} Simulation",
                message=(
                    f"Hi {request.user.first_name},\n\n"
                    f"You have successfully completed the '{sim.project_title}' simulation.\n"
                    f"Your Final Score: {overall_score}%\n\n"
                    f"Log in to download your certificate.\n\n— Team VirtuWork"
                ),
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[request.user.email],
                fail_silently=True,
            )
        except Exception as e:
            print(f"Email failed: {e}")

    return render(request, 'final_report.html', {
        'sim':           sim,
        'report':        sim.final_report_data,
        'overall_score': overall_score,
    })


@login_required
def profile_view(request):
    from .models import Profile
    profile, created = Profile.objects.get_or_create(user=request.user)

    if request.method == 'POST' and request.FILES.get('profile_photo'):
        profile.profile_photo = request.FILES['profile_photo']
        profile.save()
        return redirect('profile')

    all_sims = Simulation.objects.filter(user=request.user).order_by('-created_at')

    for sim in all_sims:
        tasks = sim.tasks.all()
        if tasks.exists():
            total             = sum(t.score for t in tasks if t.score)
            sim.overall_score = round(total / tasks.count())
        else:
            sim.overall_score = 0

    completed_sims = [s for s in all_sims if s.status == 'completed']
    ongoing_sims   = [s for s in all_sims if s.status == 'ongoing']

    career_readiness = None
    if completed_sims:
        tech_scores, comm_scores, ps_scores = [], [], []
        for sim in completed_sims:
            if sim.final_report_data and isinstance(sim.final_report_data, dict):
                tech_scores.append(sim.final_report_data.get('technical_score', 0))
                comm_scores.append(sim.final_report_data.get('communication_score', 0))
                ps_scores.append(sim.final_report_data.get('problem_solving_score', 0))
        if tech_scores:
            career_readiness = {
                'technical':       round(sum(tech_scores) / len(tech_scores)),
                'communication':   round(sum(comm_scores) / len(comm_scores)),
                'problem_solving': round(sum(ps_scores)   / len(ps_scores)),
            }

    return render(request, 'profile.html', {
        'user':             request.user,
        'profile':          profile,
        'certificates':     completed_sims,
        'history':          ongoing_sims,
        'total_sims':       all_sims.count(),
        'career_readiness': career_readiness,
    })


def certificate_view(request, simulation_id):
    sim   = get_object_or_404(Simulation, id=simulation_id)
    tasks = sim.tasks.all()

    total_score   = sum(task.score for task in tasks if task.score)
    overall_score = round(total_score / tasks.count()) if tasks.exists() else 0
    cert_id       = f"VW-{sim.created_at.year}-{sim.id:04d}"
    start_date    = sim.created_at

    try:
        completion_date = sim.updated_at
    except AttributeError:
        completion_date = sim.created_at

    from django.urls import reverse
    verify_url = request.build_absolute_uri(reverse('verify_certificate', args=[simulation_id]))

    return render(request, "certificate.html", {
        "user":             sim.user,
        "sim":              sim,
        "overall_score":    overall_score,
        "cert_id":          cert_id,
        "start_date":       start_date,
        "completion_date":  completion_date,
        "verify_url":       verify_url,
    })


@login_required
def download_certificate_pdf(request, sim_id):
    sim = get_object_or_404(Simulation, id=sim_id, user=request.user, status='completed')

    async def generate_pdf():
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context()
            await context.add_cookies([{
                'name': 'sessionid', 'value': request.COOKIES.get('sessionid'),
                'domain': '127.0.0.1', 'path': '/'
            }])
            page = await context.new_page()
            url  = request.build_absolute_uri(f"/certificate/{sim_id}/")
            await page.goto(url)
            await page.add_style_tag(content="""
                @media print {
                    nav, .text-right, .text-center button { display: none !important; }
                    body { background: none !important; }
                    .certificate-bg { margin: 0 !important; border: none !important; }
                }
            """)
            pdf_bytes = await page.pdf(format="Letter", landscape=True, print_background=True)
            await browser.close()
            return pdf_bytes

    pdf_content = asyncio.run(generate_pdf())
    response    = HttpResponse(pdf_content, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Certificate_{sim.role_title}.pdf"'
    return response


def login_view(request):
    if request.method == "POST":
        email    = request.POST.get('email')
        password = request.POST.get('password')

        authenticated_user = None
        for user_obj in User.objects.filter(email=email):
            user = authenticate(request, username=user_obj.username, password=password)
            if user is not None:
                authenticated_user = user
                break

        if authenticated_user:
            login(request, authenticated_user)
            return redirect('dashboard')
        else:
            messages.error(request, "Invalid credentials. Please check your password.")

    return render(request, 'login.html')


@login_required
def edit_profile(request):
    if request.method == 'POST':
        request.user.first_name = request.POST.get('first_name')
        request.user.last_name  = request.POST.get('last_name')
        request.user.email      = request.POST.get('email')
        request.user.save()
        return redirect('profile')
    return render(request, 'edit_profile.html', {'user': request.user})


def verify_certificate(request, simulation_id):
    sim   = get_object_or_404(Simulation, id=simulation_id)
    tasks = sim.tasks.all()
    overall_score = round(sum(t.score for t in tasks if t.score) / tasks.count()) if tasks.exists() else 0
    return render(request, 'verify_certificate.html', {
        'sim': sim, 'overall_score': overall_score, 'user': sim.user,
    })


# ─── Dataset Download ─────────────────────────────────────────────────────────

@login_required
def download_project_dataset(request, simulation_id):
    sim = get_object_or_404(Simulation, id=simulation_id, user=request.user)

    project_title       = sim.project_title or sim.role_title or "General Project"
    project_description = sim.description or ""

    try:
        csv_bytes, filename = get_dataset_for_project(project_title, project_description)
    except Exception as e:
        return HttpResponse(f"Failed to generate dataset: {str(e)}", status=500)

    response = HttpResponse(csv_bytes, content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Content-Length'] = len(csv_bytes)
    return response