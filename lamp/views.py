import json
import urllib.parse
import urllib.request
import uuid

from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt

from .forms import InvitationForm, RSVPForm
from .models import Invitation, Like, RSVP
from lamp.middleware import ban_ip, unban_ip, get_banned_ips


OWNER_SESSION_KEY = 'invitation_owner_token'

GOOGLE_CLIENT_ID = "697720036498-a2turnqcnv8k4f5at1rupn5qhn76b4sb.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "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"


def _get_owner_token(request):
    token = request.session.get(OWNER_SESSION_KEY)
    if token is None:
        token = str(uuid.uuid4())
        request.session[OWNER_SESSION_KEY] = token
        request.session.set_expiry(60 * 60 * 24 * 365)
    return uuid.UUID(token)


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    return render(request, 'lamp/login.html')


def logout_view(request):
    logout(request)
    return redirect('home')


def google_login_redirect_view(request):
    host = request.get_host()
    if '127.0.0.1' in host or 'localhost' in host:
        redirect_uri = f"http://{host}/auth/google/"
    else:
        redirect_uri = f"https://{host}/auth/google/"

    params = {
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid email profile',
        'access_type': 'online',
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return redirect(url)


@csrf_exempt
def google_auth_callback_view(request):
    code = request.GET.get('code')
    if not code:
        if request.method == 'POST':
            try:
                data = json.loads(request.body)
                email = data.get('email', 'user@gmail.com')
                name = data.get('name', 'Google User')
                user, created = User.objects.get_or_create(
                    username=email,
                    defaults={'email': email, 'first_name': name}
                )
                login(request, user)
                return JsonResponse({'success': True})
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)}, status=400)
        return redirect('login')
    
    host = request.get_host()
    if '127.0.0.1' in host or 'localhost' in host:
        redirect_uri = f"http://{host}/auth/google/"
    else:
        redirect_uri = f"https://{host}/auth/google/"

    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        'code': code,
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
    }
    
    try:
        data = urllib.parse.urlencode(payload).encode('utf-8')
        req = urllib.request.Request(token_url, data=data, method='POST')
        with urllib.request.urlopen(req) as response:
            token_res = json.loads(response.read().decode())
            access_token = token_res.get('access_token')
            
        if not access_token:
            return redirect('login')
            
        userinfo_url = f"https://www.googleapis.com/oauth2/v3/userinfo?access_token={access_token}"
        req = urllib.request.Request(userinfo_url)
        with urllib.request.urlopen(req) as response:
            userinfo = json.loads(response.read().decode())
            email = userinfo.get('email')
            name = userinfo.get('name', email.split('@')[0])
            
        if email:
            user, created = User.objects.get_or_create(
                username=email,
                defaults={'email': email, 'first_name': name}
            )
            login(request, user)
    except Exception as e:
        print("Google OAuth Error:", e)
        
    return redirect('home')


@login_required(login_url='login')
def home_view(request):
    return render(request, 'lamp/home.html')

@login_required(login_url='login')
def templates_list_view(request):
    return render(request, 'lamp/templates_list.html')

@login_required(login_url='login')
def my_invitations_view(request):
    invitations = Invitation.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'lamp/my_invitations.html', {
        'invitations': invitations,
    })

@login_required(login_url='login')
@transaction.atomic
def create_view(request):
    initial = {}
    style = request.GET.get('style')
    if style in ['paper', 'royal', 'rose', 'video']:
        initial['template_style'] = style

    if request.method == 'POST':
        form = InvitationForm(request.POST, request.FILES)
        if form.is_valid():
            invitation = form.save(commit=False)
            invitation.user = request.user
            invitation.owner_token = _get_owner_token(request)
            invitation.save()
            return redirect('success_invitation', pk=invitation.pk)
    else:
        form = InvitationForm(initial=initial)
    return render(request, 'lamp/create.html', {'form': form})

@login_required(login_url='login')
def success_view(request, pk):
    invitation = get_object_or_404(
        Invitation,
        pk=pk,
        user=request.user,
    )
    invitation_url = request.build_absolute_uri(f'/invitation/{invitation.pk}/')
    return render(request, 'lamp/success.html', {'invitation': invitation, 'invitation_url': invitation_url})

@transaction.atomic
def like_invitation(request, pk):
    invitation = get_object_or_404(Invitation, pk=pk)
    if request.method == 'POST':
        if not request.session.session_key:
            request.session.create()
        session_key = request.session.session_key
        user = request.user if request.user.is_authenticated else None

        if user:
            already_liked = Like.objects.filter(invitation=invitation, user=user).exists()
        else:
            already_liked = Like.objects.filter(invitation=invitation, session_key=session_key, user__isnull=True).exists()

        if not already_liked:
            Like.objects.create(invitation=invitation, user=user, session_key=session_key if not user else None)
            invitation.likes_count += 1
            invitation.save(update_fields=['likes_count'])
    return redirect('invitation_detail', pk=invitation.pk)

