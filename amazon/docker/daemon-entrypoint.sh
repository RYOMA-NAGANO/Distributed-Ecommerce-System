#!/bin/sh
set -e

echo "Waiting for database..."
until python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'amazon_web.settings')
django.setup()
from django.db import connection
connection.ensure_connection()
" 2>/dev/null; do
  sleep 2
done
echo "Database ready."

echo "Waiting for web migrations..."
until python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'amazon_web.settings')
django.setup()
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute(\"select 1 from django_migrations where app = 'store' and name = '0004_expand_catalog_products'\")
    cursor.fetchone()
" 2>/dev/null; do
  sleep 2
done
echo "Migrations ready."

python daemon/main.py
