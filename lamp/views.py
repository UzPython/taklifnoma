import uuid

from django.shortcuts import render, redirect, get_object_or_404
from .models import Invitation, RSVP
from .forms import InvitationForm, RSVPForm


OWNER_SESSION_KEY = 'invitation_owner_token'


def _get_owner_token(request):
    token = request.session.get(OWNER_SESSION_KEY)
    if token is None:
        token = str(uuid.uuid4())
        request.session[OWNER_SESSION_KEY] = token
        request.session.set_expiry(60 * 60 * 24 * 365)
    return uuid.UUID(token)


def home_view(request):
    return render(request, 'lamp/home.html')

def templates_list_view(request):
    return render(request, 'lamp/templates_list.html')

def my_invitations_view(request):
    invitations = Invitation.objects.none()
    token = request.session.get(OWNER_SESSION_KEY)
    if token:
        invitations = Invitation.objects.filter(
            owner_token=uuid.UUID(token)
        ).order_by('-created_at')
    return render(request, 'lamp/my_invitations.html', {
        'invitations': invitations,
    })

def create_view(request):
    initial = {}
    style = request.GET.get('style')
    if style in ['paper', 'royal', 'rose', 'video']:
        initial['template_style'] = style

    if request.method == 'POST':
        form = InvitationForm(request.POST, request.FILES)
        if form.is_valid():
            invitation = form.save(commit=False)
            invitation.owner_token = _get_owner_token(request)
            invitation.save()
            return redirect('success_invitation', pk=invitation.pk)
    else:
        form = InvitationForm(initial=initial)
    return render(request, 'lamp/create.html', {'form': form})

def success_view(request, pk):
    invitation = get_object_or_404(
        Invitation,
        pk=pk,
        owner_token=_get_owner_token(request),
    )
    invitation_url = request.build_absolute_uri(f'/invitation/{invitation.pk}/')
    return render(request, 'lamp/success.html', {'invitation': invitation, 'invitation_url': invitation_url})

def like_invitation(request, pk):
    invitation = get_object_or_404(Invitation, pk=pk)
    if request.method == 'POST':
        invitation.likes_count += 1
        invitation.save(update_fields=['likes_count'])
    return redirect('invitation_detail', pk=invitation.pk)

def invitation_detail_view(request, pk):
    invitation = get_object_or_404(Invitation, pk=pk)
    rsvps = invitation.rsvps.all().order_by('-created_at')
    
    if request.method == 'POST':
        form = RSVPForm(request.POST)
        if form.is_valid():
            rsvp = form.save(commit=False)
            rsvp.invitation = invitation
            rsvp.save()
            return redirect('invitation_detail', pk=invitation.pk)
    else:
        form = RSVPForm()

    context = {
        'invitation': invitation,
        'rsvps': rsvps,
        'rsvp_form': form,
    }
    return render(request, 'lamp/detail.html', context)

def delete_invitation_view(request, pk):
    invitation = get_object_or_404(
        Invitation,
        pk=pk,
        owner_token=_get_owner_token(request),
    )
    if request.method == 'POST':
        invitation.delete()
    return redirect('my_invitations')
