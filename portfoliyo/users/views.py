"""
Account-related views.

"""
from functools import partial

from django.core.urlresolvers import reverse
from django.views.decorators.http import require_POST

from django.contrib.auth import views as auth_views, forms as auth_forms
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from ratelimit.decorators import ratelimit
from registration import views as registration_views
from session_csrf import anonymous_csrf

from . import forms



@anonymous_csrf
@ratelimit(field='username', method='POST', rate='5/m')
def login(request):
    kwargs = {
        'template_name': 'users/login.html',
        'authentication_form': forms.CaptchaAuthenticationForm,
        }
    # the contrib.auth login view doesn't pass request into the bound form,
    # but CaptchaAuthenticationForm needs it, so we ensure it's passed in
    if request.method == 'POST':
        kwargs['authentication_form'] = partial(
            kwargs['authentication_form'], request)
    return auth_views.login(request, **kwargs)



@require_POST
def logout(request):
    return auth_views.logout_then_login(request)



@login_required
def password_change(request):
    response = auth_views.password_change(
        request,
        template_name='users/password_change.html',
        password_change_form=auth_forms.PasswordChangeForm,
        post_change_redirect=reverse('home')
        )

    if response.status_code == 302:
        messages.success(request, "Password changed.")

    return response



@anonymous_csrf
def password_reset(request):
    response = auth_views.password_reset(
        request,
        password_reset_form=forms.PasswordResetForm,
        template_name='users/password_reset.html',
        email_template_name='registration/password_reset_email.txt',
        subject_template_name='registration/password_reset_subject.txt',
        post_reset_redirect=reverse('home')
        )

    if response.status_code == 302:
        messages.success(
            request,
            u"Password reset email sent; check your email. "
            u"If you don't receive an email, verify that you are entering the "
            u"email address you signed up with, and try again."
            )

    return response



@anonymous_csrf
def password_reset_confirm(request, uidb36, token):
    response = auth_views.password_reset_confirm(
        request,
        uidb36=uidb36,
        token=token,
        template_name='users/password_reset_confirm.html',
        set_password_form=auth_forms.SetPasswordForm,
        post_reset_redirect=reverse('home')
        )

    if response.status_code == 302:
        messages.success(request, "Password changed.")

    return response



def activate(request, activation_key):
    response = registration_views.activate(
        request,
        activation_key=activation_key,
        backend='portfoliyo.users.register.RegistrationBackend',
        template_name='users/activate.html',
        success_url=reverse('home'),
        )

    if response.status_code == 302:
        messages.success(request, "Account activated; now you can login.")

    return response



@anonymous_csrf
def register(request):
    response = registration_views.register(
        request,
        backend='portfoliyo.users.register.RegistrationBackend',
        template_name='users/register.html',
        success_url=reverse('home'),
        )

    if response.status_code == 302:
        messages.success(
            request, "Check your email for an account activation link.")

    return response
