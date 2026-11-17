#!/usr/bin/env bash
set -Eeuo pipefail

AK_ACCOUNT_VERSION="2.0.0"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ -r "$SCRIPT_DIR/common.sh" ]]; then
    . "$SCRIPT_DIR/common.sh"
elif [[ -r "/root/hxsy/common.sh" ]]; then
    . "/root/hxsy/common.sh"
else
    echo "ERROR: common.sh not found next to this script." >&2
    exit 1
fi

ak_conf_load
INSTALL_DIR="$SCRIPT_DIR"
[[ -d ${AK_INSTALL_DIR:-} ]] && INSTALL_DIR="$AK_INSTALL_DIR"

DB_USER="postgres"
DB_MEMBER="FFMember"
DB_ACCOUNT="FFAccount"
DB_PASS=""
PG_MODE="peer"
LOG_FILE="/tmp/ak-account.log"

BATCH_USER=""
BATCH_PASS=""
BATCH_PVALUES=""

usage() {
    cat <<EOF
Aura Kingdom account manager ${AK_ACCOUNT_VERSION}

Usage: ./account_creator.sh [options]

  --user=NAME       Create this account without prompting
  --pass=PASSWORD   Password for --user
  --pvalues=N       Starting point balance (default 0)
  --lang=CODE       en de ru fr zh ko ja pt pt_BR tr
  --help            Show this text
EOF
}

for arg in "$@"; do
    case "$arg" in
        --user=*)    BATCH_USER="${arg#*=}" ;;
        --pass=*)    BATCH_PASS="${arg#*=}" ;;
        --pvalues=*) BATCH_PVALUES="${arg#*=}" ;;
        --lang=*)    ak_set_lang "${arg#*=}" ;;
        --help|-h)   usage; exit 0 ;;
        *)           usage; exit 1 ;;
    esac
done

ak_log_init "$LOG_FILE"

[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "$(t need_root)" >&2; exit 1; }
ak_have psql || { echo "psql not found" >&2; exit 1; }

