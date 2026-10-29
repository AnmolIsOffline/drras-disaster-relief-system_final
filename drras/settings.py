import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE=BASE_DIR/'.env'
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        key,value=line.split('=',1); value=value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(),value)
DEBUG = os.getenv('DJANGO_DEBUG', '1') == '1'
from django.core.exceptions import ImproperlyConfigured
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY','').strip()
if not SECRET_KEY:
    if not DEBUG: raise ImproperlyConfigured('DJANGO_SECRET_KEY must be set when DJANGO_DEBUG=0.')
    SECRET_KEY='local-demo-key-change-before-deploy'
if not DEBUG and (len(SECRET_KEY)<50 or len(set(SECRET_KEY))<5 or SECRET_KEY=='replace-for-deployment'):
    raise ImproperlyConfigured('DJANGO_SECRET_KEY must be a unique random value of at least 50 characters when DJANGO_DEBUG=0.')
DEMO_PAYMENT_MODE=os.getenv('DEMO_PAYMENT_MODE','1' if DEBUG else '0')=='1'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
INSTALLED_APPS = ['django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','operations']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','drras.middleware.EnforceAccountApprovalMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'drras.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'templates'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'drras.wsgi.application'
DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':BASE_DIR/'db.sqlite3','OPTIONS':{'timeout':10}}}
AUTH_PASSWORD_VALIDATORS=[]
LANGUAGE_CODE='en-us'; TIME_ZONE='Asia/Kolkata'; USE_I18N=True; USE_TZ=True
STATIC_URL='static/'; STATICFILES_DIRS=[BASE_DIR/'static']; MEDIA_URL='/media/'; MEDIA_ROOT=BASE_DIR/'media'
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
SESSION_COOKIE_HTTPONLY=True; CSRF_COOKIE_SAMESITE='Lax'
SESSION_COOKIE_SECURE=not DEBUG; CSRF_COOKIE_SECURE=not DEBUG
SECURE_SSL_REDIRECT=os.getenv('SECURE_SSL_REDIRECT','0' if DEBUG else '1')=='1'
SECURE_HSTS_SECONDS=int(os.getenv('SECURE_HSTS_SECONDS','0' if DEBUG else '31536000'))
SECURE_HSTS_INCLUDE_SUBDOMAINS=os.getenv('SECURE_HSTS_INCLUDE_SUBDOMAINS','0')=='1'
SECURE_HSTS_PRELOAD=os.getenv('SECURE_HSTS_PRELOAD','0')=='1'
if os.getenv('TRUST_X_FORWARDED_PROTO','0')=='1': SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')
