#!/usr/bin/env bash

set -eu
SCRIPTDIR=$( cd "${0%/*}" && pwd)
ROOTDIR="${SCRIPTDIR%/*}"

export COVERAGE_FILE="${ROOTDIR}/.coverage"
export COVERAGE_RCFILE="${ROOTDIR}/.coveragerc"

cleanup() {
    if [ -e "$SQLITE" ] ; then
        rm "$SQLITE"
    fi
    "${SCRIPTDIR}/test_infra.sh" stop
    if [ -z "${SUCCESS:-}" ] && [ -e "$LOG" ] ; then
        cat "$LOG"
    fi
    "${SCRIPTDIR}/test_infra.sh" report
}

init() {
    if [ -e "$LOG" ] ; then
	rm "$LOG"
    fi
    "${SCRIPTDIR}/test_infra.sh" start
    local COUNT=5
    while [ "$COUNT" -gt 0 ] ; do
        if ! curl -o /dev/null -s http://localhost:8000/api/login/ ; then
            sleep 1
            COUNT="$((COUNT - 1))"
	    if [ "$COUNT" -le 0 ] ; then
		echo "Unable to start backend???"
		exit 1
	    fi
        else
            COUNT=0
        fi
    done
}

manage() {
    uv run --python "$(cat "${ROOTDIR}/.python-version")" --project "${ROOTDIR}/backend/pyproject.toml" --group dev --env-file "${ROOTDIR}/test.env" coverage run --append \
       "${ROOTDIR}/backend/manage.py" $*
}

run() {
    # first run tests with static fixtures
    source "${ROOTDIR}/test.env"

    manage loaddata test_admin
    manage loaddata test_users
    "$TAVERN" backend/tavern/test_login.tavern.yml

    manage loaddata test_admin
    manage loaddata test_users
    manage loaddata test_rooms
    "$TAVERN" backend/tavern/test_room_swap.tavern.yml
    "$TAVERN" backend/tavern/test_room_swap_multi_hotel.tavern.yml
    "$TAVERN" backend/tavern/test_room_field_validation.tavern.yml
    "$TAVERN" backend/tavern/test_admin.tavern.yml
    "$TAVERN" backend/tavern/test_reports.tavern.yml

    manage room_list >> "$LOG" 2>&1
    manage room_list -t Queen >> "$LOG" 2>&1
    manage room_show --hotel ballys 503 >> "$LOG" 2>&1
    manage user_show testadmin@example.com >> "$LOG" 2>&1
    manage user_show testuser1@example.com >> "$LOG" 2>&1
    manage check --fail-level=WARNING --deploy >> "$LOG" 2>&1

    # then run tests following typical import data flow
    manage flush --noinput >> "$LOG" 2>&1
    manage migrate >> "$LOG" 2>&1
    manage create_staff "${ROOTDIR}/samples/exampleMainStaffList.csv"
    manage create_rooms \
           "${ROOTDIR}/samples/exampleBallysRoomList.csv" \
           --hotel ballys --preserve --force --blank-placement-is-available \
           --default-check-in="1999/1/1" --default-check-out="1999/1/10"
    manage create_rooms \
           "${ROOTDIR}/samples/exampleNuggetRoomList.csv" \
           --hotel nugget --preserve --force --blank-placement-is-available  \
           --default-check-in "1999/1/1" --default-check-out "1999/1/10"

    manage loaddata test_admin
    "$TAVERN" backend/tavern/test_guests.tavern.yml
    manage room_list >> "$LOG" 2>&1
    manage room_list -t Queen >> "$LOG" 2>&1
    manage room_show --hotel ballys 400 >> "$LOG" 2>&1
    manage room_show --hotel nugget 110 >> "$LOG" 2>&1
    manage check --fail-level=WARNING --deploy >> "$LOG" 2>&1

    SUCCESS="yea girl"
}

SQLITE="${ROOTDIR}/backend/test.sqlite"
export PYTHONPATH="${ROOTDIR}/backend/tavern"
export ROOTDIR
TAVERN="${ROOTDIR}/backend/.venv/bin/tavern-ci"
LOG="${ROOTDIR}/test.log"

if [ -e "$SQLITE" ] ; then
    rm -rf "$SQLITE"
fi

export ROOMBAHT_CONFIG="${ROOTDIR}/test.env"

trap cleanup EXIT
init
run
