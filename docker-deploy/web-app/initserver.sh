#!/bin/bash

res=1
while [ "$res" != "0" ]
do
    sleep 3
    python3 manage.py migrate
    res="$?"
done

python3 manage.py makemigrations
python3 manage.py migrate
