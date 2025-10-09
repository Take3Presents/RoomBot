#!/usr/bin/env bash
# Invoke various out-of-band tasks for roombot

export ROOMBAHT_DJANGO_SECRET_KEY="@SECRET_KEY@"
export ROOMBAHT_EMAIL_HOST_USER="@EMAIL_HOST_USER@"
export ROOMBAHT_EMAIL_HOST_PASSWORD="@EMAIL_HOST_PASSWORD@"
export ROOMBAHT_DB="@DB_NAME@"
export ROOMBAHT_SEND_MAIL="@SEND_MAIL@"
export ROOMBAHT_TMP="@TEMP@"
export ROOMBAHT_JWT_KEY="@JWT_KEY@"
export ROOMBAHT_HOST="@HOST@"
export ROOMBAHT_LOGLEVEL="@LOGLEVEL@"
export ROOMBAHT_SEND_ONBOARDING="@SEND_ONBOARDING@"
export ROOMBAHT_IGNORE_TRANSACTIONS="@IGNORE_TRANSACTIONS@"
export ROOMBAHT_ONBOARDING_BATCH="@ONBOARDING_BATCH@"
export ROOMBAHT_DEV_MAIL="@DEV_MAIL@"
export ROOMBAHT_SWAPS_ENABLED="@SWAPS_ENABLED@"
export ROOMBAHT_URL_PORT="@URL_PORT@"
export ROOMBAHT_URL_SCHEMA="@URL_SCHEMA@"

if [ "${ROOMBAHT_SEND_ONBOARDING,,}" == "true" ] ; then
    /opt/roombaht-backend/.venv/bin/python3 /opt/roombaht-backend/manage.py send_onboarding
else
    2>&1 echo "Not sending onboarding emails"
fi
