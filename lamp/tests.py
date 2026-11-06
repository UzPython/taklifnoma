import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Invitation, RSVP


class InvitationPrivacyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='test@gmail.com', email='test@gmail.com', first_name='Test')
        self.other_user = User.objects.create_user(username='other@gmail.com', email='other@gmail.com', first_name='Other')
        
        self.invitation = Invitation.objects.create(
            user=self.user,
            title='Private celebration',
            hosts='Test host',
            event_datetime=timezone.now(),
            venue_name='Private venue',
            venue_address='Private address',
        )

    def test_my_invitations_only_shows_current_user_invitations(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('my_invitations'))
        self.assertContains(response, 'Private celebration')

        other_client = self.client_class()
        other_client.force_login(self.other_user)
        response = other_client.get(reverse('my_invitations'))
        self.assertNotContains(response, 'Private celebration')

    def test_public_pages_require_login(self):
        for path in ('home', 'templates_list'):
            with self.subTest(path=path):
                response = self.client.get(reverse(path))
                # Should redirect to login (302)
                self.assertEqual(response.status_code, 302)

    def test_shared_invitation_link_remains_public(self):
        response = self.client.get(
            reverse('invitation_detail', args=[self.invitation.pk])
        )
        self.assertContains(response, 'Private celebration')

    def test_success_page_is_only_visible_to_owner(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('success_invitation', args=[self.invitation.pk])
        )
        self.assertEqual(response.status_code, 200)

        other_client = self.client_class()
        other_client.force_login(self.other_user)
        response = other_client.get(
            reverse('success_invitation', args=[self.invitation.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_created_invitation_is_assigned_to_current_user(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('create_invitation'), {
            'event_type': 'wedding',
            'template_style': 'paper',
            'title': 'New private invitation',
            'hosts': 'New host',
            'event_datetime': '2030-05-01T10:00',
            'venue_name': 'New venue',
            'venue_address': 'New address',
            'message': 'Join us',
            'reminder_hours': '24',
        })
        self.assertEqual(response.status_code, 302)
        created = Invitation.objects.get(title='New private invitation')
        self.assertEqual(created.user, self.user)

    def test_owner_can_edit_invitation(self):
        edit_url = reverse('edit_invitation', args=[self.invitation.pk])
        self.client.force_login(self.user)

        self.assertEqual(self.client.get(edit_url).status_code, 200)
        response = self.client.post(edit_url, {
            'event_type': 'wedding',
            'template_style': 'paper',
            'title': 'Updated celebration',
            'hosts': 'Updated hosts',
            'event_datetime': '2030-05-01T10:00',
            'venue_name': 'Updated venue',
            'venue_address': 'Updated address',
            'message': 'Updated invitation',
            'reminder_hours': '24',
        })

        self.assertRedirects(
            response,
            reverse('invitation_detail', args=[self.invitation.pk]),
        )
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.title, 'Updated celebration')
        self.assertEqual(self.invitation.venue_name, 'Updated venue')

    def test_only_invitation_owner_can_edit(self):
        edit_url = reverse('edit_invitation', args=[self.invitation.pk])
        self.client.force_login(self.other_user)

        self.assertEqual(self.client.get(edit_url).status_code, 404)
        self.assertEqual(self.client.post(edit_url, {}).status_code, 404)
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.title, 'Private celebration')

    def test_my_invitations_shows_rsvp_counts(self):
        RSVP.objects.create(
            invitation=self.invitation,
            guest_name='Guest One',
            attendance='yes',
        )
        RSVP.objects.create(
            invitation=self.invitation,
            guest_name='Guest Two',
            attendance='maybe',
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse('my_invitations'))

        self.assertEqual(response.status_code, 200)
        invitation = response.context['invitations'][0]
        self.assertEqual(invitation.rsvp_total_count, 2)
        self.assertEqual(invitation.rsvp_yes_count, 1)
        self.assertEqual(invitation.rsvp_maybe_count, 1)
        self.assertEqual(invitation.rsvp_no_count, 0)
        self.assertContains(response, 'Mehmonlar javobi')

    def test_rsvp_export_is_only_available_to_invitation_owner(self):
        RSVP.objects.create(
            invitation=self.invitation,
            guest_name='Guest One',
            attendance='yes',
            wish_message='Bayramingiz muborak!',
        )
        export_url = reverse('export_invitation_rsvps', args=[self.invitation.pk])
        self.client.force_login(self.user)

        response = self.client.get(export_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('private, no-store', response['Cache-Control'])
        self.assertIn('Guest One', response.content.decode('utf-8-sig'))
        self.assertIn('Bayramingiz muborak!', response.content.decode('utf-8-sig'))

        other_client = self.client_class()
        other_client.force_login(self.other_user)
        self.assertEqual(other_client.get(export_url).status_code, 404)


class FileUploadValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testfile@gmail.com', email='testfile@gmail.com')

    def test_invalid_file_upload_rejected(self):
        self.client.force_login(self.user)
        malicious_file = SimpleUploadedFile("shell.php", b"<?php system($_GET['cmd']); ?>", content_type="application/x-php")
        response = self.client.post(reverse('create_invitation'), {
            'event_type': 'wedding',
            'template_style': 'paper',
            'title': 'Hacker test',
            'hosts': 'Hacker',
            'event_datetime': '2030-05-01T10:00',
            'venue_name': 'Venue',
            'venue_address': 'Address',
            'message': 'Test',
            'reminder_hours': '24',
            'cover_image': malicious_file,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            "Faqat rasm formatidagi" in response.content.decode('utf-8') or
            "Upload a valid image" in response.content.decode('utf-8')
        )

    def test_invalid_audio_file_rejected(self):
        self.client.force_login(self.user)
        malicious_file = SimpleUploadedFile("script.sh", b"rm -rf /", content_type="application/x-sh")
        response = self.client.post(reverse('create_invitation'), {
            'event_type': 'wedding',
            'template_style': 'paper',
            'title': 'Hacker test',
            'hosts': 'Hacker',
            'event_datetime': '2030-05-01T10:00',
            'venue_name': 'Venue',
            'venue_address': 'Address',
            'message': 'Test',
            'reminder_hours': '24',
            'audio_file': malicious_file,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Faqat MP3 yoki M4A formatidagi audio fayllar yuklanishi mumkin")

    def test_m4a_audio_file_accepted(self):
        self.client.force_login(self.user)
        m4a_file = SimpleUploadedFile("audio.m4a", b"fake m4a audio content", content_type="audio/mp4")
        response = self.client.post(reverse('create_invitation'), {
            'event_type': 'wedding',
            'template_style': 'paper',
            'title': 'M4A Test',
            'hosts': 'Hacker',
            'event_datetime': '2030-05-01T10:00',
            'venue_name': 'Venue',
            'venue_address': 'Address',
            'message': 'Test',
            'reminder_hours': '24',
            'audio_file': m4a_file,
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Invitation.objects.filter(title='M4A Test').exists())

    def test_invalid_video_file_rejected(self):
        self.client.force_login(self.user)
        malicious_file = SimpleUploadedFile("script.exe", b"MZ...", content_type="application/x-msdownload")
        response = self.client.post(reverse('create_invitation'), {
            'event_type': 'wedding',
            'template_style': 'paper',
            'title': 'Hacker test',
            'hosts': 'Hacker',
            'event_datetime': '2030-05-01T10:00',
            'venue_name': 'Venue',
            'venue_address': 'Address',
            'message': 'Test',
            'reminder_hours': '24',
            'video_file': malicious_file,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Faqat MP4 formatidagi video fayllar yuklanishi mumkin")


class MediaServingTests(TestCase):
    @override_settings(DEBUG=False)
    def test_media_url_serves_audio_when_debug_is_false(self):
        relative_path = f"audio/test-{uuid.uuid4()}.mp3"
        audio_path = settings.MEDIA_ROOT / relative_path
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_content = b"test audio data"

        try:
            audio_path.write_bytes(audio_content)
            response = self.client.get(f"/media/{relative_path}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), audio_content)
            self.assertEqual(response["Content-Type"], "audio/mpeg")
        finally:
            audio_path.unlink(missing_ok=True)
