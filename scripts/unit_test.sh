#!/usr/bin/env bash

set -e
SCRIPTDIR=$( cd "${0%/*}" && pwd)
ROOTDIR="${SCRIPTDIR%/*}"

cleanup() {
    if [ -e "$SQLITE" ] ; then
        rm "$SQLITE"
    fi
}

run() {
    source "${ROOTDIR}/test.env"
    cd backend && "${ROOTDIR}/backend/.venv/bin/pytest"
}

SQLITE="${ROOTDIR}/backend/test.sqlite"
export ROOTDIR

if [ -e "$SQLITE" ] ; then
    rm -rf "$SQLITE"
fi

export ROOMBAHT_CONFIG="${ROOTDIR}/test.env"

trap cleanup EXIT
run
