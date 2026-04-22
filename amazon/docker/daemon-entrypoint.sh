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

python daemon/main.py
