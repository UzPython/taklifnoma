import os
import threading
import time
import json
import urllib.error
import urllib.parse
import urllib.request
from django.apps import AppConfig
from django.conf import settings
from django.core.cache import cache
from django.db.backends.signals import connection_created
from django.dispatch import receiver
from lamp.middleware import ban_ip, unban_ip, get_banned_ips


def configure_telegram_webhook(bot_token, webhook_url):
    api_url = f"https://api.telegram.org/bot{bot_token}"
    info_request = urllib.request.Request(f"{api_url}/getWebhookInfo")
    with urllib.request.urlopen(info_request, timeout=5) as response:
        info = json.loads(response.read().decode('utf-8'))

    if not info.get('ok'):
        raise RuntimeError("Telegram did not return webhook information.")

    current_url = info.get('result', {}).get('url', '')
    if current_url == webhook_url:
        return False

    payload = urllib.parse.urlencode({'url': webhook_url}).encode('utf-8')
    set_request = urllib.request.Request(
        f"{api_url}/setWebhook",
        data=payload,
        method='POST',
    )
    with urllib.request.urlopen(set_request, timeout=5) as response:
        result = json.loads(response.read().decode('utf-8'))

    if not result.get('ok'):
        raise RuntimeError("Telegram rejected the webhook configuration.")
    return True


@receiver(connection_created)
def configure_sqlite_connection(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        cursor = connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('PRAGMA synchronous=NORMAL;')
        cursor.execute('PRAGMA busy_timeout=5000;')

class LampConfig(AppConfig):
    name = "lamp"

    def ready(self):
        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        if bot_token:
            def setup_webhook():
                time.sleep(3)
                try:
                    railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN') or os.environ.get('RAILWAY_STATIC_URL')
                    custom_webhook = os.environ.get('WEBHOOK_URL')
                    if custom_webhook:
                        webhook_url = custom_webhook
                    elif railway_domain:
                        if not railway_domain.startswith('http'):
                            railway_domain = f"https://{railway_domain}"
                        webhook_url = f"{railway_domain.rstrip('/')}/telegram/webhook/"
                    else:
                        webhook_url = "https://taklifnoma-production-94ce.up.railway.app/telegram/webhook/"

                    configure_telegram_webhook(bot_token, webhook_url)
                except urllib.error.HTTPError as e:
                    print(f"Telegram webhook configuration failed (HTTP {e.code}).")
                except RuntimeError as e:
                    print(f"Telegram webhook configuration failed: {e}")
                except Exception as e:
                    print(f"Telegram webhook configuration failed: {type(e).__name__}.")

            threading.Thread(target=setup_webhook, daemon=True).start()

def start_telegram_polling():
    time.sleep(3)
    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not bot_token:
        return
    
    # Delete webhook so getUpdates polling works reliably
    try:
        url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
        urllib.request.urlopen(urllib.request.Request(url, method='POST'), timeout=5)
    except Exception:
        pass

    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset={offset}&timeout=10"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))
                if data.get('ok'):
                    for update in data.get('result', []):
                        offset = update['update_id'] + 1
                        
                        if 'callback_query' in update:
                            cb = update['callback_query']
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
                            
                            answer_url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
                            req_data = urllib.parse.urlencode({
                                'callback_query_id': callback_query_id,
                                'text': text,
                                'show_alert': True
                            }).encode('utf-8')
                            urllib.request.urlopen(urllib.request.Request(answer_url, data=req_data, method='POST'), timeout=3)
                        
                        elif 'message' in update:
                            msg = update['message']
                            chat_id = msg['chat']['id']
                            text_body = msg.get('text', '').lower().strip()
                            
                            if text_body in ['salom', '/start', 'hi', 'hello']:
                                reply_text = "Salom! Men DDoS himoya botiman 🛡️.\n\nBloklangan IP larni ko'rish va boshqarish uchun /ban buyrug'ini yuboring."
                                send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                                reply_payload = {
                                    'chat_id': chat_id,
                                    'text': reply_text
                                }
                                reply_data = urllib.parse.urlencode(reply_payload).encode('utf-8')
                                urllib.request.urlopen(urllib.request.Request(send_url, data=reply_data, method='POST'), timeout=3)
                            
                            elif text_body in ['/ban', 'ban']:
                                active_bans = get_banned_ips()
                                if not active_bans:
                                    reply_text = "Hozirda bloklangan (ban olgan) IP manzillar mavjud emas ✅"
                                    send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                                    reply_payload = {
                                        'chat_id': chat_id,
                                        'text': reply_text
                                    }
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
            time.sleep(5)
        time.sleep(0.5)
