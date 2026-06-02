#!/bin/bash
# Run DTR from the test node against the Drizzle container image.

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRIZZLE_SOURCE_DIR="${DRIZZLE_SOURCE_DIR:-${HOME}/src/opendev.org/drizzle/drizzle}"
BUILD_ROOT="${DRIZZLE_DTR_BUILD_ROOT:-${ROOT_DIR}/.dtr-container-build}"
VARDIR="${BUILD_ROOT}/tests/var"
WRAPPER="${ROOT_DIR}/tools/dtr-podman-wrapper.sh"
BASE_TESTS="main,bool_type,cast,ddl_transactions,execute,flush_tables,identifiers,jp,mysql_compatibility,regression,tamil,time_type,uuid_type,microtime_type"

discover_plugin_suites() {
    local plugin_root="${DRIZZLE_SOURCE_DIR}/plugin"
    local skip_suites="${DTR_PLUGIN_SUITES_SKIP:-js,json_server,mysql_protocol,query_log,rabbitmq}"

    [ -d "${plugin_root}" ] || return 0

    find "${plugin_root}" -mindepth 1 -maxdepth 1 -type d -exec sh -c '
        skip_suites="$1"
        shift
        for plugin_dir do
            plugin_ini="${plugin_dir}/plugin.ini"
            suite_name="${plugin_dir##*/}"

            [ -d "${plugin_dir}/tests/t" ] || continue
            [ -d "${plugin_dir}/tests/r" ] || continue
            [ -f "${plugin_ini}" ] || continue

            case ",${skip_suites}," in
                *,"${suite_name}",*) continue ;;
            esac

            if grep -Eq "^[[:space:]]*disabled[[:space:]]*=[[:space:]]*(1|yes|true)[[:space:]]*$" "${plugin_ini}"; then
                continue
            fi
            if grep -Eq "^[[:space:]]*testsuite[[:space:]]*=[[:space:]]*disable[[:space:]]*$" "${plugin_ini}"; then
                continue
            fi

            printf "%s\n" "${suite_name}"
        done
    ' sh "${skip_suites}" {} + | sort | paste -sd, -
}

if [ -n "${DTR_SUITES:-}" ]; then
    NORMAL_TESTS="${DTR_SUITES}"
else
    PLUGIN_TESTS="${DTR_PLUGIN_SUITES:-$(discover_plugin_suites)}"
    NORMAL_TESTS="${BASE_TESTS}"
    if [ -n "${PLUGIN_TESTS}" ]; then
        NORMAL_TESTS="${NORMAL_TESTS},${PLUGIN_TESTS}"
    fi
fi

export DTR_BUILD_THREAD="${DTR_BUILD_THREAD:-auto}"
export DRIZZLE_DTR_WORKDIR="${ROOT_DIR}"
export DRIZZLE_DTR_SOURCE_DIR="${DRIZZLE_SOURCE_DIR}"
export DRIZZLE_DTR_RUN_ID="${DRIZZLE_DTR_RUN_ID:-${ZUUL_UUID:-$$}}"
export DRIZZLE_DTR_STATE_DIR="${BUILD_ROOT}/podman"

rm -rf "${DRIZZLE_DTR_STATE_DIR}"
mkdir -p "${BUILD_ROOT}/client" "${BUILD_ROOT}/drizzled" "${VARDIR}/drizzle" "${DRIZZLE_DTR_STATE_DIR}/ports"

for name in drizzle drizzledump drizzleimport drizzleslap drizzle_password_hash drizzletest; do
    ln -sf "${WRAPPER}" "${BUILD_ROOT}/client/${name}"
done
ln -sf "${WRAPPER}" "${BUILD_ROOT}/drizzled/drizzled"

cd "${ROOT_DIR}"

DTR_LOG="$(mktemp)"
trap 'rm -f "${DTR_LOG}"' EXIT

DTR_TEST_RUN=(
    "${PERL:-/usr/bin/perl}" -I"${ROOT_DIR}/tests/lib" "${ROOT_DIR}/tests/test-run.pl"
    --top-srcdir="${DRIZZLE_SOURCE_DIR}"
    --top-builddir="${BUILD_ROOT}"
    --vardir="${VARDIR}"
    --reorder
    --suitepath="${ROOT_DIR}/tests/suite"
    --suitepath="${DRIZZLE_SOURCE_DIR}/plugin"
    --testdir="${ROOT_DIR}/tests"
    --drizzled=--mysql-protocol.bind-address=0.0.0.0
    --drizzled=--plugin-remove=drizzle_protocol
)

failed=0

echo "=== DTR startup smoke ==="
"${DTR_TEST_RUN[@]}" --fast --suite=main 1st 2>&1 | tee "${DTR_LOG}"
smoke_exit=${PIPESTATUS[0]}

if [ "${smoke_exit}" -ne 0 ]; then
    echo "run-container-dtr: DTR startup smoke failed" >&2
    failed=1
else
    echo
    echo "=== DTR regression suite ==="
    "${DTR_TEST_RUN[@]}" --fast --force --suite="${NORMAL_TESTS}" 2>&1 | tee -a "${DTR_LOG}"
    dtr_exit=${PIPESTATUS[0]}
    if [ "${dtr_exit}" -ne 0 ]; then
        echo "run-container-dtr: DTR reported failures" >&2
        failed=1
    fi
fi

if grep -q "Server version not detectable" "${DTR_LOG}"; then
    echo "run-container-dtr: server_detect leaked 'version not detectable' through to test output" >&2
    failed=1
fi

if [ "${failed}" -ne 0 ]; then
    exit 1
fi

echo "run-container-dtr: all DTR tests passed"
exit 0
