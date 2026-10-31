import uuid

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Invitation
from .views import OWNER_SESSION_KEY


class InvitationPrivacyTests(TestCase):
    def setUp(self):
        self.owner_token = uuid.uuid4()
        self.invitation = Invitation.objects.create(
            owner_token=self.owner_token,
            title='Private celebration',
            hosts='Test host',
            event_datetime=timezone.now(),
            venue_name='Private venue',
            venue_address='Private address',
        )

    def test_my_invitations_only_shows_current_browser_owner(self):
        owner_client = self.client
        session = owner_client.session
        session[OWNER_SESSION_KEY] = str(self.owner_token)
        session.save()

        response = owner_client.get(reverse('my_invitations'))
        self.assertContains(response, 'Private celebration')

        other_client = self.client_class()
        response = other_client.get(reverse('my_invitations'))
        self.assertNotContains(response, 'Private celebration')

    def test_public_pages_do_not_list_created_invitations(self):
        for path in ('home', 'templates_list'):
            with self.subTest(path=path):
                response = self.client.get(reverse(path))
                self.assertNotContains(response, 'Private celebration')
                self.assertNotContains(response, 'Private venue')

    def test_shared_invitation_link_remains_public(self):
        response = self.client.get(
            reverse('invitation_detail', args=[self.invitation.pk])
        )
        self.assertContains(response, 'Private celebration')

    def test_success_page_is_only_visible_to_owner_session(self):
        owner_client = self.client_class()
        session = owner_client.session
        session[OWNER_SESSION_KEY] = str(self.owner_token)
        session.save()
        response = owner_client.get(
            reverse('success_invitation', args=[self.invitation.pk])
        )
        self.assertEqual(response.status_code, 200)

        other_client = self.client_class()
        response = other_client.get(
            reverse('success_invitation', args=[self.invitation.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_created_invitation_is_assigned_to_current_browser(self):
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
        session_token = uuid.UUID(self.client.session[OWNER_SESSION_KEY])
        self.assertEqual(created.owner_token, session_token)
