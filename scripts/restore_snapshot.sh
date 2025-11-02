#!/usr/bin/env bash
set -euo pipefail

SCRIPTDIR=$( cd "${0%/*}" && pwd)
ROOTDIR="${SCRIPTDIR%/*}"

problems() {
    2>&1 echo "Error: $*"
    exit 1
}

usage() {
    cat <<EOF
Usage: $0 <snapshot.sql|snapshot.sql.gz>

Options:
  -h             Show this help

Examples:
  $0 ./roombaht-staging-01011969-0420.sql.gz
EOF
}

info() { echo "==> $*"; }

if [ -f "${ROOTDIR}/docker-dev.env" ]; then
    # shellcheck disable=SC1090
    source "${ROOTDIR}/docker-dev.env"
else
    problems "Missing ${ROOTDIR}/docker-dev.env, rip"
fi

SNAPSHOT_FILE="${1-}"
[ -n "$SNAPSHOT_FILE" ] || { usage; problems "Missing snapshot file argument"; }
[ -f "$SNAPSHOT_FILE" ] || problems "Snapshot file not found: $SNAPSHOT_FILE"

# Decide how to stream the snapshot
if [[ "$SNAPSHOT_FILE" == *.gz ]]; then
    STREAM_CMD="gunzip -c '$SNAPSHOT_FILE'"
else
    STREAM_CMD="cat '$SNAPSHOT_FILE'"
fi

# even locally, it can take a minute for the db to come back to life
wait_for_db_accepting_connections() {
    local db="$1"
    local i allow
    local RETRIES=30
    local SLEEP_SECONDS=1

    for i in $(seq 1 "$RETRIES"); do
        allow="$(run_psql postgres "SELECT datallowconn FROM pg_database WHERE datname = '$db';" || true)"
        allow="$(echo "$allow" | tr -d '[:space:]' || true)"

        if [ "$allow" = "t" ]; then
            if docker compose exec -T db psql -U "$POSTGRES_USER" -d "$db" -c '\q' >/dev/null 2>&1; then
                return 0
            fi
        elif [ "$allow" = "f" ]; then
            echo "Database '$db' exists but disallows connections; attempting to enable..."
            run_psql postgres "ALTER DATABASE \"${db}\" WITH ALLOW_CONNECTIONS = true;" || problems "Unable to enable connections"
        else
            if docker compose exec -T db psql -U "$POSTGRES_USER" -d "$db" -c '\q' >/dev/null 2>&1; then
                return 0
            fi
        fi

        sleep "$SLEEP_SECONDS"
    done

    return 1
}

run_psql() {
    db="$1"
    sql="$2"
    docker compose exec -T db psql -U "$POSTGRES_USER" -d "$db" -v ON_ERROR_STOP=1 -q -A -t -c "$sql"
}

# # Revoke connects, terminate any backends, drop and create the DB

# * kick connections and block for now
# * drop and re-create the database
info "Dropping and recreating database '$POSTGRES_DB' (connecting to 'postgres' for maintenance)..."
run_psql postgres "REVOKE CONNECT ON DATABASE \"$POSTGRES_DB\" FROM public;" >/dev/null 2>&1 || problems "Unable to bloc connections"
run_psql postgres "ALTER DATABASE \"$POSTGRES_DB\" CONNECTION LIMIT 0;" >/dev/null 2>&1 || problems "Unable to update connection limit"
run_psql postgres "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$(echo "$POSTGRES_DB" | sed "s/'/''/g")' AND pid <> pg_backend_pid();" >/dev/null 2>&1 || problems "Unable to terminate connections"
run_psql postgres "DROP DATABASE IF EXISTS \"$POSTGRES_DB\";" >/dev/null 2>&1 || problems "Unable to drop database"
run_psql postgres "CREATE DATABASE \"$POSTGRES_DB\";" >/dev/null 2>&1 || problems "Uanble to create database"
wait_for_db_accepting_connections "$POSTGRES_DB"

# "translate" any roles set in RDS to be usable locally
# relatively conservative fetching of roles from OWNER TO, CREATE ROLE, SET ROLE
info "Scanning snapshot for referenced roles and ensuring they exist in the cluster..."
ROLES_TMP="$(mktemp)"
trap 'rm -f "$ROLES_TMP"' EXIT

set +o errexit
# todo something other than eval heh
eval "$STREAM_CMD" | \
  grep -oE -e "OWNER TO[[:space:]]*['\"]?[A-Za-z0-9_]+" \
            -e "CREATE ROLE[[:space:]]*['\"]?[A-Za-z0-9_]+" \
            -e "SET ROLE[[:space:]]*['\"]?[A-Za-z0-9_]+" \
  | sed -E "s/^(OWNER TO|CREATE ROLE|SET ROLE)[[:space:]]*['\"]?([A-Za-z0-9_]+).*/\2/" \
  | sort -u > "$ROLES_TMP" || true
set -o errexit

while read -r role; do
    [ -z "$role" ] && continue
    # skip obvious existing roles
    if [ "$role" = "$POSTGRES_USER" ] || [ "$role" = "postgres" ]; then
        continue
    fi
    info "Ensuring role '$role' exists..."
    # Create role if missing; use a DO block to avoid errors if it already exists.
    run_psql postgres "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$role') THEN CREATE ROLE \"$role\" LOGIN; END IF; END \$\$;" >/dev/null 2>&1 || problems "Unable to update roles"
done < "$ROLES_TMP"

info "Restoring snapshot into database '$POSTGRES_DB'..."
eval "$STREAM_CMD" | docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 > /dev/null 2>&1
info "Restore complete 🎺"
exit 0
