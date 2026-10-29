from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect


class EnforceAccountApprovalMiddleware:
    """End existing sessions as soon as an account is rejected or suspended."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            profile = getattr(user, 'profile', None)
            if profile and profile.approval in ('REJECTED', 'SUSPENDED'):
                status = profile.approval
                logout(request)
                if request.path.startswith('/api/'):
                    return JsonResponse({'error': f'This account is {status.lower()}. Contact an administrator.'}, status=403)
                return redirect('/login.html')
        return self.get_response(request)
