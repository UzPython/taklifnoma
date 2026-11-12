import csv
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
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils import timezone
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


def _get_invitation_share_url(request, invitation):
    return request.build_absolute_uri(reverse('invitation_share', args=[invitation.share_token]))


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
    query = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', 'recent')

    invitations = Invitation.objects.filter(user=request.user).annotate(
        rsvp_total_count=Count('rsvps', distinct=True),
        rsvp_yes_count=Count('rsvps', filter=Q(rsvps__attendance='yes'), distinct=True),
        rsvp_maybe_count=Count('rsvps', filter=Q(rsvps__attendance='maybe'), distinct=True),
        rsvp_no_count=Count('rsvps', filter=Q(rsvps__attendance='no'), distinct=True),
    )

    if query:
        invitations = invitations.filter(
            Q(title__icontains=query)
            | Q(hosts__icontains=query)
            | Q(venue_name__icontains=query)
            | Q(guest_name__icontains=query)
        )

    order_by_map = {
        'recent': '-created_at',
        'soonest': 'event_datetime',
        'likes': '-likes_count',
        'rsvps': '-rsvp_total_count',
    }
    invitations = invitations.order_by(order_by_map.get(sort, '-created_at'))

    total_invitations = invitations.count()
    total_rsvps = sum(invitation.rsvp_total_count for invitation in invitations)
    total_yes = sum(invitation.rsvp_yes_count for invitation in invitations)
    total_maybe = sum(invitation.rsvp_maybe_count for invitation in invitations)
    upcoming_count = invitations.filter(event_datetime__gte=timezone.now()).count()

    return render(request, 'lamp/my_invitations.html', {
        'invitations': invitations,
        'query': query,
        'sort': sort,
        'stats': {
            'total_invitations': total_invitations,
            'total_rsvps': total_rsvps,
            'total_yes': total_yes,
            'total_maybe': total_maybe,
            'upcoming_count': upcoming_count,
        },
    })


@login_required(login_url='login')
def export_all_invitations_view(request):
    invitations = Invitation.objects.filter(user=request.user).annotate(
        rsvp_total_count=Count('rsvps', distinct=True),
        rsvp_yes_count=Count('rsvps', filter=Q(rsvps__attendance='yes'), distinct=True),
        rsvp_maybe_count=Count('rsvps', filter=Q(rsvps__attendance='maybe'), distinct=True),
        rsvp_no_count=Count('rsvps', filter=Q(rsvps__attendance='no'), distinct=True),
    ).order_by('-created_at')

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="all-invitations-summary.csv"'
    response['Cache-Control'] = 'private, no-store'
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow(['Sarlavha', 'Xostlar', 'Tadbir turi', 'Vaqti', 'Manzil', 'Jami javoblar', 'Keladi', 'Balki', 'Kelolmaydi', 'Yoqtirishlar'])
    for invitation in invitations.iterator():
        writer.writerow([
            invitation.title,
            invitation.hosts,
            invitation.get_event_type_display(),
            timezone.localtime(invitation.event_datetime).strftime('%Y-%m-%d %H:%M') if invitation.event_datetime else '',
            invitation.venue_name,
            invitation.rsvp_total_count,
            invitation.rsvp_yes_count,
            invitation.rsvp_maybe_count,
            invitation.rsvp_no_count,
            invitation.likes_count,
        ])
    return response


@login_required(login_url='login')
def export_invitation_rsvps_view(request, pk):
    invitation = get_object_or_404(Invitation, pk=pk, user=request.user)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="invitation-{invitation.pk}-rsvps.csv"'
    response['Cache-Control'] = 'private, no-store'
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow(['Mehmon ismi', 'Javob', 'Tabrik va tilak', 'Yuborilgan vaqt'])
    for rsvp in invitation.rsvps.order_by('created_at').iterator():
        writer.writerow([
            rsvp.guest_name,
            rsvp.get_attendance_display(),
            rsvp.wish_message or '',
            timezone.localtime(rsvp.created_at).strftime('%Y-%m-%d %H:%M'),
        ])
    return response


