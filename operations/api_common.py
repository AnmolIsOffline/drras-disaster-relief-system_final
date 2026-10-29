from django.http import JsonResponse
from django.db import OperationalError
from functools import wraps


def profile(request):
    return getattr(request.user, 'profile', None)


def error(message, status=400):
    return JsonResponse({'error': message}, status=status)


def payload(request):
    import json
    try:
        return json.loads(request.body or '{}')
    except (ValueError, UnicodeDecodeError):
        return {}


def notify(user, title, body, link=''):
    if user:
        from .models import Notification
        Notification.objects.create(user=user, title=title, body=body, link=link)


def sqlite_write_conflict(message):
    """Turn SQLite writer contention into a retryable API conflict."""
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            try:
                return view(*args, **kwargs)
            except OperationalError as exc:
                if 'locked' in str(exc).casefold():
                    return error(message, 409)
                raise
        return wrapped
    return decorate
