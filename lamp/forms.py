import os
from django import forms
from django.core.exceptions import ValidationError
from PIL import Image
from .models import Invitation, RSVP

class InvitationForm(forms.ModelForm):
    class Meta:
        model = Invitation
        fields = [
            'hosts',
            'event_datetime',
            'venue_name',
            'venue_address',
            'venue_map_url',
        ]
        widgets = {
            'hosts': forms.TextInput(attrs={'class': 'form-control form-control-lg', 'placeholder': 'Masalan: Anvar va Dilnoza'}),
            'event_datetime': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control form-control-lg'}, format='%Y-%m-%dT%H:%M'),
            'venue_name': forms.TextInput(attrs={'class': 'form-control form-control-lg', 'placeholder': "Masalan: 'Oqsaroy' tantanalar saroyi"}),
            'venue_address': forms.HiddenInput(),
            'venue_map_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://maps.app.goo.gl/...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ['event_datetime', 'venue_address', 'venue_map_url']:
            if field_name in self.fields:
                self.fields[field_name].required = False

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
            valid_extensions = ['.mp3', '.m4a']
            if ext not in valid_extensions:
                raise ValidationError("Faqat MP3 yoki M4A formatidagi audio fayllar yuklanishi mumkin (.mp3, .m4a).")
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