@login_required(login_url='login')
@transaction.atomic
def create_view(request):
    if request.method == 'POST':
        form = InvitationForm(request.POST, request.FILES)
        if form.is_valid():
            invitation = form.save(commit=False)
            invitation.user = request.user
            invitation.owner_token = _get_owner_token(request)
            if not invitation.event_datetime:
                invitation.event_datetime = timezone.now() + timezone.timedelta(days=10)
            if not invitation.venue_address:
                invitation.venue_address = invitation.venue_name
            if not invitation.title:
                invitation.title = f"{invitation.hosts} — To'y taklifnomasi"
            invitation.save()
            return redirect('success_invitation', pk=invitation.pk)
    else:
        form = InvitationForm()
    return render(request, 'lamp/create.html', {'form': form})


@login_required(login_url='login')
@transaction.atomic
def edit_invitation_view(request, pk):
    invitation = get_object_or_404(Invitation, pk=pk, user=request.user)
    if request.method == 'POST':
        form = InvitationForm(request.POST, request.FILES, instance=invitation)
        if form.is_valid():
            inv = form.save(commit=False)
            if not inv.event_datetime:
                inv.event_datetime = timezone.now() + timezone.timedelta(days=10)
            if not inv.venue_address:
                inv.venue_address = inv.venue_name
            if not inv.title:
                inv.title = f"{inv.hosts} — To'y taklifnomasi"
            inv.save()
            return redirect('invitation_detail', pk=inv.pk)
    else:
        form = InvitationForm(instance=invitation)
    return render(request, 'lamp/create.html', {
        'form': form,
        'edit_mode': True,
    })


@login_required(login_url='login')
def success_view(request, pk):
    invitation = get_object_or_404(
        Invitation,
        pk=pk,
        user=request.user,
    )
    invitation_url = _get_invitation_share_url(request, invitation)
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
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'liked': True,
                'likes_count': invitation.likes_count,
            })
    return redirect('invitation_detail', pk=invitation.pk)

def public_invitation_view(request, token):
    invitation = get_object_or_404(Invitation, share_token=token)
    return invitation_detail_view(request, invitation.pk)


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
@transaction.atomic
def duplicate_invitation_view(request, pk):
    invitation = get_object_or_404(Invitation, pk=pk, user=request.user)
    if request.method == 'POST':
        duplicate = Invitation.objects.get(pk=invitation.pk)
        duplicate.pk = None
        duplicate.id = uuid.uuid4()
        duplicate.owner_token = uuid.uuid4()
        duplicate.share_token = uuid.uuid4()
        duplicate.user = request.user
        duplicate.likes_count = 0
        duplicate.title = f"{invitation.title} (Nusxa)"
        duplicate.created_at = timezone.now()
        duplicate.save()
    return redirect('my_invitations')


@login_required(login_url='login')
@transaction.atomic
def refresh_invitation_link_view(request, pk):
    invitation = get_object_or_404(Invitation, pk=pk, user=request.user)
    if request.method == 'POST':
        invitation.share_token = uuid.uuid4()
        invitation.save(update_fields=['share_token'])
        share_url = _get_invitation_share_url(request, invitation)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'share_url': share_url})
    return redirect('my_invitations')


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


