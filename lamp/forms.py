from django import forms
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
            'cover_image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'audio_file': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.mp3,audio/*'}),
            'video_file': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.mp4,video/*'}),
            'reminder_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '720', 'placeholder': 'Masalan: 24 (soat)'}),
        }


class RSVPForm(forms.ModelForm):
    class Meta:
        model = RSVP
        fields = ['guest_name', 'attendance', 'wish_message']
        widgets = {
            'guest_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ism va familiyangiz'}),
            'attendance': forms.Select(attrs={'class': 'form-select'}),
            'wish_message': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Tabrik va tilaklaringizni yozib qoldiring...'}),
        }

