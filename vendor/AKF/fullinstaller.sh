#!/usr/bin/env bash
set -Eeuo pipefail

AK_INSTALLER_VERSION="2.0.0"
AK_MIRRORS=(
    "https://raw.githubusercontent.com/MrDulgan/AKF/b1b5f590edb108347f82e6f951f4521192750e52"
    "https://cdn.jsdelivr.net/gh/MrDulgan/AKF@b1b5f590edb108347f82e6f951f4521192750e52"
)

DB_USER="postgres"
DB_PASS=""
PG_WANTED="13"
PG_VERSION=""
INSTALL_DIR="/root/hxsy"
ARCHIVE_PATH="/root/hxsy.zip"
ARCHIVE_URL=""
MEGA_URL="https://mega.nz/file/z6AyGIaA#1OXGc4amedlwtNvknc-KC9im_B9nh0FeXO1Ns51Fvr0"
LOG_FILE="/var/log/ak-installer.log"
SERVER_IP=""
PUBLIC_IP=""
ADMIN_USER=""
ADMIN_PASS=""
EXPOSE_DB=0
WANT_SERVICE=-1
DOCTOR_MODE=0
REBOOT_REQUIRED=0
DATABASES=(FFAccount FFDB1 FFMember)
MIN_RAM_MB=2048
MIN_DISK_GB=3

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a
export APT_LISTCHANGES_FRONTEND=none
export LC_ALL=C

usage() {
    cat <<EOF
Aura Kingdom Server Installer ${AK_INSTALLER_VERSION}

Usage: ./fullinstaller.sh [options]

  --lang=CODE          en de ru fr zh ko ja pt pt_BR tr
  --ip=ADDRESS         Public address players will connect to
  --dir=PATH           Installation folder (default: /root/hxsy)
  --archive=PATH       Use a local server archive instead of downloading
  --archive-url=URL    Download the server archive from a direct HTTP(S) link
  --pg-version=N       PostgreSQL major version (default: 13)
  --admin-user=NAME    Create the GM account without prompting
  --admin-pass=PASS    Password for --admin-user
  --expose-db          Allow remote PostgreSQL connections
  --service            Install the systemd service
  --no-service         Do not install the systemd service
  --yes                Accept every confirmation
  --non-interactive    Never ask anything (implies --yes)
  --doctor             Only diagnose an existing installation
  --help               Show this text

Examples:
  ./fullinstaller.sh
  ./fullinstaller.sh --lang=tr --ip=203.0.113.10 --yes
  ./fullinstaller.sh --archive=/root/hxsy.zip --non-interactive \\
                     --ip=203.0.113.10 --admin-user=gm --admin-pass=secret123
EOF
}

resolve_common() {
    local here dest url
    here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
    if [[ -r "$here/common.sh" ]]; then
        printf '%s' "$here/common.sh"
        return 0
    fi
    dest="$(mktemp -d)/common.sh"
    for url in "${AK_MIRRORS[@]}"; do
        if command -v curl >/dev/null 2>&1; then
            curl -fsSL --max-time 30 -o "$dest" "$url/common.sh" && break
        elif command -v wget >/dev/null 2>&1; then
            wget -q --timeout=30 -O "$dest" "$url/common.sh" && break
        fi
    done
    [[ -s $dest ]] || return 1
    printf '%s' "$dest"
}

on_error() {
    local line="$1" cmd="$2"
    ak_spin_stop
    ak_log "FATAL line $line: $cmd"
    printf '\n'
    ui_err "$(t fail_title)"
    ui_plain "$(t fail_hint "$LOG_FILE")"
    exit 1
}

die() {
    ak_spin_stop
    ui_err "$1"
    exit 1
}

die_step() {
    ak_spin_stop
    printf '\n'
    ui_err "$(t fail_title)"
    ui_plain "$(t fail_step "$1")"
    [[ -n ${STEP_HINT:-} ]] && ui_warn "$STEP_HINT"
    printf '\n'
    ui_plain "${C_GREY}$(tail -n 15 "$LOG_FILE" 2>/dev/null | sed 's/^/    /')${C_RESET}"
    printf '\n'
    ui_plain "$(t fail_hint "$LOG_FILE")"
    exit 1
}

q() {
    ak_log "run: $*"
    "$@" >>"$LOG_FILE" 2>&1
}

run_step() {
    local label="$1"; shift
    ui_step_start "$label"
    if "$@"; then
        ui_step_end ok
    else
        ui_step_end fail
        die_step "$label"
    fi
}

skip_step() {
    ui_step_start "$1"
    ui_step_end skip "${2:-}"
}

