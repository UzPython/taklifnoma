import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Invitation


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
        self.assertContains(response, "Faqat MP3 formatidagi audio fayllar yuklanishi mumkin")

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

