#!/bin/bash
# Run DTR from the test node against the Drizzle container image.

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_ROOT="${DRIZZLE_DTR_BUILD_ROOT:-${ROOT_DIR}/.dtr-container-build}"
VARDIR="${BUILD_ROOT}/tests/var"
WRAPPER="${ROOT_DIR}/tools/dtr-podman-wrapper.sh"
NORMAL_TESTS="${DTR_SUITES:-main,bool_type,cast,ddl_transactions,execute,flush_tables,identifiers,jp,mysql_compatibility,regression,tamil,time_type,uuid_type,microtime_type}"

export DTR_BUILD_THREAD="${DTR_BUILD_THREAD:-auto}"
export DRIZZLE_DTR_WORKDIR="${ROOT_DIR}"
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
    --top-srcdir="${ROOT_DIR}"
    --top-builddir="${BUILD_ROOT}"
    --vardir="${VARDIR}"
    --reorder
    --suitepath="${ROOT_DIR}/tests/suite"
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
    if [ -d "${VARDIR}/log" ]; then
        echo
        echo "=== ${VARDIR}/log/drizzle-test-run.log ==="
        sed -n '1,240p' "${VARDIR}/log/drizzle-test-run.log" 2>/dev/null || true
        echo
        echo "=== ${VARDIR}/log/master.err ==="
        sed -n '1,240p' "${VARDIR}/log/master.err" 2>/dev/null || true
    fi
    exit 1
fi

echo "run-container-dtr: all DTR tests passed"
exit 0