parse_args() {
    local arg
    for arg in "$@"; do
        case "$arg" in
            --lang=*)        AK_FORCE_LANG="${arg#*=}" ;;
            --ip=*)          SERVER_IP="${arg#*=}" ;;
            --dir=*)         INSTALL_DIR="${arg#*=}" ;;
            --archive=*)     ARCHIVE_PATH="${arg#*=}"; ARCHIVE_PROVIDED=1 ;;
            --archive-url=*) ARCHIVE_URL="${arg#*=}" ;;
            --pg-version=*)  PG_WANTED="${arg#*=}" ;;
            --admin-user=*)  ADMIN_USER="${arg#*=}" ;;
            --admin-pass=*)  ADMIN_PASS="${arg#*=}" ;;
            --expose-db)     EXPOSE_DB=1 ;;
            --service)       WANT_SERVICE=1 ;;
            --no-service)    WANT_SERVICE=0 ;;
            --yes|-y)        AK_ASSUME_YES=1 ;;
            --non-interactive) AK_ASSUME_YES=1; NON_INTERACTIVE=1 ;;
            --doctor)        DOCTOR_MODE=1 ;;
            --help|-h)       usage; exit 0 ;;
            *)               usage; die "Unknown option: $arg" ;;
        esac
    done
    [[ $INSTALL_DIR == /* ]] || die "The installation folder must be an absolute path: $INSTALL_DIR"
    while [[ $INSTALL_DIR == */ && ${#INSTALL_DIR} -gt 1 ]]; do
        INSTALL_DIR="${INSTALL_DIR%/}"
    done
    case "$INSTALL_DIR" in
        /|/root|/home|/usr|/var|/etc|/opt|/srv|/boot|/tmp|/bin|/sbin|/lib|/lib64|/dev|/proc|/sys|\
/usr/bin|/usr/sbin|/usr/lib|/usr/lib64|/usr/share|/usr/local|/var/lib|/var/log|/etc/*)
            die "Refusing to use $INSTALL_DIR as the installation folder." ;;
    esac
}

detect_os() {
    [[ -r /etc/os-release ]] || die "$(t no_osrelease)"
    # shellcheck disable=SC1091
    . /etc/os-release
    OS_ID="${ID:-unknown}"
    OS_LIKE="${ID_LIKE:-}"
    OS_NAME="${PRETTY_NAME:-$OS_ID}"
    OS_VER="${VERSION_ID:-0}"
    OS_CODENAME="${VERSION_CODENAME:-${UBUNTU_CODENAME:-}}"

    case "$OS_ID" in
        debian|ubuntu|linuxmint|pop|raspbian|devuan) PKG="apt" ;;
        rocky|almalinux|centos|rhel|fedora)          PKG="dnf" ;;
        *)
            case "$OS_LIKE" in
                *debian*) PKG="apt" ;;
                *rhel*|*fedora*) PKG="dnf" ;;
                *) die "$(t os_unsupported "$OS_NAME")" ;;
            esac
            ;;
    esac
    [[ $PKG == dnf ]] && ! ak_have dnf && PKG="yum"

    if [[ -z $OS_CODENAME && $PKG == apt ]]; then
        OS_CODENAME=$(ak_have lsb_release && lsb_release -cs 2>/dev/null || echo "")
    fi
    OS_FAMILY_UNTESTED=0
    case "$OS_ID" in
        debian|ubuntu|rocky|almalinux|centos) ;;
        *) OS_FAMILY_UNTESTED=1 ;;
    esac
}

pkg_update() {
    case "$PKG" in
        apt) q apt-get update ;;
        dnf) q dnf -y makecache ;;
        yum) q yum -y makecache ;;
    esac
}

pkg_install() {
    case "$PKG" in
        apt) q apt-get -y -o Dpkg::Options::=--force-confold -o Dpkg::Options::=--force-confdef install "$@" ;;
        dnf) q dnf -y install "$@" ;;
        yum) q yum -y install "$@" ;;
    esac
}

pkg_available() {
    case "$PKG" in
        apt) apt-cache policy "$1" 2>/dev/null | grep -q 'Candidate: [^(]' ;;
        dnf) dnf -q list --available "$1" >/dev/null 2>&1 || dnf -q list --installed "$1" >/dev/null 2>&1 ;;
        yum) yum -q list "$1" >/dev/null 2>&1 ;;
    esac
}

fetch() {
    local url="$1" dest="$2"
    if ak_have curl; then
        curl -fL --retry 3 --retry-delay 2 --connect-timeout 15 -C - -o "$dest" "$url" >>"$LOG_FILE" 2>&1
    else
        wget -c -q --tries=3 --timeout=30 -O "$dest" "$url" >>"$LOG_FILE" 2>&1
    fi
}

fetch_repo_file() {
    local name="$1" dest="$2" base
    for base in "${AK_MIRRORS[@]}"; do
        if fetch "$base/$name" "$dest"; then
            [[ -s $dest ]] && return 0
        fi
    done
    return 1
}

psql_as() {
    (cd /tmp && sudo -u "$DB_USER" psql -v ON_ERROR_STOP=1 -q "$@")
}

psql_val() {
    (cd /tmp && sudo -u "$DB_USER" psql -tAX "$@")
}

pg_service() {
    if [[ ${PKG:-apt} == apt ]]; then printf 'postgresql'; else printf 'postgresql-%s' "${PG_VERSION:-13}"; fi
}

elf_class() {
    local b
    b=$(od -An -tu1 -j4 -N1 "$1" 2>/dev/null | tr -d ' ')
    [[ $b == 1 ]] && printf '32' || printf '64'
}

bin_patch() {
    local file="$1" from="$2" to="$3"
    perl -0777 -e '
        my ($f, $s, $r) = @ARGV;
        open(my $in, "<:raw", $f) or die "open: $!";
        local $/; my $data = <$in>; close $in;
        my $sb = pack("H*", $s);
        my $rb = pack("H*", $r);
        die "pattern length mismatch\n" if length($sb) != length($rb);
        my $n = ($data =~ s/\Q$sb\E/$rb/g);
        if ($n > 0) {
            open(my $out, ">:raw", "$f.tmp") or die "write: $!";
            print $out $data; close $out;
            chmod((stat($f))[2] & 07777, "$f.tmp") or die "chmod: $!";
            rename("$f.tmp", $f) or die "rename: $!";
        }
        print "$n\n";
    ' "$file" "$from" "$to"
}

check_root() {
    [[ ${EUID:-$(id -u)} -eq 0 ]] || die "$(t need_root)"
}

check_bash() {
    if (( BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 3) )); then
        die "$(t need_bash "${BASH_VERSION}")"
    fi
}

detect_public_ip() {
    local svc
    for svc in "https://api.ipify.org" "https://ifconfig.me/ip" "https://icanhazip.com"; do
        if ak_have curl; then
            PUBLIC_IP=$(curl -4 -fsS --max-time 6 "$svc" 2>/dev/null | tr -d '[:space:]') || PUBLIC_IP=""
        else
            PUBLIC_IP=$(wget -4 -qO- --timeout=6 "$svc" 2>/dev/null | tr -d '[:space:]') || PUBLIC_IP=""
        fi
        ak_is_ipv4 "$PUBLIC_IP" && return 0
        PUBLIC_IP=""
    done
    return 0
}

preflight() {
    ui_section "$(t preflight_title)"

    local arch kernel ram_mb disk_gb virt target
    arch=$(uname -m)
    kernel=$(uname -r)
    ram_mb=$(( $(grep -m1 MemTotal /proc/meminfo | awk '{print $2}') / 1024 ))

    target="$INSTALL_DIR"
    while [[ ! -d $target && $target == */* ]]; do target="${target%/*}"; done
    [[ -d $target ]] || target="/"
    disk_gb=$(( $(df -Pk "$target" | tail -1 | awk '{print $4}') / 1024 / 1024 ))

    virt=$(systemd-detect-virt 2>/dev/null) || virt=""
    [[ -n $virt ]] || virt="unknown"

    ui_kv "$(t pf_os)" "$OS_NAME"
    ui_kv "$(t pf_kernel)" "$kernel"
    ui_kv "$(t pf_arch)" "$arch"
    ui_kv "$(t pf_ram)" "${ram_mb} MB"
    ui_kv "$(t pf_disk)" "${disk_gb} GB"
    ui_kv "$(t pf_virt)" "$virt"
    printf '\n'

    [[ $arch == x86_64 || $arch == amd64 ]] || die "$(t bad_arch "$arch")"
    (( OS_FAMILY_UNTESTED == 0 )) || ui_warn "$(t os_untested "$OS_NAME")"
    (( disk_gb >= MIN_DISK_GB )) || die "$(t low_disk "$disk_gb" "$MIN_DISK_GB")"

    if ! ak_have curl && ! ak_have wget; then
        pkg_update || true
        pkg_install curl ca-certificates || pkg_install wget ca-certificates || true
    fi

    detect_public_ip
    if [[ -z $PUBLIC_IP ]]; then
        if ! ping -c1 -W3 1.1.1.1 >/dev/null 2>&1; then
            die "$(t no_network)"
        fi
        ui_warn "$(t pf_net): limited"
    else
        ui_ok "$(t pf_net) ($PUBLIC_IP)"
    fi

    if (( ram_mb < MIN_RAM_MB )); then
        ui_warn "$(t low_ram "$ram_mb" "$MIN_RAM_MB")"
        local swap_kb
        swap_kb=$(grep -m1 SwapTotal /proc/meminfo | awk '{print $2}')
        if (( swap_kb < 262144 )) && ui_confirm "$(t swap_offer 2048)" y; then
            create_swap 2048
        fi
    fi
}

