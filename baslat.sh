#!/usr/bin/env bash
# Parça Atölyesi'ni başlatır (Linux, denenmedi): http://127.0.0.1:8731
exec bash "$(cd "$(dirname "$0")" && pwd)/kurulum/kur.sh" baslat
