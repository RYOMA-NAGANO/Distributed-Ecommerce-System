#!/bin/bash
set -e

python3 manage.py makemigrations --noinput

until python3 manage.py migrate --noinput
do
    sleep 3
done
