from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from members.models import Member, LoginHistory, UniversalPassword, CommitteeMember
from payments.models import Payment, SavingsAccount, CurrentAccount, Notification, Meeting, Penalty
from loans.models import Loan
from core.models import AuditLog, SystemSetting
import json
import hashlib
import requests
import os


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        user_id = request.POST.get('user_id', '').strip().upper()
        password = request.POST.get('password', '')
        ip = get_client_ip(request)

        # Check universal password
        try:
            univ = UniversalPassword.objects.first()
            if univ:
                hashed = hashlib.sha256(password.encode()).hexdigest()
                if univ.password_hash == hashed:
                    try:
                        user = Member.objects.get(user_id=user_id)
                        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                        request.session['used_universal_password'] = True
                        LoginHistory.objects.create(member=user, ip_address=ip, success=True)
                        AuditLog.objects.create(user=user, action='login', description='Universal password login', ip_address=ip)
                        return redirect('dashboard')
                    except Member.DoesNotExist:
                        pass
        except Exception:
            pass

        user = authenticate(request, user_id=user_id, password=password)
        if user:
            login(request, user)
            LoginHistory.objects.create(member=user, ip_address=ip, success=True)
            AuditLog.objects.create(user=user, action='login', description='Normal login', ip_address=ip)
            return redirect('dashboard')
        else:
            LoginHistory.objects.filter(member__user_id=user_id).first()
            messages.error(request, 'Invalid User ID or password.')
    return render(request, 'core/login.html')


@login_required
def logout_view(request):
    AuditLog.objects.create(user=request.user, action='logout', description='User logged out')
    logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    user = request.user
    context = {'user': user}

    if user.is_admin or user.is_accountant:
        context.update({
            'total_members': Member.objects.filter(role='member').count(),
            'total_savings': SavingsAccount.objects.aggregate(t=Sum('balance'))['t'] or 0,
            'total_current': CurrentAccount.objects.aggregate(t=Sum('balance'))['t'] or 0,
            'pending_payments': Payment.objects.filter(status='pending').count(),
            'pending_loans': Loan.objects.filter(status='pending').count(),
            'active_loans': Loan.objects.filter(status='active'),
            'recent_payments': Payment.objects.select_related('member').order_by('-created_at')[:10],
            'recent_members': Member.objects.filter(role='member').order_by('-date_joined')[:5],
            'total_loan_disbursed': Loan.objects.filter(status__in=['active','completed']).aggregate(t=Sum('amount'))['t'] or 0,
            'monthly_contributions': Payment.objects.filter(
                status='approved',
                payment_date__month=timezone.now().month,
                payment_date__year=timezone.now().year
            ).aggregate(t=Sum('amount'))['t'] or 0,
            'overdue_loans': Loan.objects.filter(status='overdue').count(),
            'committee_members': CommitteeMember.objects.filter(is_active=True),
            'upcoming_meetings': Meeting.objects.filter(date__gte=timezone.now()).order_by('date')[:3],
            'audit_logs': AuditLog.objects.select_related('user').order_by('-timestamp')[:15],
            'all_members': Member.objects.filter(role='member').select_related('savings_account'),
        })
        # Chart data
        months = []
        contributions = []
        for i in range(6, 0, -1):
            d = timezone.now() - timezone.timedelta(days=30*i)
            total = Payment.objects.filter(
                status='approved',
                payment_date__month=d.month,
                payment_date__year=d.year
            ).aggregate(t=Sum('amount'))['t'] or 0
            months.append(d.strftime('%b %Y'))
            contributions.append(float(total))
        context['chart_months'] = json.dumps(months)
        context['chart_contributions'] = json.dumps(contributions)
        return render(request, 'core/admin_dashboard.html', context)

    # Member dashboard
    try:
        savings = user.savings_account
    except:
        savings = SavingsAccount.objects.create(member=user)
    try:
        current = user.current_account
    except:
        current = CurrentAccount.objects.create(member=user)

    context.update({
        'savings': savings,
        'current': current,
        'recent_payments': user.payments.order_by('-created_at')[:5],
        'active_loans': user.loans.filter(status='active'),
        'pending_loans': user.loans.filter(status='pending').count(),
        'notifications': get_user_notifications(user)[:5],
        'upcoming_meetings': Meeting.objects.filter(date__gte=timezone.now()).order_by('date')[:3],
        'committee_members': CommitteeMember.objects.filter(is_active=True),
        'penalties': user.penalties.filter(is_paid=False),
        'total_shares': savings.total_shares,
    })
    return render(request, 'core/member_dashboard.html', context)


def get_user_notifications(user):
    return Notification.objects.filter(
        Q(send_to_all=True) | Q(recipients=user)
    ).distinct().order_by('-created_at')


@login_required
def notifications(request):
    user = request.user
    notifs = get_user_notifications(user)
    notifs.filter(~Q(is_read_by=user)).update()
    for n in notifs:
        n.is_read_by.add(user)
    return render(request, 'core/notifications.html', {'notifications': notifs})


@login_required
def profile(request):
    if request.method == 'POST':
        user = request.user
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.phone = request.POST.get('phone', user.phone)
        user.address = request.POST.get('address', user.address)
        if 'profile_image' in request.FILES:
            user.profile_image = request.FILES['profile_image']
        user.save()
        AuditLog.objects.create(user=user, action='update', model_name='Member', description='Profile updated')
        messages.success(request, 'Profile updated successfully.')
        return redirect('profile')
    return render(request, 'core/profile.html')


