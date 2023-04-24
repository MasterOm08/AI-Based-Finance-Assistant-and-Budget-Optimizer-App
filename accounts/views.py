from babel._compat import force_text
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.db.models.query_utils import Q
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.safestring import mark_safe
from .send_OTP import send_sms_code

from accounts.forms import CustomUSerCreationForm, UpdateProfileForm
from .forms import Set_Password_Form, Password_Reset_Form, SMSCodeForm
from .tokens import account_activation_token
from .send_activation_email import send_activation_email
from .models import CustomUser


# Create your views here.
def register(request):
    form = CustomUSerCreationForm()
    if request.method == 'POST':
        form = CustomUSerCreationForm(request.POST or None)
        if form.is_valid():
            # save form in the memory not in database
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            # Send activation email
            send_activation_email(request, user)
            return redirect('accounts:login')
    context = {'form': form}
    return render(request, 'accounts/register.html', context)


def login_view(request):
    if request.user.is_authenticated:
        messages.info(request, mark_safe(f'You are already logged in as <b>{request.user.username}</b>. To switch user'
                                         f' <a href="#" data-toggle="modal" data-target="#logoutModal"></i>'
                                         f'log out here.</a>'))
        return redirect('website:index')
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        remember_me = request.POST.get('remember_me')
        if remember_me:
            request.session.set_expiry(0)
        user = authenticate(request, username=email, password=password)
        if user is not None:
            if user.email_verified and not user.enable_two_factor_authentication:
                login(request, user=user)
                messages.success(request, message=f'{user.email} successfully logged in!')
                return redirect('website:index')
            elif user.email_verified and user.enable_two_factor_authentication:
                user_id = user.id
                send_sms_code(phone_number=user.phone_number, code=user.smscode.number)
                messages.success(request, message=f'{user.email} SMS verification code sent!')
                return redirect('accounts:sms_verify', user_id=user_id)  # redirect to other page with user ID

            else:
                messages.error(request, 'Your account is inactive. Click on the activation link in your inbox to '
                                        'activate your'
                                        'account!')
        else:
            messages.error(request, 'Invalid username or password. Check your credentials!')
    return render(request, 'accounts/login.html')


def sms_verification_view(request):
    user = request.GET.get('user_id')  # get the user ID from the URL query string
    form = SMSCodeForm(user_id=user)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            user = authenticate(request, username=user.email, password=user.password)
            login(request, user=user)
            messages.success(request, message=f'{user.email} successfully logged in!')
            return redirect('website:index')
        else:
            messages.error(request, 'An error occurred!')

    context = {'form': form}
    return render(request, 'accounts/sms_verify.html', context)


@login_required
def logout_view(request):
    logout(request)
    messages.success(request, 'Logged out successfully!')
    return redirect('accounts:login')


# class MyProfile(LoginRequiredMixin, View):
#     def get(self, request):
#         user_form = UserUpdateForm(instance=request.user)
#         print(user_form)
#         profile_form = ProfileUpdateForm(instance=request.user.profile)
#         print(profile_form)
#         context = {
#             'user_form': user_form,
#             'profile_form': profile_form
#         }
#
#         return render(request, 'accounts/profile/profile.html', context)
#
#     def post(self, request):
#         user_form = UserUpdateForm(
#             request.POST,
#             instance=request.user
#         )
#         profile_form = ProfileUpdateForm(
#             request.POST,
#             request.FILES,
#             instance=request.user.profile
#         )
#         two_FA = request.POST.get('2FA')
#         if user_form.is_valid():
#             if two_FA:
#                 request.user.enable_two_factor_authentication = True
#             user_form.save()
#             profile_form.save()
#             messages.success(request, 'Your profile has been updated successfully')
#
#             return render(request, 'accounts/profile/profile.html')
#         else:
#             context = {
#                 'user_form': user_form,
#                 'profile_form': profile_form
#             }
#             messages.error(request, 'Error updating you profile')
#
#             return render(request, 'accounts/profile/profile.html', context)


