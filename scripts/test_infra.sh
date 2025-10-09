#!/usr/bin/env bash

set -e
SCRIPTDIR=$( cd "${0%/*}" && pwd)
ROOTDIR="${SCRIPTDIR%/*}"

source "${ROOTDIR}/test.env"

COVERAGEFILE="${ROOTDIR}/.coverage"
export COVERAGE_RCFILE="${ROOTDIR}/.coveragerc"
LOG="${ROOTDIR}/test.log"
SQLITE="${ROOTDIR}/${ROOMBAHT_SQLITE}"
BACKEND="${ROOTDIR}/backend"

usage() {
    echo "${0}            start"
    echo "${0}            stop"
}

start() {
    uv run --active coverage run --data-file "$COVERAGEFILE" \
		--source="reservations,party,waittime" \
		"${BACKEND}/manage.py" migrate >> "$LOG" 2>&1
    nohup uv run --active coverage run --data-file "$COVERAGEFILE" \
	  --source="backend" --append \
	  "${BACKEND}/manage.py" \
	  runserver --noreload --nothreading 0.0.0.0:8000 \
	  < /dev/null >> "$LOG" 2>&1 & disown
}

stop() {
    if [ -e "$SQLITE" ] ; then
	rm "$SQLITE"
    fi
    PIDS="$(pgrep -f '.*manage.py runserver.*')"
    if [ -n "$PIDS" ] ; then
	for pid in $PIDS ; do
	    if ps "$pid" > /dev/null 2>&1 ; then
		kill -s SIGTERM "$pid"
	    fi
	done
    fi
}

report() {
    coverage report --data-file "$COVERAGEFILE" -m --skip-covered
}

if [ $# == 0 ] ; then
    usage
    exit 1
fi
ACTION="$1"
shift

. "${BACKEND}/.venv/bin/activate"
if [ "$ACTION" == "start" ] ; then
    start
elif [ "$ACTION" == "stop" ] ; then
    stop
elif [ "$ACTION" == "report" ] ; then
    report
else
    usage
    exit 1
fi
