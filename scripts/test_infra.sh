#!/usr/bin/env bash

set -eu
SCRIPTDIR=$( cd "${0%/*}" && pwd)
ROOTDIR="${SCRIPTDIR%/*}"

source "${ROOTDIR}/test.env"

LOG="${ROOTDIR}/test.log"
SQLITE="${ROOTDIR}/${ROOMBAHT_SQLITE}"
BACKEND="${ROOTDIR}/backend"

usage() {
    echo "${0}            start"
    echo "${0}            stop"
}

start() {
    if [ -e "$SQLITE" ] ; then
	rm "$SQLITE"
    fi
    cd "${BACKEND}"
    uv run --python "$(cat "${ROOTDIR}/.python-version")" --project "${ROOTDIR}/backend/pyproject.toml" \
       --group dev --env-file "${ROOTDIR}/test.env" coverage run --append \
       manage.py migrate >> "$LOG" 2>&1
    nohup uv run --python "$(cat "${ROOTDIR}/.python-version")" --project "${ROOTDIR}/backend/pyproject.toml"  \
	  --group dev --env-file "${ROOTDIR}/test.env" coverage run --append \
	  manage.py \
	  runserver --noreload --nothreading 0.0.0.0:8000 \
	  < /dev/null >> "$LOG" 2>&1 & disown
    cd "${ROOTDIR}"
}

stop() {
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
    uv run --python "$(cat "${ROOTDIR}/.python-version")" --project "${ROOTDIR}/backend/pyproject.toml" --group dev --env-file "${ROOTDIR}/test.env" coverage report -m --skip-covered
    rm "$COVERAGE_FILE"
}

if [ $# == 0 ] ; then
    usage
    exit 1
fi
ACTION="$1"
shift

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
