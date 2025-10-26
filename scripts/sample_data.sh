#!/usr/bin/env bash

set -e
SCRIPTDIR=$( cd "${0%/*}" && pwd)
ROOTDIR="${SCRIPTDIR%/*}"

if [ -n "$ROOMBAHT_CONFIG" ] ; then
    echo "Using alternative config ${ROOMBAHT_CONFIG}"
    if [ ! -e "$ROOMBAHT_CONFIG" ] ; then
	echo "Unable to open alternate config, lollll"
	exit 2
    fi
else
    ROOMBAHT_CONFIG="dev.env"
fi
source "$ROOMBAHT_CONFIG"

"${SCRIPTDIR}/manage_dev" migrate
"${SCRIPTDIR}/manage_dev" create_rooms "${ROOTDIR}/samples/exampleBallysRoomList.csv" \
			  --force --preserve --hotel-name=ballys --blank-placement-is-available
"${SCRIPTDIR}/manage_dev" create_rooms "${ROOTDIR}/samples/exampleNuggetRoomList.csv" \
			  --force --preserve --hotel-name=nugget --blank-placement-is-available
"${SCRIPTDIR}/manage_dev" create_staff "${ROOTDIR}/samples/exampleMainStaffList.csv"
