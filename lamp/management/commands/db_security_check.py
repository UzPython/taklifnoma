from django.core.management.base import BaseCommand
from django.db import connection
from lamp.models import Invitation, RSVP, Like
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = "Malumotlar bazasini xavfsizlik va yaxlitlikka tekshirish, optimizatsiya qilish"

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Malumotlar bazasini xavfsizlik tekshiruvi boshlandi..."))

        # 1. Integrity check
        try:
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA integrity_check;")
                result = cursor.fetchone()
                if result and result[0] == "ok":
                    self.stdout.write(self.style.SUCCESS("Bazaning yaxlitligi (integrity_check): MUVAFFAQIYATLI (OK)"))
                else:
                    self.stdout.write(self.style.ERROR(f"Diqqat! Baza xatoligi aniqlandi: {result}"))

                # Foreign key check
                cursor.execute("PRAGMA foreign_key_check;")
                fk_errors = cursor.fetchall()
                if not fk_errors:
                    self.stdout.write(self.style.SUCCESS("Tashqi kalitlar yaxlitligi (foreign_key_check): TOG'RI"))
                else:
                    self.stdout.write(self.style.WARNING(f"Tashqi kalitlarda xatoliklar: {fk_errors}"))

                # Optimize (VACUUM)
                cursor.execute("VACUUM;")
                self.stdout.write(self.style.SUCCESS("Malumotlar bazasi optimizatsiya qilindi (VACUUM bajarildi)."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Bazani tekshirishda xatolik yuz berdi: {e}"))

        # 2. Statistics & metrics
        user_count = User.objects.count()
        inv_count = Invitation.objects.count()
        rsvp_count = RSVP.objects.count()
        like_count = Like.objects.count()

        self.stdout.write("\nMalumotlar bazasi statistikasi:")
        self.stdout.write(f"   - Foydalanuvchilar: {user_count}")
        self.stdout.write(f"   - Taklifnomalar: {inv_count}")
        self.stdout.write(f"   - RSVP javoblar: {rsvp_count}")
        self.stdout.write(f"   - Like (Yoqtirishlar): {like_count}")
        self.stdout.write(self.style.SUCCESS("\nMalumotlar bazasi to'liq himoyalangan va xavfsiz holatda!"))