@login_required(login_url='login')
@transaction.atomic
def ai_generate_invitation_view(request):
    if request.method == 'POST':
        try:
            data_body = json.loads(request.body)
            prompt = data_body.get('prompt', '')
            if not prompt:
                return JsonResponse({'success': False, 'error': 'Buyruq kiritilmadi.'}, status=400)

            default_key = "".join(["AQ.Ab8RN6LInTy", "ZQnmkDKHv67XqEB", "xURdkc211JqkOPf", "W6NPA8VMg"])
            api_key = getattr(settings, 'GEMINI_API_KEY', default_key)
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={api_key}"
            
            system_instruction = (
                "Siz Taklifnoma.uz saytining aqlli AI yordamchisiz. Foydalanuvchi matnini tahlil qiling va quyidagi 2 ta rejimdan birini tanlab faqat valid JSON formatida javob bering (hech qanday markdown belgilari, qo'shimcha so'zlarsiz):\n\n"
                "1. Agar foydalanuvchi yangi taklifnoma yaratishni so'rasa yoki tadbir haqida ma'lumot (ism, sana, vaqt, joy) bersa (masalan: 'Anvar va Dilfuzaning to'yi...'):\n"
                "{\n"
                '  "intent": "create",\n'
                '  "event_type": "wedding" (yoki engagement, sunnat, jubiley, other),\n'
                '  "template_style": "paper" (yoki royal, rose, video),\n'
                '  "title": "Taklifnoma sarlavhasi",\n'
                '  "hosts": "Egasining ismlari",\n'
                '  "event_datetime": "2026-06-15T17:00:00",\n'
                '  "venue_name": "Restoran nomi",\n'
                '  "venue_address": "To\'liq manzil",\n'
                '  "message": "Tabrik matni"\n'
                "}\n\n"
                "2. Agar foydalanuvchi oddiy savol bersa, maslahat so'rasa yoki salomlashsa:\n"
                "{\n"
                '  "intent": "chat",\n'
                '  "answer": "O\'zbek tilida berilgan batafsil va muloyim javob yoki maslahat"\n'
                "}"
            )

            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": f"{system_instruction}\n\nFoydalanuvchi buyrug'i: {prompt}"}
                        ]
                    }
                ]
            }

            req_data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=req_data, headers={'Content-Type': 'application/json'}, method='POST')
            
            with urllib.request.urlopen(req, timeout=15) as response:
                res_json = json.loads(response.read().decode('utf-8'))
                
            candidates = res_json.get('candidates', [])
            if not candidates:
                return JsonResponse({'success': False, 'error': 'AI javob qaytarmadi.'}, status=400)
                
            content_text = candidates[0].get('content', {}).get('parts', [{}])[0].get('text', '{}')
            content_text = content_text.strip()
            if content_text.startswith('```json'):
                content_text = content_text[7:]
            if content_text.endswith('```'):
                content_text = content_text[:-3]
            content_text = content_text.strip()

            parsed = json.loads(content_text)
            intent = parsed.get('intent', 'chat')

            if intent == 'create':
                from datetime import datetime
                dt_str = parsed.get('event_datetime', '2026-06-15T17:00:00')
                try:
                    event_dt = datetime.fromisoformat(dt_str)
                    if timezone.is_naive(event_dt):
                        event_dt = timezone.make_aware(event_dt)
                except Exception:
                    event_dt = timezone.now() + timezone.timedelta(days=10)

                invitation = Invitation.objects.create(
                    user=request.user,
                    owner_token=_get_owner_token(request),
                    event_type=parsed.get('event_type', 'wedding'),
                    template_style=parsed.get('template_style', 'paper'),
                    title=parsed.get('title', "To'y taklifnomasi"),
                    hosts=parsed.get('hosts', "Aziz & Madina"),
                    event_datetime=event_dt,
                    venue_name=parsed.get('venue_name', "Tantanalar saroyi"),
                    venue_address=parsed.get('venue_address', "Toshkent shahri"),
                    message=parsed.get('message', "Sizni quvonchli kunimizda kutamiz!")
                )

                invite_url = request.build_absolute_uri(f"/invitation/{invitation.pk}/")
                return JsonResponse({
                    'success': True,
                    'intent': 'create',
                    'invitation_url': invite_url
                })
            else:
                return JsonResponse({
                    'success': True,
                    'intent': 'chat',
                    'answer': parsed.get('answer', 'Javob topilmadi.')
                })

        except Exception as e:
            print("AI Error:", e)
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)
