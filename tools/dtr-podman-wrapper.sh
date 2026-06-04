#!/bin/bash
# Run DTR's Drizzle executables from the container image.

set -euo pipefail

prog="$(basename "$0")"
image="${DRIZZLE_TEST_IMAGE:-quay.io/drizzle/drizzle}"
workdir="${DRIZZLE_DTR_WORKDIR:-$(pwd)}"
source_dir="${DRIZZLE_DTR_SOURCE_DIR:-}"
run_id="${DRIZZLE_DTR_RUN_ID:-manual}"
state_dir="${DRIZZLE_DTR_STATE_DIR:-${workdir}/.dtr-container-build/podman}"
server_container="${DRIZZLE_DTR_SERVER_CONTAINER:-drizzle-dtr-${run_id}-master}"

exec_drizzle_program() {
    local prog="$1"
    shift

    if [ "${prog}" = "drizzled" ]; then
        candidates=(/usr/sbin/drizzled /usr/local/sbin/drizzled)
    else
        candidates=("/usr/bin/${prog}" "/usr/local/bin/${prog}")
    fi

    for exe in "${candidates[@]}"; do
        if [ -x "${exe}" ]; then
            exec "${exe}" "$@"
        fi
    done

    printf 'dtr-podman-wrapper: could not find %s in container\n' "${prog}" >&2
    exit 127
}

if [ "${DRIZZLE_DTR_IN_CONTAINER:-0}" = "1" ] || ! command -v podman >/dev/null 2>&1; then
    exec_drizzle_program "${prog}" "$@"
fi

container_command=(
    /bin/sh -ec '
        prog="$1"
        shift

        if [ "${prog}" = "drizzled" ]; then
            candidates="/usr/sbin/drizzled /usr/local/sbin/drizzled"
        else
            candidates="/usr/bin/${prog} /usr/local/bin/${prog}"
        fi

        for exe in ${candidates}; do
            if [ -x "${exe}" ]; then
                exec "${exe}" "$@"
            fi
        done

        printf "dtr-podman-wrapper: could not find %s in container\n" "${prog}" >&2
        exit 127
    ' sh
)

podman_mount_args=(
    --volume "${workdir}:${workdir}:rw"
    --workdir "${PWD}"
    --env-host
    --env DRIZZLE_DTR_IN_CONTAINER=1
)

if [ -n "${source_dir}" ] && [ "${source_dir}" != "${workdir}" ] && [ -d "${source_dir}" ]; then
    podman_mount_args+=(--volume "${source_dir}:${source_dir}:ro")
fi

if [ "${prog}" != "drizzled" ]; then
    client_port=""
    next_is_port=0
    for arg in "$@"; do
        if [ "${next_is_port}" = "1" ]; then
            client_port="${arg}"
            next_is_port=0
            continue
        fi
        case "${arg}" in
            --port=*)
                client_port="${arg#--port=}"
                ;;
            --port)
                next_is_port=1
                ;;
        esac
    done
    if [ -n "${client_port}" ] && [ -f "${state_dir}/ports/${client_port}" ]; then
        server_container="$(cat "${state_dir}/ports/${client_port}")"
    fi
    network_args=()
    if podman container exists "${server_container}" >/dev/null 2>&1; then
        network_args=(--network "container:${server_container}")
    fi
    exec podman run --rm \
        "${network_args[@]}" \
        "${podman_mount_args[@]}" \
        "${image}" \
        "${container_command[@]}" "${prog}" "$@"
fi

help_only=0
instance="server-$$"
port_args=()

for arg in "$@"; do
    case "${arg}" in
        --help|--version)
            help_only=1
            ;;
        --pid-file=*)
            pid_file="${arg#--pid-file=}"
            instance="$(basename "${pid_file}" .pid)"
            ;;
        --*.port=*)
            port="${arg##*=}"
            port_args+=(--publish "127.0.0.1:${port}:${port}")
            ;;
    esac
done

if [ "${help_only}" = "1" ]; then
    exec podman run --rm \
        "${podman_mount_args[@]}" \
        "${image}" \
        "${container_command[@]}" "${prog}" "$@"
fi

container="drizzle-dtr-${run_id}-${instance}"

cleanup() {
    for port in "${published_ports[@]}"; do
        rm -f "${state_dir}/ports/${port}"
    done
    podman rm -f "${container}" >/dev/null 2>&1 || true
}

podman rm -f "${container}" >/dev/null 2>&1 || true
mkdir -p "${state_dir}/ports"
published_ports=()
for ((i=0; i<${#port_args[@]}; i++)); do
    if [ "${port_args[$i]}" = "--publish" ]; then
        value="${port_args[$((i + 1))]}"
        port="${value#127.0.0.1:}"
        port="${port%%:*}"
        printf '%s\n' "${container}" > "${state_dir}/ports/${port}"
        published_ports+=("${port}")
    fi
done
trap cleanup INT TERM HUP EXIT

podman run --rm \
    --name "${container}" \
    "${port_args[@]}" \
    "${podman_mount_args[@]}" \
    "${image}" \
    "${container_command[@]}" "${prog}" "$@" &
podman_pid=$!

wait "${podman_pid}"
status=$?
trap - INT TERM HUP EXIT
exit "${status}"