read_ini_password() {
    local file="$INSTALL_DIR/setup.ini" value
    [[ -r $file ]] || return 1
    value=$(grep -m1 -E '^[[:space:]]*AccountDBPW[[:space:]]*=' "$file" 2>/dev/null | cut -d'=' -f2- | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    [[ -n $value ]] || return 1
    printf '%s' "$value"
}

pq() {
    if [[ $PG_MODE == peer ]]; then
        (cd /tmp && sudo -u "$DB_USER" psql -v ON_ERROR_STOP=1 -tAX "$@")
    else
        PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -U "$DB_USER" -v ON_ERROR_STOP=1 -tAX "$@"
    fi
}

connect() {
    if pq -d "$DB_MEMBER" -c "SELECT 1" >/dev/null 2>&1; then
        return 0
    fi
    PG_MODE="password"
    DB_PASS=$(read_ini_password) || DB_PASS=""
    if [[ -n $DB_PASS ]] && pq -d "$DB_MEMBER" -c "SELECT 1" >/dev/null 2>&1; then
        return 0
    fi
    ui_warn "$(t acc_dbpass_missing "$INSTALL_DIR/setup.ini")"
    while :; do
        ak_read DB_PASS "  $(t acc_dbpass_q "$DB_USER"): " silent || exit 1
        [[ -n $DB_PASS ]] || continue
        pq -d "$DB_MEMBER" -c "SELECT 1" >/dev/null 2>&1 && return 0
        ui_err "$(t acc_db_error "$LOG_FILE")"
    done
}

account_exists() {
    [[ $(pq -d "$DB_MEMBER" -c "SELECT 1 FROM tb_user WHERE mid = '$(ak_sql_escape "$1")' LIMIT 1;" 2>/dev/null) == "1" ]]
}

ask_username() {
    local __var="$1" name
    while :; do
        ak_read name "  $(t acc_user_q): " || exit 1
        if [[ ! $name =~ ^[a-z0-9]{3,16}$ ]]; then
            ui_warn "$(t acc_user_bad)"
            continue
        fi
        if account_exists "$name"; then
            ui_warn "$(t acc_user_taken "$name")"
            continue
        fi
        printf -v "$__var" '%s' "$name"
        return 0
    done
}

ask_password() {
    local __var="$1" pass confirm
    while :; do
        ak_read pass "  $(t acc_pass_q): " silent || exit 1
        if (( ${#pass} < 6 )); then ui_warn "$(t acc_pass_short)"; continue; fi
        ak_read confirm "  $(t acc_pass_q2): " silent || exit 1
        if [[ $pass != "$confirm" ]]; then ui_warn "$(t acc_pass_mismatch)"; continue; fi
        printf -v "$__var" '%s' "$pass"
        return 0
    done
}

create_account() {
    local name="$1" pass="$2" pvalues="$3"
    local u p hash uid
    u=$(ak_sql_escape "$name")
    p=$(ak_sql_escape "$pass")
    hash=$(printf '%s' "$pass" | md5sum | cut -d' ' -f1)

    uid=$(pq -d "$DB_MEMBER" -c "INSERT INTO tb_user (mid, password, pwd, pvalues) VALUES ('$u', '$p', '$hash', $pvalues) RETURNING idnum;" 2>>"$LOG_FILE") || {
        ui_err "$(t acc_db_error "$LOG_FILE")"; return 1; }
    [[ -n $uid ]] || { ui_err "$(t acc_db_error "$LOG_FILE")"; return 1; }

    if ! pq -d "$DB_ACCOUNT" -c "INSERT INTO accounts (id, username, password) VALUES ($uid, '$u', '$p');" >>"$LOG_FILE" 2>&1; then
        pq -d "$DB_MEMBER" -c "DELETE FROM tb_user WHERE idnum = $uid;" >>"$LOG_FILE" 2>&1 || true
        ui_err "$(t acc_db_error "$LOG_FILE")"
        return 1
    fi

    ui_ok "$(t acc_created "$name")"
    return 0
}

change_password() {
    local name pass u p hash
    ak_read name "  $(t acc_user_ask): " || return 1
    if ! account_exists "$name"; then
        ui_warn "$(t acc_not_found "$name")"
        return 1
    fi
    ask_password pass
    u=$(ak_sql_escape "$name")
    p=$(ak_sql_escape "$pass")
    hash=$(printf '%s' "$pass" | md5sum | cut -d' ' -f1)
    pq -d "$DB_MEMBER" -c "UPDATE tb_user SET password = '$p', pwd = '$hash' WHERE mid = '$u';" >>"$LOG_FILE" 2>&1 || {
        ui_err "$(t acc_db_error "$LOG_FILE")"; return 1; }
    pq -d "$DB_ACCOUNT" -c "UPDATE accounts SET password = '$p' WHERE username = '$u';" >>"$LOG_FILE" 2>&1 || true
    ui_ok "$(t acc_updated "$name")"
    return 0
}

set_pvalues() {
    local name value u
    ak_read name "  $(t acc_user_ask): " || return 1
    if ! account_exists "$name"; then
        ui_warn "$(t acc_not_found "$name")"
        return 1
    fi
    while :; do
        ak_read value "  $(t acc_pvalues_ask): " || return 1
        [[ $value =~ ^[0-9]+$ ]] && break
        ui_warn "$(t acc_number_bad)"
    done
    u=$(ak_sql_escape "$name")
    pq -d "$DB_MEMBER" -c "UPDATE tb_user SET pvalues = $value WHERE mid = '$u';" >>"$LOG_FILE" 2>&1 || {
        ui_err "$(t acc_db_error "$LOG_FILE")"; return 1; }
    ui_ok "$(t acc_updated "$name")"
    return 0
}

grant_gm() {
    local name u uid
    ak_read name "  $(t acc_user_ask): " || return 1
    if ! account_exists "$name"; then
        ui_warn "$(t acc_not_found "$name")"
        return 1
    fi
    u=$(ak_sql_escape "$name")
    uid=$(pq -d "$DB_MEMBER" -c "SELECT idnum FROM tb_user WHERE mid = '$u';")
    [[ -n $uid ]] || return 1
    if [[ $(pq -d "$DB_ACCOUNT" -c "SELECT 1 FROM gm_tool_accounts WHERE id = $uid LIMIT 1;") == "1" ]]; then
        pq -d "$DB_ACCOUNT" -c "UPDATE gm_tool_accounts SET privilege = 5 WHERE id = $uid;" >>"$LOG_FILE" 2>&1
    else
        local pass
        pass=$(pq -d "$DB_MEMBER" -c "SELECT password FROM tb_user WHERE idnum = $uid;")
        pq -d "$DB_ACCOUNT" -c "INSERT INTO gm_tool_accounts (id, account_name, password, privilege) VALUES ($uid, '$u', '$(ak_sql_escape "$pass")', 5);" >>"$LOG_FILE" 2>&1
    fi
    ui_ok "$(t acc_updated "$name")"
    ui_plain "${C_GREY}$(t admin_gm_hint)${C_RESET}"
    return 0
}

run_batch() {
    [[ $BATCH_USER =~ ^[a-z0-9]{3,16}$ ]] || { ui_err "$(t acc_user_bad)"; exit 1; }
    (( ${#BATCH_PASS} >= 6 )) || { ui_err "$(t acc_pass_short)"; exit 1; }
    account_exists "$BATCH_USER" && { ui_err "$(t acc_user_taken "$BATCH_USER")"; exit 1; }
    local pv="${BATCH_PVALUES:-0}"
    [[ $pv =~ ^[0-9]+$ ]] || pv=0
    create_account "$BATCH_USER" "$BATCH_PASS" "$pv"
    exit $?
}

ui_banner "$(t acc_title) $AK_ACCOUNT_VERSION" "$INSTALL_DIR"
connect

[[ -n $BATCH_USER ]] && run_batch

while :; do
    choice=""
    ui_menu choice "$(t choose)" "$(t menu_create)" "$(t menu_passwd)" "$(t menu_points)" "$(t menu_gm)"

    case "$choice" in
        1)
            username=""; password=""; pvalues=0
            ask_username username
            ask_password password
            if ui_confirm "$(t acc_pvalues_q)" n; then
                while :; do
                    ak_read pvalues "  $(t acc_pvalues_ask): " || break
                    [[ $pvalues =~ ^[0-9]+$ ]] && break
                    ui_warn "$(t acc_number_bad)"
                done
            fi
            create_account "$username" "$password" "${pvalues:-0}" || true
            ;;
        2) change_password || true ;;
        3) set_pvalues || true ;;
        4) grant_gm || true ;;
    esac

    printf '\n'
    ui_confirm "$(t acc_more_q)" y || break
done

printf '\n'
ui_ok "$(t acc_bye)"
