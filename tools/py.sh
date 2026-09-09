#!/bin/bash
# Run a Python script via WSL (no native Python on this Windows box). Converts Windows/MSYS paths in args to /mnt/c/...
args=(); for a in "$@"; do
  case "$a" in
    /c/*) a="/mnt/c/${a#/c/}";;
    [A-Za-z]:[\/]*) d=${a:0:1}; r=${a:3}; a="/mnt/${d,,}/${r//\//}";;
  esac; args+=("$a"); done
MSYS_NO_PATHCONV=1 exec wsl python3 "${args[@]}"
