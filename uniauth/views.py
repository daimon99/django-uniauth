import logging

import jwt
from django.contrib import auth
from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView
from django.http import HttpResponseRedirect
# Create your views here.
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django_redis import get_redis_connection

from uniauth.models import Account
from . import settings

User = get_user_model()

log = logging.getLogger(__name__)


def get_jwt_secret():
    if settings.UNIAUTH_JWT_SECRET:
        return settings.UNIAUTH_JWT_SECRET
    else:
        conn = get_redis_connection("uniauth")
        secret = conn.get('jwt_secret')
        if secret:
            return secret
        return 'nicainicainicaicaicai'


def get_qywx_user(provider, uid):
    try:
        account = Account.objects.get(provider=provider, uid=uid)
        return account.user
    except Account.DoesNotExist:
        username = f'{provider}-{uid}'
        user = User.objects.create_user(username)
        Account.objects.create(
            user=user,
            provider=provider,
            uid=uid,
            created=now()
        )
        return user


class UniAuthView(LoginView):
    redirect_authenticated_user = True

    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        jwt_token = request.GET.get('jwt') or request.COOKIES.get('jwt')
        if jwt_token:
            try:
                payload = jwt.decode(jwt_token, get_jwt_secret())
                provider = payload.get('provider')
                uid = payload.get('uid')
                if provider and uid:
                    if provider == 'qywx':
                        user = get_qywx_user(provider, uid)
                        auth.login(request, user)
                    else:
                        log.warning('不能识别的 provider: %s', payload)
                else:
                    log.warning('jwt payload 信息非法: %s', payload)
            except Exception as e:
                log.warning('jwt 解析异常: %s', e)

        if self.redirect_authenticated_user and self.request.user.is_authenticated:
            redirect_to = self.get_success_url()
            if redirect_to == self.request.path:
                raise ValueError(
                    "Redirection loop for authenticated user detected. Check that "
                    "your LOGIN_REDIRECT_URL doesn't point to a login page."
                )
            return HttpResponseRedirect(redirect_to)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'qywx_login_url': f'{settings.QYWX_LOGIN_URL}{self.request.build_absolute_uri()}'
        })
        return context


verify_uniauth = UniAuthView.as_view()