create_swap() {
    local mb="$1" file="/swapfile"
    [[ -e $file ]] && file="/swapfile-ak"
    if q fallocate -l "${mb}M" "$file" || q dd if=/dev/zero of="$file" bs=1M count="$mb"; then
        chmod 600 "$file"
        q mkswap "$file" && q swapon "$file" || return 0
        grep -q "^$file" /etc/fstab 2>/dev/null || echo "$file none swap sw 0 0" >>/etc/fstab
        ui_ok "$(t swap_created "$mb")"
    fi
    return 0
}

choose_language() {
    if [[ -n ${AK_FORCE_LANG:-} ]]; then
        ak_set_lang "$AK_FORCE_LANG"
    elif [[ ${NON_INTERACTIVE:-0} -eq 1 ]] || ! ak_interactive; then
        ak_set_lang "$(ak_lang_autodetect)"
    else
        ui_language_menu
    fi
}

choose_ip() {
    if [[ -n $SERVER_IP ]]; then
        ak_is_ipv4 "$SERVER_IP" || die "$(t ip_invalid "$SERVER_IP")"
    else
        if [[ ${NON_INTERACTIVE:-0} -eq 1 ]]; then
            SERVER_IP="${PUBLIC_IP:-$(hostname -I | awk '{print $1}')}"
        else
            ui_section "$(t ip_title)"
            ui_plain "${C_GREY}$(t ip_hint)${C_RESET}"

            local options=() values=() addr choice
            while read -r addr; do
                ak_is_ipv4 "$addr" || continue
                [[ $addr == 127.* ]] && continue
                options+=("$(t ip_local): $addr")
                values+=("$addr")
            done < <(hostname -I | tr ' ' '\n')

            if [[ -n $PUBLIC_IP ]]; then
                local dup=0 v
                for v in "${values[@]}"; do [[ $v == "$PUBLIC_IP" ]] && dup=1; done
                if (( dup == 0 )); then
                    options=("$(t ip_public): $PUBLIC_IP" "${options[@]}")
                    values=("$PUBLIC_IP" "${values[@]}")
                fi
            fi
            options+=("$(t ip_manual)")

            ui_menu choice "$(t ip_prompt)" "${options[@]}"
            if (( choice > ${#values[@]} )); then
                while :; do
                    ak_read SERVER_IP "  $(t ip_ask): " || die "$(t no_tty)"
                    ak_is_ipv4 "$SERVER_IP" && break
                    ui_warn "$(t ip_invalid "$SERVER_IP")"
                done
            else
                SERVER_IP="${values[$((choice - 1))]}"
            fi
        fi
    fi

    ak_is_ipv4 "$SERVER_IP" || die "$(t ip_invalid "$SERVER_IP")"
    ui_ok "$(t sum_ip): $SERVER_IP"
    if ak_is_private_ip "$SERVER_IP" && [[ -n $PUBLIC_IP && $PUBLIC_IP != "$SERVER_IP" ]]; then
        ui_warn "$(t ip_nat_warn "$SERVER_IP" "$PUBLIC_IP")"
    fi
}

choose_install_dir() {
    [[ -d $INSTALL_DIR ]] || return 0
    ui_section "$(t dir_title)"
    ui_warn "$(t dir_exists "$INSTALL_DIR")"
    if [[ ${NON_INTERACTIVE:-0} -eq 1 ]]; then
        local backup="${INSTALL_DIR}-old-$(date +%Y%m%d%H%M%S)"
        mv "$INSTALL_DIR" "$backup"
        ui_ok "$(t dir_renamed "$backup")"
        return 0
    fi
    local choice
    ui_menu choice "$(t choose)" "$(t dir_del)" "$(t dir_ren)" "$(t dir_abort)"
    case "$choice" in
        1) rm -rf "$INSTALL_DIR"; ui_ok "$(t dir_deleted)" ;;
        2) local backup="${INSTALL_DIR}-old-$(date +%Y%m%d%H%M%S)"
           mv "$INSTALL_DIR" "$backup"; ui_ok "$(t dir_renamed "$backup")" ;;
        3) die "$(t aborted)" ;;
    esac
}

detect_installed_pg() {
    local v=""
    if ak_have psql; then
        v=$(psql --version 2>/dev/null | awk '{print $3}' | cut -d. -f1)
    fi
    printf '%s' "$v"
}

choose_pg_version() {
    local installed
    installed=$(detect_installed_pg)
    if [[ -n $installed ]]; then
        if [[ $installed == "$PG_WANTED" ]]; then
            PG_VERSION="$installed"
            PG_ALREADY=1
            ui_ok "$(t pg_found "$installed")"
            return 0
        fi
        ui_section "PostgreSQL"
        ui_warn "$(t pg_mismatch "$installed" "$PG_WANTED")"
        local choice
        if [[ ${NON_INTERACTIVE:-0} -eq 1 ]]; then
            choice=1
        else
            ui_menu choice "$(t choose)" "$(t pg_keep)" "$(t pg_replace "$PG_WANTED")"
        fi
        if [[ $choice == 1 ]]; then
            PG_VERSION="$installed"
            PG_ALREADY=1
            return 0
        fi
        PG_PURGE=1
    fi
    PG_VERSION="$PG_WANTED"
    PG_ALREADY=0
    return 0
}

step_update() { pkg_update; }

