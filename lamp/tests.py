import json
import uuid
import urllib.parse
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .apps import configure_telegram_webhook
from .models import Invitation, RSVP


class TelegramWebhookConfigurationTests(SimpleTestCase):
    def make_response(self, payload):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(payload).encode('utf-8')
        return response

    @patch('lamp.apps.urllib.request.urlopen')
    def test_existing_webhook_is_not_registered_again(self, urlopen):
        webhook_url = 'https://example.com/telegram/webhook/'
        urlopen.return_value = self.make_response({
            'ok': True,
            'result': {'url': webhook_url},
        })

        changed = configure_telegram_webhook('test-token', webhook_url)

        self.assertFalse(changed)
        urlopen.assert_called_once()
        self.assertTrue(urlopen.call_args.args[0].full_url.endswith('/getWebhookInfo'))

    @patch('lamp.apps.urllib.request.urlopen')
    def test_changed_webhook_url_is_registered(self, urlopen):
        webhook_url = 'https://example.com/telegram/webhook/'
        urlopen.side_effect = [
            self.make_response({'ok': True, 'result': {'url': ''}}),
            self.make_response({'ok': True, 'result': True}),
        ]

        changed = configure_telegram_webhook('test-token', webhook_url)

        self.assertTrue(changed)
        self.assertEqual(urlopen.call_count, 2)
        set_request = urlopen.call_args.args[0]
        self.assertEqual(set_request.full_url, 'https://api.telegram.org/bottest-token/setWebhook')
        self.assertEqual(set_request.method, 'POST')
        self.assertEqual(
            urllib.parse.parse_qs(set_request.data.decode('utf-8')),
            {'url': [webhook_url]},
        )


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
        self.assertNotContains(response, 'Tadbirgacha qolgan vaqt')
        self.assertNotContains(response, 'Tadbir boshlandi!')
        self.assertNotContains(response, 'Eslatma vaqtini tanlang')
        self.assertNotContains(response, 'userReminderMinutes')
        self.assertNotContains(response, 'enableCustomPushReminder')
        self.assertNotContains(response, 'Kalendarga qo&#x27;shish')
        self.assertContains(response, 'Lokatsiyani ochish')

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
            'hosts': 'New hosts',
            'event_datetime': '2030-05-01T10:00',
            'venue_name': 'New venue',
            'venue_address': 'New address',
            'venue_map_url': 'https://maps.app.goo.gl/example',
        })
        self.assertEqual(response.status_code, 302)
        created = Invitation.objects.get(venue_name='New venue')
        self.assertEqual(created.user, self.user)
        self.assertEqual(created.hosts, 'New hosts')
        self.assertEqual(created.event_type, 'wedding')
        self.assertEqual(created.template_style, 'paper')
        self.assertEqual(created.title, "To'y taklifnomasi")
        self.assertEqual(created.message, Invitation._meta.get_field('message').default)
        self.assertEqual(created.venue_map_url, 'https://maps.app.goo.gl/example')

    def test_owner_can_edit_invitation(self):
        edit_url = reverse('edit_invitation', args=[self.invitation.pk])
        self.client.force_login(self.user)

        page = self.client.get(edit_url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Ism va familiya')
        for removed_section in (
            'Tadbir turi va Dizayn',
            'Ism va Sarlavha',
            'Taklifnoma matni',
            'Media va Qo&#x27;shimchalar',
        ):
            with self.subTest(section=removed_section):
                self.assertNotContains(page, removed_section)

        response = self.client.post(edit_url, {
            'hosts': 'Updated hosts',
            'event_datetime': '2030-05-01T10:00',
            'venue_name': 'Updated venue',
            'venue_address': 'Updated address',
            'venue_map_url': 'https://maps.google.com/?q=Updated+venue',
        })

        self.assertRedirects(
            response,
            reverse('invitation_detail', args=[self.invitation.pk]),
        )
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.title, 'Private celebration')
        self.assertEqual(self.invitation.hosts, 'Updated hosts')
        self.assertEqual(self.invitation.venue_name, 'Updated venue')
        self.assertEqual(self.invitation.venue_map_url, 'https://maps.google.com/?q=Updated+venue')

    def test_map_link_is_used_on_public_invitation(self):
        self.invitation.venue_map_url = 'https://maps.app.goo.gl/example'
        self.invitation.save()

        response = self.client.get(reverse('invitation_detail', args=[self.invitation.pk]))

        self.assertContains(response, 'href="https://maps.app.goo.gl/example"')

    def test_map_link_only_accepts_http_or_https_urls(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('create_invitation'), {
            'venue_name': 'Unsafe map',
            'venue_map_url': 'javascript:alert(1)',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Invitation.objects.filter(venue_name='Unsafe map').exists())
        self.assertFormError(response.context['form'], 'venue_map_url', 'Enter a valid URL.')

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


class RemovedInvitationFieldsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testfile@gmail.com', email='testfile@gmail.com')

    def test_removed_fields_are_not_rendered_or_saved(self):
        self.client.force_login(self.user)
        page = self.client.get(reverse('create_invitation'))
        self.assertEqual(
            set(page.context['form'].fields),
            {'hosts', 'event_datetime', 'venue_name', 'venue_address', 'venue_map_url'},
        )
        self.assertContains(page, 'venue-map-search-input')
        self.assertContains(page, 'venue-map')
        self.assertContains(page, 'nominatim.openstreetmap.org')
        self.assertContains(page, 'maxNativeZoom: 15')
        self.assertContains(page, 'type="hidden" name="venue_address"')
        self.assertNotContains(page, 'Masalan: Toshkent shahri, Yunusobod tumani, Amir Temur ko&#x27;chasi')

        upload = SimpleUploadedFile("unused.txt", b"unused")
        response = self.client.post(reverse('create_invitation'), {
            'hosts': 'Test couple',
            'event_datetime': '2030-05-01T10:00',
            'venue_name': 'Venue',
            'venue_address': 'Address',
            'cover_image': upload,
        })
        self.assertEqual(response.status_code, 302)
        invitation = Invitation.objects.get(venue_name='Venue')
        self.assertFalse(invitation.cover_image)


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
