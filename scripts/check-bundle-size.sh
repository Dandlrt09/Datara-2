#!/usr/bin/env bash
set -euo pipefail

# check-bundle-size.sh
#
# Builds the web frontend with Vite, gzips the initial entry chunk
# (dist/assets/index-*.js), and asserts it is < 50 KB.
#
# Usage:  bash scripts/check-bundle-size.sh
#         npm run check-bundle   (from web/)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_DIR="$ROOT_DIR/web"

echo "=== check-bundle-size ==="
echo "Building web frontend..."

# Build the frontend (quietly)
cd "$WEB_DIR"
npx vite build --logLevel warn 2>&1 | tail -5

# Locate the initial entry chunk
INDEX_JS=$(find "$WEB_DIR/dist/assets" -name 'index-*.js' -type f | head -1)

if [ -z "$INDEX_JS" ]; then
    echo "ERROR: No index-*.js found in dist/assets/"
    exit 1
fi

# Gzip and measure
RAW_SIZE=$(wc -c < "$INDEX_JS" | tr -d ' ')
GZ_SIZE=$(gzip -c "$INDEX_JS" | wc -c | tr -d ' ')
LIMIT=$((50 * 1024))  # 50 KB

echo "Raw size:  $RAW_SIZE bytes ($(( RAW_SIZE / 1024 )) KB)"
echo "Gzip size: $GZ_SIZE bytes ($(( GZ_SIZE / 1024 )) KB)"
echo "Limit:     $LIMIT bytes (50 KB)"

if [ "$GZ_SIZE" -gt "$LIMIT" ]; then
    echo "FAIL: Bundle size $GZ_SIZE bytes exceeds ${LIMIT} bytes limit!"
    exit 1
fi

echo "PASS: Bundle size $GZ_SIZE bytes is under ${LIMIT} bytes limit."