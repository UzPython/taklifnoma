import uuid
from django.db import models

class Invitation(models.Model):
    EVENT_TYPES = [
        ('wedding', "Nikoh to'yi"),
        ('engagement', "Fotiha to'yi"),
        ('sunnat', "Sunnat to'yi"),
        ('jubiley', "Jubiley / Tug'ilgan kun"),
        ('other', "Boshqa tadbir"),
    ]

    TEMPLATE_CHOICES = [
        ('paper', "Klassik Oqshom (Oq va Oltin)"),
        ('royal', "Qirollik Kechasi (To'q qora va Oltin)"),
        ('rose', "Nozik Atirgul (Pushti va Krem)"),
        ('video', "Video taklifnoma"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, null=True, blank=True, related_name='invitations')
    owner_token = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES, default='wedding', verbose_name="Tadbir turi")
    template_style = models.CharField(max_length=20, choices=TEMPLATE_CHOICES, default='paper', verbose_name="Taklifnoma dizayni")
    title = models.CharField(max_length=200, default="To'y taklifnomasi", verbose_name="Taklifnoma sarlavhasi")
    hosts = models.CharField(max_length=250, verbose_name="Egasining ismlari (masalan: Anvar & Gulnora)")
    guest_name = models.TextField(blank=True, null=True, verbose_name="Mehmonlar ismi (ixtiyoriy)")
    event_datetime = models.DateTimeField(verbose_name="Tadbir vaqti va sanasi")
    venue_name = models.CharField(max_length=250, verbose_name="Restoran / Maskon nomi")
    venue_address = models.TextField(verbose_name="To'liq manzil")
    message = models.TextField(verbose_name="Taklifnoma matni / Tabrik", default="Sizni hayotimizdagi eng quvonchli kunda qadrli mehmonimiz bo'lishga taklif qilamiz!")
    cover_image = models.ImageField(upload_to='covers/', blank=True, null=True, verbose_name="Juftlik yoki tadbir rasmi (ixtiyoriy)")
    audio_file = models.FileField(upload_to='audio/', blank=True, null=True, verbose_name="Fon musiqasi (MP3 fayl yuklash)")
    video_file = models.FileField(upload_to='videos/', blank=True, null=True, verbose_name="Video fayl yuklash (MP4)")
    
    reminder_hours = models.PositiveIntegerField(default=24, verbose_name="Necha soat oldin eslatish (soatda)")
    likes_count = models.PositiveIntegerField(default=0, verbose_name="Yoqtirishlar soni")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def yes_rsvp_count(self):
        return self.rsvps.filter(attendance='yes').count()

    @property
    def maybe_rsvp_count(self):
        return self.rsvps.filter(attendance='maybe').count()

    @property
    def no_rsvp_count(self):
        return self.rsvps.filter(attendance='no').count()

    def __str__(self):
        return f"{self.title} - {self.hosts}"


class RSVP(models.Model):
    ATTENDANCE_CHOICES = [
        ('yes', "Albatta kelaman 🎉"),
        ('no', "Afsuski kelolmayman 😔"),
        ('maybe', "Harakat qilaman 🤔"),
    ]
    invitation = models.ForeignKey(Invitation, on_delete=models.CASCADE, related_name='rsvps')
    guest_name = models.CharField(max_length=200, verbose_name="Ismingiz")
    attendance = models.CharField(max_length=20, choices=ATTENDANCE_CHOICES, default='yes', verbose_name="Ishtirok etishingiz")
    wish_message = models.TextField(blank=True, null=True, verbose_name="Tabrik va tilaklaringiz")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.guest_name} - {self.get_attendance_display()}"


class Like(models.Model):
    invitation = models.ForeignKey(Invitation, on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, null=True, blank=True)
    session_key = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Like on {self.invitation} by {self.user or self.session_key}"