step_deps() {
    local required optional p
    if [[ $PKG == apt ]]; then
        required=(ca-certificates curl unzip perl gnupg sudo)
        optional=(wget procps iproute2 lsof net-tools hostname)
    else
        required=(ca-certificates curl unzip perl gnupg2 sudo)
        optional=(wget procps-ng iproute lsof net-tools hostname)
    fi
    pkg_install "${required[@]}" || return 1
    for p in "${optional[@]}"; do
        pkg_install "$p" >/dev/null 2>&1 || ak_log "optional package not installed: $p"
    done
    ak_have perl || return 1
    ak_have unzip || return 1
    return 0
}

step_locale() {
    if [[ $PKG == apt ]]; then
        pkg_install locales || return 1
        local l
        for l in "en_US.UTF-8 UTF-8" "en_US ISO-8859-1"; do
            grep -q "^${l}$" /etc/locale.gen 2>/dev/null && continue
            sed -i "s/^# *${l}$/${l}/" /etc/locale.gen 2>/dev/null || true
        done
        grep -q "^en_US.UTF-8 UTF-8" /etc/locale.gen 2>/dev/null || echo "en_US.UTF-8 UTF-8" >>/etc/locale.gen
        q locale-gen || return 1
    else
        pkg_install glibc-langpack-en || true
        locale -a 2>/dev/null | grep -qi "en_US.utf8" || q localedef -i en_US -f UTF-8 en_US.UTF-8 || true
    fi
    return 0
}

pg_add_repo_apt() {
    local key="/usr/share/keyrings/pgdg-archive-keyring.gpg"
    install -d -m 0755 /usr/share/keyrings
    if [[ ! -s $key ]]; then
        if ak_have curl; then
            curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc 2>>"$LOG_FILE" | gpg --dearmor -o "$key" 2>>"$LOG_FILE" || return 1
        else
            wget -qO- https://www.postgresql.org/media/keys/ACCC4CF8.asc 2>>"$LOG_FILE" | gpg --dearmor -o "$key" 2>>"$LOG_FILE" || return 1
        fi
    fi
    rm -f /etc/apt/sources.list.d/pgdg.list.save /etc/apt/trusted.gpg.d/pgdg.gpg 2>/dev/null || true
    echo "deb [signed-by=$key] https://apt.postgresql.org/pub/repos/apt ${OS_CODENAME}-pgdg main" \
        >/etc/apt/sources.list.d/pgdg.list
    q apt-get update || return 1
    return 0
}

pg_pick_available_apt() {
    local candidates=("$PG_WANTED" 16 15 14 13 17) v
    for v in "${candidates[@]}"; do
        if pkg_available "postgresql-$v"; then
            printf '%s' "$v"
            return 0
        fi
    done
    return 1
}

step_pg_install() {
    if [[ ${PG_PURGE:-0} -eq 1 ]]; then
        case "$PKG" in
            apt) q apt-get -y remove --purge 'postgresql*' || true; q apt-get -y autoremove || true ;;
            dnf|yum) q "$PKG" -y remove 'postgresql*' || true ;;
        esac
    fi

    if [[ $PKG == apt ]]; then
        [[ -n $OS_CODENAME ]] || return 1
        pg_add_repo_apt || return 1
        local chosen
        chosen=$(pg_pick_available_apt) || return 1
        if [[ $chosen != "$PG_WANTED" ]]; then
            PG_FALLBACK_NOTE="$(t pg_unavailable "$PG_WANTED" "$OS_NAME" "$chosen")"
        fi
        PG_VERSION="$chosen"
        pkg_install "postgresql-$PG_VERSION" "postgresql-client-$PG_VERSION" || return 1
        q systemctl enable --now postgresql || true
    else
        local rel="${OS_VER%%.*}"
        pkg_install "https://download.postgresql.org/pub/repos/yum/reporpms/EL-${rel}-x86_64/pgdg-redhat-repo-latest.noarch.rpm" || true
        q "$PKG" -qy module disable postgresql || true
        if ! pkg_available "postgresql${PG_WANTED}-server"; then
            local v
            for v in 16 15 14 13; do
                pkg_available "postgresql${v}-server" && { PG_VERSION="$v"; break; }
            done
            [[ $PG_VERSION == "$PG_WANTED" ]] || PG_FALLBACK_NOTE="$(t pg_unavailable "$PG_WANTED" "$OS_NAME" "$PG_VERSION")"
        fi
        pkg_install "postgresql${PG_VERSION}-server" "postgresql${PG_VERSION}-contrib" || return 1
        [[ -d "/var/lib/pgsql/$PG_VERSION/data/base" ]] || \
            q "/usr/pgsql-$PG_VERSION/bin/postgresql-$PG_VERSION-setup" initdb || return 1
        q systemctl enable --now "postgresql-$PG_VERSION" || return 1
    fi

    ak_have psql || return 1
    return 0
}

step_pg_config() {
    local conf hba
    q systemctl start "$(pg_service)" || true
    conf=$(psql_val -c "SHOW config_file" 2>/dev/null | tr -d ' ') || return 1
    hba=$(psql_val -c "SHOW hba_file" 2>/dev/null | tr -d ' ') || return 1
    [[ -f $conf && -f $hba ]] || return 1

    cp -n "$conf" "$conf.ak-backup" 2>/dev/null || true
    cp -n "$hba" "$hba.ak-backup" 2>/dev/null || true

    if grep -qE "^\s*#?\s*password_encryption" "$conf"; then
        sed -i "s|^\s*#\?\s*password_encryption.*|password_encryption = md5|" "$conf"
    else
        echo "password_encryption = md5" >>"$conf"
    fi

    if (( EXPOSE_DB == 1 )); then
        if grep -qE "^\s*#?\s*listen_addresses" "$conf"; then
            sed -i "s|^\s*#\?\s*listen_addresses.*|listen_addresses = '*'|" "$conf"
        else
            echo "listen_addresses = '*'" >>"$conf"
        fi
        grep -qE "^host\s+all\s+all\s+0\.0\.0\.0/0\s+md5" "$hba" || \
            echo "host    all             all             0.0.0.0/0               md5" >>"$hba"
    else
        if grep -qE "^\s*#?\s*listen_addresses" "$conf"; then
            sed -i "s|^\s*#\?\s*listen_addresses.*|listen_addresses = 'localhost'|" "$conf"
        else
            echo "listen_addresses = 'localhost'" >>"$conf"
        fi
        :
    fi

    sed -i -E 's#^([[:space:]]*host[[:space:]]+all[[:space:]]+all[[:space:]]+127\.0\.0\.1/32[[:space:]]+)[a-z0-9-]+#\1md5#' "$hba"
    sed -i -E 's#^([[:space:]]*host[[:space:]]+all[[:space:]]+all[[:space:]]+::1/128[[:space:]]+)[a-z0-9-]+#\1md5#' "$hba"
    grep -qE "^[[:space:]]*host[[:space:]]+all[[:space:]]+all[[:space:]]+127\.0\.0\.1/32" "$hba" || \
        echo "host    all             all             127.0.0.1/32            md5" >>"$hba"

    q systemctl restart "$(pg_service)" || return 1
    local i
    for i in $(seq 1 20); do
        psql_val -c "SELECT 1" >/dev/null 2>&1 && return 0
        sleep 1
    done
    return 1
}

