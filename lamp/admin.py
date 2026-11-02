from django.contrib import admin
from .models import Invitation, RSVP

@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ('title', 'hosts', 'event_type', 'event_datetime', 'venue_name', 'likes_count', 'created_at')
    list_filter = ('event_type', 'template_style', 'created_at')
    search_fields = ('title', 'hosts', 'venue_name', 'venue_address')

@admin.register(RSVP)
class RSVPAdmin(admin.ModelAdmin):
    list_display = ('guest_name', 'invitation', 'attendance', 'created_at')
    list_filter = ('attendance', 'created_at')
    search_fields = ('guest_name', 'invitation__title')
