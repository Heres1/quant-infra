#!/usr/bin/env bash
# 本机 ClickHouse 启动脚本（brew 官方单二进制版，dev 用）
# 说明：docker hub 在本网络不稳定，docker-compose.yml 保留用于服务器部署；
# 本地开发用原生二进制 + ~/.quant-infra/ch/config.xml（数据与日志都在该目录）。
set -euo pipefail

CONF="$HOME/.quant-infra/ch/config.xml"
BIN="$(command -v clickhouse || echo /opt/homebrew/bin/clickhouse)"

mkdir -p "$HOME/.quant-infra/ch"/{data,logs,tmp,user_files,format_schemas}
[ -f "$CONF" ] || { echo "缺少配置 $CONF"; exit 1; }

if curl -s -m 2 "http://127.0.0.1:8123/?query=SELECT+1" >/dev/null 2>&1; then
    echo "ClickHouse 已在运行"
else
    "$BIN" server --config-file="$CONF" --daemon
    for _ in $(seq 1 20); do
        sleep 1
        if curl -s -m 2 "http://127.0.0.1:8123/?query=SELECT+1" >/dev/null 2>&1; then
            break
        fi
    done
    curl -s -m 2 "http://127.0.0.1:8123/?query=SELECT+version()" && echo
fi

# 幂等应用建表 SQL（IF NOT EXISTS，可重复执行）
clickhouse client --multiquery < "$(dirname "$0")/../scripts/clickhouse/init.sql"
clickhouse client --query "SHOW TABLES FROM qinfra"