step_pg_secure() {
    if ak_have openssl; then
        DB_PASS=$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 24)
    else
        DB_PASS=$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)
    fi
    [[ ${#DB_PASS} -ge 16 ]] || return 1
    psql_as -c "ALTER USER \"$DB_USER\" WITH PASSWORD '$(ak_sql_escape "$DB_PASS")';" >>"$LOG_FILE" 2>&1 || return 1
    return 0
}

step_firewall() {
    (( EXPOSE_DB == 0 )) || return 1
    nft list table inet ak_guard >/dev/null || return 1
    return 0
}

download_via_mega() {
    ak_have megadl || pkg_install megatools >>"$LOG_FILE" 2>&1 || true
    ak_have megadl || return 1
    rm -f "$ARCHIVE_PATH"
    q megadl "$MEGA_URL" --path "$ARCHIVE_PATH"
}

step_download() {
    if [[ -s $ARCHIVE_PATH ]]; then
        if unzip -tqq "$ARCHIVE_PATH" >>"$LOG_FILE" 2>&1; then
            DOWNLOAD_NOTE="$(t dl_cached "$ARCHIVE_PATH")"
            return 0
        fi
        rm -f "$ARCHIVE_PATH"
        DOWNLOAD_HINT="$(t dl_bad_archive)"
        [[ ${ARCHIVE_PROVIDED:-0} -eq 1 ]] && return 1
    elif [[ ${ARCHIVE_PROVIDED:-0} -eq 1 ]]; then
        DOWNLOAD_HINT="$ARCHIVE_PATH: not found"
        return 1
    fi

    if [[ -n $ARCHIVE_URL ]]; then
        DOWNLOAD_SOURCE="$ARCHIVE_URL"
        fetch "$ARCHIVE_URL" "$ARCHIVE_PATH" || return 1
    else
        DOWNLOAD_SOURCE="$MEGA_URL"
        download_via_mega || { DOWNLOAD_HINT="$(t dl_mega_note)"; return 1; }
    fi

    [[ -s $ARCHIVE_PATH ]] || return 1
    unzip -tqq "$ARCHIVE_PATH" >>"$LOG_FILE" 2>&1 || {
        rm -f "$ARCHIVE_PATH"
        DOWNLOAD_HINT="$(t dl_bad_archive)"
        return 1
    }
    return 0
}

download_failure_help() {
    printf '\n'
    ui_err "$(t dl_failed)"
    [[ -n ${DOWNLOAD_HINT:-} ]] && ui_warn "$DOWNLOAD_HINT"
    ui_plain "${C_GREY}$(t dl_source): ${DOWNLOAD_SOURCE:-$MEGA_URL}${C_RESET}"
    printf '\n'
    ui_plain "$(t dl_manual "$ARCHIVE_PATH" "$0 --archive=$ARCHIVE_PATH")"
    printf '\n'
}

step_extract() {
    local tmp root
    tmp=$(mktemp -d)
    q unzip -qo "$ARCHIVE_PATH" -d "$tmp" || { rm -rf "$tmp"; return 1; }

    root=$(find "$tmp" -maxdepth 3 -type d -name GatewayServer -print -quit)
    [[ -n $root ]] || { rm -rf "$tmp"; return 1; }
    root=$(dirname "$root")

    mkdir -p "$(dirname "$INSTALL_DIR")"
    rm -rf "$INSTALL_DIR"
    mv "$root" "$INSTALL_DIR" || { rm -rf "$tmp"; return 1; }
    rm -rf "$tmp"

    chown -R root:root "$INSTALL_DIR"
    chmod -R u+rwX,go-rwx "$INSTALL_DIR"
    local s
    for s in "${AK_SERVERS[@]}"; do
        [[ -f "$INSTALL_DIR/$s/$s" ]] && chmod 750 "$INSTALL_DIR/$s/$s"
    done
    return 0
}

step_tools() {
    local f here
    here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
    for f in start stop account_creator.sh common.sh fullinstaller.sh; do
        if [[ -r "$here/$f" && "$here" != "$INSTALL_DIR" ]]; then
            cp -f "$here/$f" "$INSTALL_DIR/$f"
        else
            fetch_repo_file "$f" "$INSTALL_DIR/$f" || return 1
        fi
    done
    chmod 750 "$INSTALL_DIR/start" "$INSTALL_DIR/stop" "$INSTALL_DIR/account_creator.sh" "$INSTALL_DIR/fullinstaller.sh"
    chmod 640 "$INSTALL_DIR/common.sh"
    return 0
}

step_libs() {
    local probe="" s
    for s in "${AK_SERVERS[@]}"; do
        [[ -f "$INSTALL_DIR/$s/$s" ]] && { probe="$INSTALL_DIR/$s/$s"; break; }
    done
    [[ -n $probe ]] || return 1

    if [[ $(elf_class "$probe") == "32" ]]; then
        LIBS_NOTE="$(t libs_32bit)"
        if [[ $PKG == apt ]]; then
            q dpkg --add-architecture i386 || return 1
            q apt-get update || return 1
            pkg_install libc6:i386 libstdc++6:i386 zlib1g:i386 libgcc-s1:i386 || \
                pkg_install libc6:i386 libstdc++6:i386 zlib1g:i386 || return 1
        else
            pkg_install glibc.i686 libstdc++.i686 zlib.i686 || return 1
        fi
    else
        if [[ $PKG == apt ]]; then
            pkg_install libstdc++6 zlib1g || true
        else
            pkg_install libstdc++ zlib || true
        fi
    fi
    return 0
}

step_db_create() {
    local db
    for db in "${DATABASES[@]}"; do
        psql_as -c "DROP DATABASE IF EXISTS \"$db\";" >>"$LOG_FILE" 2>&1 || return 1
        psql_as -c "CREATE DATABASE \"$db\" TEMPLATE template0;" >>"$LOG_FILE" 2>&1 || return 1
    done
    return 0
}

db_has_table() {
    [[ $(psql_val -d "$1" -c "SELECT to_regclass('public.$2') IS NOT NULL;" 2>/dev/null) == "t" ]]
}

REQUIRED_TABLES=(
    "FFMember:tb_user"
    "FFAccount:accounts"
    "FFAccount:worlds"
    "FFAccount:gm_tool_accounts"
    "FFDB1:serverstatus"
    "FFDB1:player_characters"
)

check_required_tables() {
    local entry db table missing=""
    for entry in "${REQUIRED_TABLES[@]}"; do
        db="${entry%%:*}"; table="${entry#*:}"
        db_has_table "$db" "$table" || missing+="$db.$table "
    done
    [[ -z $missing ]] || { MISSING_TABLES="$missing"; return 1; }
    return 0
}

step_db_import() {
    local db file errors
    for db in "${DATABASES[@]}"; do
        file="$INSTALL_DIR/SQL/$db.bak"
        [[ -f $file ]] || { STEP_HINT="$(t pg_dump_missing "$file")"; ak_log "$STEP_HINT"; return 1; }
        sed -e 's/ WITH OIDS//g' -e 's/WITH OIDS;/;/g' "$file" >"/tmp/$db.sql"
        chmod 644 "/tmp/$db.sql"
        ak_log "importing $db"
        (cd /tmp && sudo -u "$DB_USER" psql -q -d "$db" -f "/tmp/$db.sql") >>"$LOG_FILE" 2>&1 || true
        rm -f "/tmp/$db.sql"
    done

    if ! check_required_tables; then
        STEP_HINT="missing tables after import: $MISSING_TABLES"
        ak_log "$STEP_HINT"
        return 1
    fi

    errors=$(grep -c '^ERROR:' "$LOG_FILE" 2>/dev/null || true)
    [[ ${errors:-0} -gt 0 ]] && ak_log "import finished with $errors reported SQL errors (tables verified present)"

    rm -rf "$INSTALL_DIR/SQL"
    return 0
}

step_patch() {
    local ini count o1 o2 o3 target
    while IFS= read -r ini; do
        sed -i "s/xxxxxxxx/$(printf '%s' "$DB_PASS" | sed 's/[\/&]/\\&/g')/g" "$ini" || return 1
        chmod 600 "$ini"
    done < <(find "$INSTALL_DIR" -maxdepth 2 -name 'setup.ini' -type f)

    target="$INSTALL_DIR/MissionServer/MissionServer"
    if [[ -f $target ]]; then
        cp -n "$target" "$target.orig" 2>/dev/null || true
        count=$(bin_patch "$target" "44240c286234" "44240c084940") || return 1
        ak_log "MissionServer patch replacements: $count"
    fi

    IFS='.' read -r o1 o2 o3 _ <<<"$SERVER_IP"
    local ip_hex
    ip_hex=$(printf '%02x%02x%02x' "$o1" "$o2" "$o3")
    for target in "$INSTALL_DIR/WorldServer/WorldServer" "$INSTALL_DIR/ZoneServer/ZoneServer"; do
        [[ -f $target ]] || continue
        cp -n "$target" "$target.orig" 2>/dev/null || true
        count=$(bin_patch "$target" "3dc0a864" "3d$ip_hex") || return 1
        ak_log "$(basename "$target") IP patch replacements: $count"
    done
    return 0
}

step_db_ip() {
    local ip
    ip=$(ak_sql_escape "$SERVER_IP")
    psql_as -d FFAccount -c "UPDATE worlds SET ip = '$ip';" >>"$LOG_FILE" 2>&1 || return 1
    psql_as -d FFDB1 -c "UPDATE serverstatus SET ext_address = '$ip', int_address = '$ip' WHERE name <> 'MissionServer';" >>"$LOG_FILE" 2>&1 || return 1
    psql_as -d FFDB1 -c "UPDATE serverstatus SET ext_address = 'none' WHERE name = 'MissionServer';" >>"$LOG_FILE" 2>&1 || return 1
    return 0
}

step_grub() {
    if grep -q "vsyscall=emulate" /proc/cmdline 2>/dev/null; then
        VSYSCALL_NOTE="$(t vs_active)"
        return 0
    fi
    if [[ ! -f /etc/default/grub ]]; then
        VSYSCALL_NOTE="$(t vs_no_grub)"
        VSYSCALL_MANUAL=1
        return 0
    fi
    cp -n /etc/default/grub /etc/default/grub.ak-backup 2>/dev/null || true
    if ! grep -q "vsyscall=emulate" /etc/default/grub; then
        if grep -q '^GRUB_CMDLINE_LINUX_DEFAULT=' /etc/default/grub; then
            sed -i 's/^\(GRUB_CMDLINE_LINUX_DEFAULT="[^"]*\)"/\1 vsyscall=emulate"/' /etc/default/grub
        elif grep -q '^GRUB_CMDLINE_LINUX=' /etc/default/grub; then
            sed -i 's/^\(GRUB_CMDLINE_LINUX="[^"]*\)"/\1 vsyscall=emulate"/' /etc/default/grub
        else
            echo 'GRUB_CMDLINE_LINUX="vsyscall=emulate"' >>/etc/default/grub
        fi
    fi
    if ak_have update-grub; then
        q update-grub || return 1
    elif ak_have grub2-mkconfig; then
        q grub2-mkconfig -o /boot/grub2/grub.cfg || q grub2-mkconfig -o /boot/efi/EFI/"$OS_ID"/grub.cfg || return 1
    else
        VSYSCALL_NOTE="$(t vs_no_grub)"
        VSYSCALL_MANUAL=1
        return 0
    fi
    REBOOT_REQUIRED=1
    VSYSCALL_NOTE="$(t vs_added)"
    return 0
}

verify_installation() {
    local issues=0 s missing bin

    if systemctl is-active --quiet "$(pg_service)" 2>/dev/null; then
        ui_ok "$(t vf_pg)"
    else
        ui_err "$(t vf_pg)"; issues=$((issues + 1))
    fi

    local ok=1
    if check_required_tables; then
        ui_ok "$(t vf_db)"
    else
        ui_err "$(t vf_db)"
        ui_plain "${C_GREY}    ${MISSING_TABLES:-}${C_RESET}"
        issues=$((issues + 1))
    fi

    ok=1
    for s in "${AK_SERVERS[@]}"; do
        bin="$INSTALL_DIR/$s/$s"
        [[ -x $bin ]] || { ok=0; ak_log "missing or not executable: $bin"; }
    done
    if (( ok == 1 )); then ui_ok "$(t vf_files)"; else ui_err "$(t vf_files)"; issues=$((issues + 1)); fi

    ok=1
    for s in "${AK_SERVERS[@]}"; do
        bin="$INSTALL_DIR/$s/$s"
        [[ -x $bin ]] || continue
        missing=$(ldd "$bin" 2>/dev/null | awk '/not found/{printf "%s ", $1}' || true)
        if [[ -n $missing ]]; then
            ui_warn "$(t libs_missing "$s" "$missing")"
            ok=0
        fi
    done
    if (( ok == 1 )); then ui_ok "$(t vf_libs)"; else issues=$((issues + 1)); fi

    if grep -q "vsyscall=emulate" /proc/cmdline 2>/dev/null; then
        ui_ok "$(t vf_vsyscall)"
    elif (( REBOOT_REQUIRED == 1 )); then
        ui_warn "$(t vs_reboot)"
    else
        ui_warn "${VSYSCALL_NOTE:-$(t vs_no_grub)}"
        issues=$((issues + 1))
    fi

    ok=1
    local port line owner
    for port in "${AK_SERVER_PORTS[@]}"; do
        line=$(ss -ltnpH 2>/dev/null | grep -E "[:.]$port[[:space:]]" || true)
        [[ -n $line ]] || continue
        owner=0
        for s in "${AK_SERVERS[@]}"; do
            [[ $line == *"\"$s\""* ]] && owner=1
        done
        if (( owner == 0 )); then
            ui_warn "$(t vf_port_busy "$port")"
            ok=0
        fi
    done
    if (( ok == 1 )); then ui_ok "$(t vf_ports)"; else issues=$((issues + 1)); fi

    VERIFY_ISSUES=$issues
    return 0
}

create_admin_account() {
    ui_section "$(t admin_title)"
    ui_plain "${C_GREY}$(t admin_hint)${C_RESET}"

    if [[ -z $ADMIN_USER ]]; then
        [[ ${NON_INTERACTIVE:-0} -eq 1 ]] && return 0
        while :; do
            ak_read ADMIN_USER "  $(t acc_user_q): " || return 0
            [[ $ADMIN_USER =~ ^[a-z0-9]{3,16}$ ]] && break
            ui_warn "$(t acc_user_bad)"
        done
    elif [[ ! $ADMIN_USER =~ ^[a-z0-9]{3,16}$ ]]; then
        die "$(t acc_user_bad)"
    fi

    if [[ -z $ADMIN_PASS ]]; then
        local confirm
        while :; do
            ak_read ADMIN_PASS "  $(t acc_pass_q): " silent || return 0
            if (( ${#ADMIN_PASS} < 6 )); then ui_warn "$(t acc_pass_short)"; continue; fi
            ak_read confirm "  $(t acc_pass_q2): " silent || return 0
            [[ $ADMIN_PASS == "$confirm" ]] && break
            ui_warn "$(t acc_pass_mismatch)"
        done
    fi

    local u p uid
    u=$(ak_sql_escape "$ADMIN_USER")
    p=$(ak_sql_escape "$ADMIN_PASS")
    local hash
    hash=$(printf '%s' "$ADMIN_PASS" | md5sum | cut -d' ' -f1)

    if [[ $(psql_val -d FFMember -c "SELECT 1 FROM tb_user WHERE mid = '$u'") == "1" ]]; then
        ui_warn "$(t acc_user_taken "$ADMIN_USER")"
        return 0
    fi

    uid=$(psql_val -d FFMember -c "INSERT INTO tb_user (mid, password, pwd, pvalues) VALUES ('$u', '$p', '$hash', 999999) RETURNING idnum;") || return 1
    [[ -n $uid ]] || return 1
    psql_as -d FFAccount -c "INSERT INTO accounts (id, username, password) VALUES ($uid, '$u', '$p');" >>"$LOG_FILE" 2>&1 || return 1
    psql_as -d FFAccount -c "INSERT INTO gm_tool_accounts (id, account_name, password, privilege) VALUES ($uid, '$u', '$p', 5);" >>"$LOG_FILE" 2>&1 || return 1

    ui_ok "$(t acc_created "$ADMIN_USER")"
    ui_plain "${C_GREY}$(t admin_gm_hint)${C_RESET}"
    ADMIN_CREATED=1
    return 0
}

install_service() {
    cat >/etc/systemd/system/aurakingdom.service <<EOF
[Unit]
Description=Aura Kingdom Server
After=network-online.target $(pg_service).service
Wants=network-online.target
Requires=$(pg_service).service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment=AK_NO_DASHBOARD=1
Environment=AK_MANAGED=1
ExecStart=$INSTALL_DIR/start
ExecStop=$INSTALL_DIR/stop
KillMode=mixed
KillSignal=SIGTERM
Restart=on-failure
RestartSec=15
TimeoutStartSec=300
TimeoutStopSec=180

[Install]
WantedBy=multi-user.target
EOF
    q systemctl daemon-reload || return 1
    q systemctl enable aurakingdom.service || return 1
    ui_ok "$(t svc_installed)"
    ui_plain "${C_GREY}$(t svc_hint)${C_RESET}"
    return 0
}

write_summary_file() {
    local file="$INSTALL_DIR/install-summary.txt"
    umask 077
    {
        printf 'Aura Kingdom Server - installation summary\n'
        printf 'Generated: %s\n\n' "$(date '+%Y-%m-%d %H:%M:%S')"
        printf '%s : %s\n' "$(ak_pad "$(t sum_ip)" "$AK_KV_WIDTH")"      "$SERVER_IP"
        printf '%s : %s\n' "$(ak_pad "$(t sum_pg)" "$AK_KV_WIDTH")"      "$PG_VERSION"
        printf '%s : %s\n' "$(ak_pad "$(t sum_dbuser)" "$AK_KV_WIDTH")"  "$DB_USER"
        printf '%s : %s\n' "$(ak_pad "$(t sum_dbpass)" "$AK_KV_WIDTH")"  "$DB_PASS"
        printf '%s : %s\n' "$(ak_pad "$(t sum_dir)" "$AK_KV_WIDTH")"     "$INSTALL_DIR"
        printf '%s : %s\n' "$(ak_pad "$(t sum_start)" "$AK_KV_WIDTH")"   "$INSTALL_DIR/start"
        printf '%s : %s\n' "$(ak_pad "$(t sum_stop)" "$AK_KV_WIDTH")"    "$INSTALL_DIR/stop"
        printf '%s : %s\n' "$(ak_pad "$(t sum_account)" "$AK_KV_WIDTH")" "$INSTALL_DIR/account_creator.sh"
        printf '%s : %s\n' "$(ak_pad "$(t sum_log)" "$AK_KV_WIDTH")"     "$LOG_FILE"
    } >"$file"
    chmod 600 "$file"
    printf '%s' "$file"
}

print_summary() {
    printf '\n'
    ui_rule
    printf '  %s%s%s\n' "$C_BOLD$C_GREEN" "$(t sum_title)" "$C_RESET"
    ui_rule
    printf '\n'
    ui_kv "$(t sum_ip)" "$SERVER_IP"
    ui_kv "$(t sum_pg)" "$PG_VERSION"
    ui_kv "$(t sum_dbuser)" "$DB_USER"
    ui_kv "$(t sum_dbpass)" "$DB_PASS"
    ui_kv "$(t sum_dir)" "$INSTALL_DIR"
    ui_kv "$(t sum_start)" "$INSTALL_DIR/start"
    ui_kv "$(t sum_stop)" "$INSTALL_DIR/stop"
    ui_kv "$(t sum_account)" "$INSTALL_DIR/account_creator.sh"
    ui_kv "$(t sum_log)" "$LOG_FILE"
    printf '\n'
    ui_plain "${C_GREY}$(t sum_saved "$(write_summary_file)")${C_RESET}"

    ui_section "$(t next_title)"
    local n=1
    if (( REBOOT_REQUIRED == 1 )); then
        ui_plain "  $n. $(t next_reboot)"; n=$((n + 1))
    fi
    ui_plain "  $n. $(t next_start "$INSTALL_DIR/start")"; n=$((n + 1))
    ui_plain "  $n. $(t next_client "$SERVER_IP")"; n=$((n + 1))
    ui_plain "  $n. $(t next_help "$INSTALL_DIR/fullinstaller.sh --doctor")"
    printf '\n'

    [[ -n ${PG_FALLBACK_NOTE:-} ]] && ui_warn "$PG_FALLBACK_NOTE"
    [[ -n ${FIREWALL_NOTE:-} ]] && ui_warn "$FIREWALL_NOTE"
    (( EXPOSE_DB == 1 )) && ui_warn "$(t pg_expose_warn)"
    (( ${VSYSCALL_MANUAL:-0} == 1 )) && ui_warn "$(t vs_no_grub)"
    return 0
}

run_doctor() {
    ak_conf_load
    INSTALL_DIR=$(ak_resolve_install_dir "${AK_INSTALL_DIR:-}")
    [[ -d $INSTALL_DIR ]] || die "$(t not_installed "$INSTALL_DIR")"
    PG_VERSION=$(detect_installed_pg)
    ui_banner "$(t doctor_title)" "$INSTALL_DIR"
    verify_installation
    printf '\n'
    if (( VERIFY_ISSUES == 0 )); then
        ui_ok "$(t doctor_ok)"
    else
        ui_warn "$(t doctor_issues "$VERIFY_ISSUES")"
        ui_plain "${C_GREY}$(t fail_hint "$LOG_FILE")${C_RESET}"
    fi
    printf '\n'
    exit 0
}

main() {
    trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

    check_bash
    parse_args "$@"
    check_root

    touch "$LOG_FILE" 2>/dev/null || LOG_FILE="/tmp/ak-installer.log"
    ak_log_init "$LOG_FILE"
    ak_log "installer $AK_INSTALLER_VERSION, args: $*"

    detect_os
    choose_language

    (( DOCTOR_MODE == 1 )) && run_doctor

    ui_banner "$(t app_name) $AK_INSTALLER_VERSION" "$(t app_by)  ·  github.com/MrDulgan/AKF"

    if [[ ${NON_INTERACTIVE:-0} -eq 0 ]] && ! ak_interactive; then
        die "$(t no_tty)"
    fi

    preflight
    choose_ip
    choose_install_dir
    choose_pg_version

    if [[ ${NON_INTERACTIVE:-0} -eq 0 && $EXPOSE_DB -eq 0 ]]; then
        ui_confirm "$(t pg_expose_q)" n && EXPOSE_DB=1
    fi

    AK_STEP_TOTAL=16
    printf '\n'

    run_step "$(t step_update)"     step_update
    run_step "$(t step_deps)"       step_deps
    run_step "$(t step_locale)"     step_locale

    if [[ ${PG_ALREADY:-0} -eq 1 ]]; then
        skip_step "$(t step_pg_install "$PG_VERSION")" "$(t pg_found "$PG_VERSION")"
    else
        run_step "$(t step_pg_install "$PG_WANTED")" step_pg_install
    fi

    run_step "$(t step_pg_config)"  step_pg_config
    run_step "$(t step_pg_secure)"  step_pg_secure
    run_step "$(t step_firewall)"   step_firewall

    ui_step_start "$(t step_download)"
    if step_download; then
        ui_step_end ok
    else
        ui_step_end fail
        download_failure_help
        die_step "$(t step_download)"
    fi

    run_step "$(t step_extract)"    step_extract
    run_step "$(t step_tools)"      step_tools
    run_step "$(t step_libs)"       step_libs
    run_step "$(t step_db_create)"  step_db_create
    run_step "$(t step_db_import)"  step_db_import
    run_step "$(t step_patch)"      step_patch
    run_step "$(t step_db_ip)"      step_db_ip
    run_step "$(t step_grub)"       step_grub

    ui_section "$(t step_verify)"
    verify_installation

    [[ -n ${DOWNLOAD_NOTE:-} ]] && ui_info "$DOWNLOAD_NOTE"
    [[ -n ${LIBS_NOTE:-} ]] && ui_info "$LIBS_NOTE"
    [[ -n ${VSYSCALL_NOTE:-} ]] && ui_info "$VSYSCALL_NOTE"

    ak_conf_save "$INSTALL_DIR" "$AK_LANG" "$SERVER_IP"

    create_admin_account || ui_warn "$(t acc_db_error "$LOG_FILE")"

    if (( WANT_SERVICE == 1 )); then
        install_service || ui_warn "$(t fail_step "$(t svc_installed)")"
    elif (( WANT_SERVICE == -1 )) && [[ ${NON_INTERACTIVE:-0} -eq 0 ]]; then
        if ui_confirm "$(t svc_q)" n; then
            install_service || ui_warn "$(t fail_step "$(t svc_installed)")"
        fi
    fi

    print_summary

    if (( REBOOT_REQUIRED == 1 )) && [[ ${NON_INTERACTIVE:-0} -eq 0 ]]; then
        if ui_confirm "$(t reboot_q)" n; then
            ak_log "rebooting"
            systemctl reboot
        fi
    fi

    ak_log "installation finished"
    return 0
}

AK_COMMON_FILE="$(resolve_common)" || {
    echo "ERROR: common.sh could not be downloaded. Check your internet connection." >&2
    exit 1
}
# shellcheck source=common.sh
. "$AK_COMMON_FILE"

[[ ${AK_SOURCE_ONLY:-0} == 1 ]] || main "$@"
