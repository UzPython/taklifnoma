import json
import secrets
import sys
import time
import urllib.request
import urllib.parse
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponseForbidden

def get_blocked_html(msg, code):
    return f"""<!DOCTYPE html>
<html lang="uz">
<head>
    <meta charset="UTF-8">
    <title>Kirish cheklandi</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; color: #f8fafc; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
        .card {{ background: #1e293b; padding: 40px; border-radius: 16px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.3); text-align: center; max-width: 480px; border: 1px solid #334155; }}
        .icon {{ font-size: 48px; margin-bottom: 20px; }}
        h1 {{ font-size: 24px; margin-bottom: 12px; color: #f87171; }}
        p {{ color: #94a3b8; font-size: 15px; line-height: 1.6; margin-bottom: 20px; }}
        .code-box {{ background: #0f172a; border: 1px dashed #475569; padding: 12px; border-radius: 8px; font-family: monospace; font-size: 14px; color: #38bdf8; word-break: break-all; margin-bottom: 24px; }}
        .btn {{ display: inline-block; background-color: #3b82f6; color: #ffffff; padding: 10px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; transition: background 0.2s; }}
        .btn:hover {{ background-color: #2563eb; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">🛡️</div>
        <h1>Xavfsizlik tizimi</h1>
        <p>{msg}</p>
        <div class="code-box">Xavfsizlik kodi: {code}</div>
        <a href="https://t.me/UzPython212" target="_blank" class="btn">Shikoyat qilish</a>
    </div>
</body>
</html>"""

def ban_ip(ip, duration):
    cache.set(f'banned_ip_{ip}', True, duration)
    
    code = cache.get(f'ban_code_{ip}')
    if not code:
        code = secrets.token_hex(10) # 20 chars
        cache.set(f'ban_code_{ip}', code, duration)
        cache.set(f'ip_by_code_{code}', ip, duration)

    if duration >= 86400:
        h = duration // 3600
        msg = f"Sizning IP manzilingiz ma'muriyat tomonidan {h} soatga bloklandi."
    elif duration >= 3600:
        h = duration // 3600
        msg = f"Sizning IP manzilingiz ma'muriyat tomonidan {h} soatga bloklandi."
    elif duration >= 60:
        m = duration // 60
        msg = f"Sizning IP manzilingiz {m} daqiqaga bloklandi."
    else:
        msg = f"Sizning IP manzilingiz {duration} soniyaga bloklandi."

    cache.set(f'ban_msg_{ip}', msg, duration)
    banned_dict = cache.get('banned_ips_dict', {})
    banned_dict[ip] = {
        'expiry': time.time() + duration,
        'code': code
    }
    cache.set('banned_ips_dict', banned_dict, 86400)
    return code

def unban_ip(ip):
    code = cache.get(f'ban_code_{ip}')
    if code:
        cache.delete(f'ip_by_code_{code}')
    cache.delete(f'banned_ip_{ip}')
    cache.delete(f'ban_msg_{ip}')
    cache.delete(f'ban_code_{ip}')
    cache.delete(f'alert_sent_{ip}')
    
    banned_dict = cache.get('banned_ips_dict', {})
    banned_dict.pop(ip, None)
    cache.set('banned_ips_dict', banned_dict, 86400)

def get_banned_ips():
    banned_dict = cache.get('banned_ips_dict', {})
    now = time.time()
    active = {}
    for ip, data in banned_dict.items():
        if isinstance(data, dict):
            expiry = data.get('expiry', 0)
            code = data.get('code', '')
        else:
            expiry = data
            code = cache.get(f'ban_code_{ip}', 'N/A')
            
        if expiry > now and cache.get(f'banned_ip_{ip}'):
            active[ip] = {
                'rem_secs': int(expiry - now),
                'code': code
            }
    cache.set('banned_ips_dict', active, 86400)
    return active

class AntiDDoSIPBanMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if 'test' in sys.argv:
            return self.get_response(request)

        ip = self.get_client_ip(request)
        if ip:
            ban_key = f'banned_ip_{ip}'
            if cache.get(ban_key):
                msg = cache.get(f'ban_msg_{ip}', "Sizning IP manzilingiz vaqtinchalik bloklandi.")
                code = cache.get(f'ban_code_{ip}', 'N/A')
                return HttpResponseForbidden(get_blocked_html(msg, code))

            now = time.time()
            rate_key = f'req_timestamps_{ip}'
            timestamps = cache.get(rate_key, [])
            
            # Keep timestamps within the last 10 seconds
            timestamps = [t for t in timestamps if now - t < 10.0]
            
            if len(timestamps) >= 5:
                code = ban_ip(ip, 60)
                cache.delete(rate_key)
                
                # Send Telegram alert
                alert_key = f'alert_sent_{ip}'
                if not cache.get(alert_key):
                    cache.set(alert_key, True, 60)
                    self.send_telegram_alert(ip, code)

                msg = cache.get(f'ban_msg_{ip}', "Juda ko'p so'rov yuborildi. IP manzilingiz bloklandi.")
                return HttpResponseForbidden(get_blocked_html(msg, code))
            
            timestamps.append(now)
            cache.set(rate_key, timestamps, 5)

        response = self.get_response(request)
        return response

    def send_telegram_alert(self, ip, code):
        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', '@uzpython212')
        if not bot_token:
            return
        
        message = f"🚨 DIQQAT! DDoS / Hujum aniqlandi!\n\nIP manzil: {ip}\n🔑 Kod: <code>{code}</code>\nHolat: 1 minutga bloklandi (>5 so'rov/sekund).\n\nQancha muddatga ban berishni tanlang:"
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "⏱ 10 daqiqa", "callback_data": f"ban_600_{ip}"},
                    {"text": "⏱ 1 soat", "callback_data": f"ban_3600_{ip}"},
                    {"text": "⏱ 24 soat", "callback_data": f"ban_86400_{ip}"}
                ],
                [
                    {"text": "🔓 Bandan yechish", "callback_data": f"unban_{ip}"}
                ]
            ]
        }
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML',
            'reply_markup': json.dumps(keyboard),
        }
        try:
            data = urllib.parse.urlencode(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, method='POST')
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            print(f"Telegram alert error: {e}")

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip or '127.0.0.1'