@login_required
def update_profile(request):
    if request.method == 'POST':
        form = UpdateProfileForm(request.POST, request.FILES, instance=request.user)
        two_FA = request.POST.get('2FA')
        if two_FA is not None:
            request.user.enable_two_factor_authentication = True
        else:
            request.user.enable_two_factor_authentication = False
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated successfully')
    else:
        form = UpdateProfileForm(instance=request.user)
    return render(request, 'accounts/profile/profile.html', {'form': form})


# DELETE USER ACCOUNT
@login_required
def delete_user_account(request):
    if request.method == 'POST':
        user = User.objects.get(username=request.user.username)
        user.delete()
        messages.success(request, f'{user} account successfully deleted!')
        redirect('accounts.login')
    return render(request, 'accounts/profile/delete_account.html')


# password views
@login_required
def password_change(request):
    user = request.user
    if request.method == 'POST':
        form = Set_Password_Form(user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Your password has been changed")
            return redirect('accounts:login')
        else:
            for error in list(form.errors.values()):
                messages.error(request, error)

    form = Set_Password_Form(user)
    return render(request, 'accounts/password-reset/password_reset_confirm.html', {'form': form})


def password_reset_request(request):
    if request.method == 'POST':
        form = Password_Reset_Form(request.POST)
        if form.is_valid():
            user_email = form.cleaned_data['email']
            associated_user = User.objects.filter(Q(email=user_email)).first()
            if associated_user:
                subject = "Password User Reset request"
                message = render_to_string("accounts/password-reset/password_reset_email.html", {
                    'user': associated_user,
                    'domain': get_current_site(request).domain,
                    'uid': urlsafe_base64_encode(force_bytes(associated_user.pk)),
                    'token': account_activation_token.make_token(associated_user),
                    "protocol": 'https' if request.is_secure() else 'http'
                })
                # email = EmailMessage(subject, message, to=[associated_user.email])
                print(settings.EMAIL_HOST_USER)
                email = send_mail(subject=subject, from_email=settings.EMAIL_HOST_USER, message=message,
                                  recipient_list=[associated_user.email])
                if email:
                    messages.success(request,
                                     mark_safe(
                                         """<h2>Password reset sent</h2><hr> <p> We've emailed you instructions for 
                                         setting your password, if an account exists with the email you entered. You 
                                         should receive them shortly.<br>If you don't receive an email, please make 
                                         sure you've entered the address you registered with, and check your spam 
                                         folder. </p>"""
                                     ))
                    messages.success(request, "Email Sent Successfully. Check your inbox!")
                    return redirect('website:index')
                else:
                    messages.error(request, mark_safe("Problem sending reset password email, <b>SERVER PROBLEM</b>"))

            else:
                messages.error(request, "Invalid email address. Try again!")
                return redirect('accounts:password_reset')

        for error in list(form.errors.values()):
            messages.error(request, error)

    form = Password_Reset_Form()
    return render(
        request=request,
        template_name="accounts/password-reset/password_reset.html",
        context={"form": form}
    )


def passwordResetConfirm(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except:
        user = None

    if user is not None and account_activation_token.check_token(user, token):
        if request.method == 'POST':
            form = Set_Password_Form(user, request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, mark_safe("Your password has been set. You may go ahead and <b>log in </b> "
                                                    "now."))
                return redirect('website:index')
            else:
                for error in list(form.errors.values()):
                    messages.error(request, error)

        form = Set_Password_Form(user)
        return render(request, 'accounts/password-reset/password_reset_confirm.html', {'form': form})
    else:
        messages.error(request, "Link is expired")

    messages.error(request, 'Something went wrong, redirecting back to Homepage')
    return redirect("accounts.login")


def activate(request, uidb64, token):
    User = get_user_model()
    try:
        uid = force_text(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and account_activation_token.check_token(user, token):
        user.is_active = True
        user.email_verified = True
        user.save()
        messages.success(request, 'Thank you for your email confirmation. Now you can login your account.')
        return redirect('accounts:login')
    else:
        messages.error(request, 'Activation link is invalid!')

    return redirect('website:index')
