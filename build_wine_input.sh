#!/bin/sh
# Build the background input helper used by Background mode on Linux.
# Needs the MinGW-w64 cross compiler (Debian/Ubuntu/Mint: gcc-mingw-w64-x86-64).
set -eu
cd "$(dirname "$0")"
x86_64-w64-mingw32-gcc -O2 -Wall -o e7_wine_input.exe e7_wine_input.c
echo "Built $(pwd)/e7_wine_input.exe"
