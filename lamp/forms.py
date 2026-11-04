import os
from django import forms
from django.core.exceptions import ValidationError
from PIL import Image
from .models import Invitation, RSVP

class InvitationForm(forms.ModelForm):
    class Meta:
        model = Invitation
        fields = [
            'event_type',
            'template_style',
            'title',
            'hosts',
            'guest_name',
            'event_datetime',
            'venue_name',
            'venue_address',
            'message',
            'cover_image',
            'audio_file',
            'video_file',
            'reminder_hours',
        ]
        widgets = {
            'event_type': forms.Select(attrs={'class': 'form-select'}),
            'template_style': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Masalan: Anvar va Dilfuza nikoh to'yi"}),
            'hosts': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Masalan: Alisher & Zaynab"}),
            'guest_name': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': "Bo'sh qoldirsangiz hammaga umumiy bo'ladi. Har bir qatorga bitta mehmon ismini yozing (xohlagancha odam)..."}),
            'event_datetime': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'venue_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Masalan: 'Oqsaroy' tantanalar saroyi"}),
            'venue_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': "Toshkent shahri, Yunusobod tumani..."}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': "Taklifnoma matnini kiriting..."}),
            'cover_image': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/jpeg,image/png,image/webp,image/gif'}),
            'audio_file': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.mp3,audio/mpeg'}),
            'video_file': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.mp4,video/mp4'}),
            'reminder_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '720', 'placeholder': 'Masalan: 24 (soat)'}),
        }

    def clean_cover_image(self):
        image = self.cleaned_data.get('cover_image')
        if image:
            ext = os.path.splitext(image.name)[1].lower()
            valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
            if ext not in valid_extensions:
                raise ValidationError("Faqat rasm formatidagi fayllar yuklanishi mumkin (.jpg, .jpeg, .png, .webp, .gif).")
            try:
                img = Image.open(image)
                img.verify()
            except Exception:
                raise ValidationError("Yuklangan fayl haqiqiy rasm emas.")
        return image

    def clean_audio_file(self):
        audio = self.cleaned_data.get('audio_file')
        if audio:
            ext = os.path.splitext(audio.name)[1].lower()
            valid_extensions = ['.mp3']
            if ext not in valid_extensions:
                raise ValidationError("Faqat MP3 formatidagi audio fayllar yuklanishi mumkin (.mp3).")
        return audio

    def clean_video_file(self):
        video = self.cleaned_data.get('video_file')
        if video:
            ext = os.path.splitext(video.name)[1].lower()
            valid_extensions = ['.mp4']
            if ext not in valid_extensions:
                raise ValidationError("Faqat MP4 formatidagi video fayllar yuklanishi mumkin (.mp4).")
        return video


class RSVPForm(forms.ModelForm):
    class Meta:
        model = RSVP
        fields = ['guest_name', 'attendance', 'wish_message']
        widgets = {
            'guest_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ism va familiyangiz'}),
            'attendance': forms.Select(attrs={'class': 'form-select'}),
            'wish_message': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Tabrik va tilaklaringizni yozib qoldiring...'}),
        }