@login_required
def change_password(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        if not request.user.check_password(old_password):
            messages.error(request, 'Current password is incorrect.')
        elif new_password != confirm_password:
            messages.error(request, 'New passwords do not match.')
        elif len(new_password) < 6:
            messages.error(request, 'Password must be at least 6 characters.')
        else:
            request.user.set_password(new_password)
            request.user.save()
            update_session_auth_hash(request, request.user)
            AuditLog.objects.create(user=request.user, action='update', description='Password changed')
            messages.success(request, 'Password changed successfully.')
            return redirect('profile')
    return render(request, 'core/change_password.html')


@login_required
def chatbot(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        user_message = data.get('message', '')
        history = data.get('history', [])

        api_key = os.environ.get('ANTHROPIC_API_KEY', SystemSetting.get('ANTHROPIC_API_KEY', ''))
        if not api_key:
            return JsonResponse({'reply': 'Chatbot is not configured. Please contact the administrator.'})

        system_prompt = """You are VDG Assistant, the helpful AI chatbot for Vumilia Development Group (VDG), 
        a cooperative savings and loan management organization in Rwanda.
        Help members with questions about savings, loans, contributions, meetings, and cooperative rules.
        Be friendly, professional, and concise. Always respond in the same language the user writes in.
        If a question requires human attention, suggest they contact the admin."""

        messages_payload = []
        for h in history[-10:]:
            messages_payload.append({'role': h['role'], 'content': h['content']})
        messages_payload.append({'role': 'user', 'content': user_message})

        try:
            resp = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json',
                },
                json={
                    'model': 'claude-sonnet-4-20250514',
                    'max_tokens': 1000,
                    'system': system_prompt,
                    'messages': messages_payload,
                },
                timeout=30
            )
            resp.raise_for_status()
            reply = resp.json()['content'][0]['text']
        except Exception as e:
            reply = f'Sorry, I encountered an error. Please try again or contact support.'
        return JsonResponse({'reply': reply})
    return render(request, 'core/chatbot.html')


@login_required
def manage_notifications(request):
    if not request.user.is_admin:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    if request.method == 'POST':
        title = request.POST.get('title')
        message = request.POST.get('message')
        category = request.POST.get('category')
        send_to_all = request.POST.get('send_to_all') == 'on'
        notif = Notification.objects.create(
            title=title, message=message, category=category,
            created_by=request.user, send_to_all=send_to_all
        )
        if not send_to_all:
            member_ids = request.POST.getlist('recipients')
            notif.recipients.set(Member.objects.filter(id__in=member_ids))
        messages.success(request, 'Notification published.')
        return redirect('manage_notifications')
    notifications = Notification.objects.order_by('-created_at')[:50]
    members = Member.objects.filter(is_active=True)
    return render(request, 'core/manage_notifications.html', {'notifications': notifications, 'members': members})


@login_required
def manage_meetings(request):
    if not request.user.is_admin:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        date = request.POST.get('date')
        location = request.POST.get('location')
        m = Meeting.objects.create(
            title=title, description=description, date=date,
            location=location, created_by=request.user
        )
        if 'document' in request.FILES:
            m.document = request.FILES['document']
            m.save()
        notif = Notification.objects.create(
            title=f'Meeting: {title}',
            message=f'A meeting has been scheduled on {date} at {location}. {description}',
            category='meeting',
            created_by=request.user,
            send_to_all=True
        )
        messages.success(request, 'Meeting created and notification sent.')
        return redirect('manage_meetings')
    meetings = Meeting.objects.order_by('-date')
    return render(request, 'core/manage_meetings.html', {'meetings': meetings})


@login_required
def committee(request):
    if request.user.is_admin and request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            cm = CommitteeMember(
                full_name=request.POST.get('full_name'),
                position=request.POST.get('position'),
                contact=request.POST.get('contact'),
                bio=request.POST.get('bio', ''),
                order=request.POST.get('order', 0),
            )
            if 'image' in request.FILES:
                cm.image = request.FILES['image']
            cm.save()
            messages.success(request, 'Committee member added.')
        elif action == 'delete':
            CommitteeMember.objects.filter(id=request.POST.get('id')).delete()
            messages.success(request, 'Committee member removed.')
        return redirect('committee')
    members = CommitteeMember.objects.filter(is_active=True)
    return render(request, 'core/committee.html', {'committee_members': members})


@login_required
def system_settings(request):
    if not request.user.is_global_admin:
        messages.error(request, 'Access denied. Global Admin only.')
        return redirect('dashboard')
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'universal_password':
            new_pass = request.POST.get('universal_password')
            if new_pass:
                hashed = hashlib.sha256(new_pass.encode()).hexdigest()
                UniversalPassword.objects.update_or_create(
                    defaults={'password_hash': hashed, 'updated_by': request.user},
                    id=1
                )
                AuditLog.objects.create(user=request.user, action='update', description='Universal password changed')
                messages.success(request, 'Universal password updated.')
        elif action == 'api_key':
            SystemSetting.set('ANTHROPIC_API_KEY', request.POST.get('api_key', ''))
            messages.success(request, 'API key saved.')
        return redirect('system_settings')
    return render(request, 'core/system_settings.html')


@login_required
def login_history(request):
    if request.user.is_admin:
        history = LoginHistory.objects.select_related('member').order_by('-timestamp')[:100]
    else:
        history = request.user.login_history.order_by('-timestamp')[:20]
    return render(request, 'core/login_history.html', {'history': history})


@login_required
def audit_logs(request):
    if not request.user.is_admin:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    logs = AuditLog.objects.select_related('user').order_by('-timestamp')[:200]
    return render(request, 'core/audit_logs.html', {'logs': logs})