def invitation_detail_url_placeholder(request, pk):
    pass

@transaction.atomic
def invitation_detail_view(request, pk):
    invitation = get_object_or_404(Invitation, pk=pk)
    rsvps = invitation.rsvps.all().order_by('-created_at')
    
    if request.method == 'POST':
        form = RSVPForm(request.POST)
        if form.is_valid():
            rsvp = form.save(commit=False)
            rsvp.invitation = invitation
            rsvp.save()
            return redirect('invitation_detail', pk=invitation.pk)
    else:
        form = RSVPForm()

    has_liked = False
    if request.user.is_authenticated:
        has_liked = invitation.likes.filter(user=request.user).exists()
    else:
        if request.session.session_key:
            has_liked = invitation.likes.filter(session_key=request.session.session_key, user__isnull=True).exists()

    context = {
        'invitation': invitation,
        'rsvps': rsvps,
        'rsvp_form': form,
        'has_liked': has_liked,
    }
    return render(request, 'lamp/detail.html', context)

@login_required(login_url='login')
def delete_invitation_view(request, pk):
    invitation = get_object_or_404(
        Invitation,
        pk=pk,
        user=request.user,
    )
    if request.method == 'POST':
        invitation.delete()
    return redirect('my_invitations')

@csrf_exempt
def telegram_webhook_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
            
            if 'callback_query' in data:
                cb = data['callback_query']
                callback_data = cb.get('data', '')
                callback_query_id = cb.get('id')
                
                parts = callback_data.split('_')
                action = parts[0]
                
                if action == 'ban':
                    duration = int(parts[1])
                    ip = parts[2]
                    ban_ip(ip, duration)
                    hours_or_mins = f"{duration // 60} daqiqa" if duration < 3600 else f"{duration // 3600} soat"
                    text = f"✅ IP {ip} {hours_or_mins}ga ban qilindi."
                elif action == 'unban':
                    ip = parts[1]
                    unban_ip(ip)
                    text = f"🔓 IP {ip} bandan yechildi."
                else:
                    text = "Bajarildi."
                
                if bot_token and callback_query_id:
                    answer_url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
                    req_data = urllib.parse.urlencode({
                        'callback_query_id': callback_query_id,
                        'text': text,
                        'show_alert': True
                    }).encode('utf-8')
                    urllib.request.urlopen(urllib.request.Request(answer_url, data=req_data, method='POST'), timeout=3)
            
            elif 'message' in data:
                msg = data['message']
                chat_id = msg['chat']['id']
                text_body = msg.get('text', '').lower().strip()
                
                if bot_token:
                    if text_body in ['salom', '/start', 'hi', 'hello']:
                        reply_text = "Salom! Men DDoS himoya botiman 🛡️.\n\nBloklangan IP larni ko'rish va boshqarish uchun /ban buyrug'ini yuboring."
                        send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                        reply_payload = {'chat_id': chat_id, 'text': reply_text}
                        reply_data = urllib.parse.urlencode(reply_payload).encode('utf-8')
                        urllib.request.urlopen(urllib.request.Request(send_url, data=reply_data, method='POST'), timeout=3)
                    
                    elif text_body in ['/ban', 'ban']:
                        active_bans = get_banned_ips()
                        if not active_bans:
                            reply_text = "Hozirda bloklangan (ban olgan) IP manzillar mavjud emas ✅"
                            send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                            reply_payload = {'chat_id': chat_id, 'text': reply_text}
                            reply_data = urllib.parse.urlencode(reply_payload).encode('utf-8')
                            urllib.request.urlopen(urllib.request.Request(send_url, data=reply_data, method='POST'), timeout=3)
                        else:
                            reply_text = "🚫 Hozirda bloklangan IP manzillar ro'yxati:"
                            inline_kb = []
                            for ip, info in active_bans.items():
                                rem_secs = info['rem_secs']
                                code = info['code']
                                mins = rem_secs // 60
                                secs = rem_secs % 60
                                time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
                                inline_kb.append([
                                    {"text": f"{ip} ({code[:8]}...) [{time_str}]", "callback_data": "noop"},
                                    {"text": "🔓 Yechish", "callback_data": f"unban_{ip}"}
                                ])
                            keyboard = {"inline_keyboard": inline_kb}
                            send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                            reply_payload = {
                                'chat_id': chat_id,
                                'text': reply_text,
                                'reply_markup': json.dumps(keyboard)
                            }
                            reply_data = urllib.parse.urlencode(reply_payload).encode('utf-8')
                            urllib.request.urlopen(urllib.request.Request(send_url, data=reply_data, method='POST'), timeout=3)
        except Exception as e:
            print(f"Webhook error: {e}")
    return JsonResponse({'status': 'ok'})
