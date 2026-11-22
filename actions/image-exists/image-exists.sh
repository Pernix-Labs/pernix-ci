#!/usr/bin/env bash
# image-exists: report whether <image>:<tag> exists in GHCR without pulling layers.
# Env: IMAGE, TAG, REGISTRY_TOKEN, REGISTRY_USERNAME. Writes exists/digest to $GITHUB_OUTPUT.
set -euo pipefail

IMAGE="${IMAGE:-}"
TAG="${TAG:-}"
REGISTRY_TOKEN="${REGISTRY_TOKEN:-}"
REGISTRY_USERNAME="${REGISTRY_USERNAME:-}"
GITHUB_OUTPUT="${GITHUB_OUTPUT:-/dev/stdout}"

readonly IMAGE_RE='^ghcr\.io/[a-z0-9._-]+(/[a-z0-9._-]+)+$'
readonly TAG_RE='^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$'
readonly DIGEST_RE='^sha256:[0-9a-f]{64}$'
readonly ACCEPT='application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json'

fail() {
  echo "::error::image-exists: $*"
  exit 1
}

# --- validate (before any network call) ---
[[ -n "$IMAGE" ]] || fail "input 'image' is required"
[[ "$IMAGE" =~ $IMAGE_RE ]] || fail "input 'image' must match ${IMAGE_RE} (lowercase ghcr.io/<owner>/<name>, no tag), got '${IMAGE}'"
[[ -n "$TAG" ]] || fail "input 'tag' is required"
[[ "$TAG" =~ $TAG_RE ]] || fail "input 'tag' is not a valid OCI tag: '${TAG}'"
[[ -n "$REGISTRY_TOKEN" ]] || fail "input 'registry-token' is required"
[[ -n "$REGISTRY_USERNAME" ]] || fail "input 'registry-username' is required"

REPO_PATH="${IMAGE#ghcr.io/}"
OWNER="${REPO_PATH%%/*}"
PKG_NAME="${REPO_PATH#*/}"

WORK="$(mktemp -d "${RUNNER_TEMP:-/tmp}/image-exists.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# Escape a value for a double-quoted curl config string.
curl_quote() {
  local v="${1//\\/\\\\}"
  printf '"%s"' "${v//\"/\\\"}"
}

# curl_once <config> <curl args...>: prints HTTP status (000 on transport error).
# Credentials travel in <config> on stdin, never on the command line.
curl_once() {
  local config="$1" code
  shift
  code="$(printf '%s\n' "$config" | curl -sS -K - -o "$WORK/body" -D "$WORK/headers" -w '%{http_code}' "$@")" || code="000"
  printf '%s' "${code:-000}"
}

# api_once <path>: GitHub API GET via gh (GH_TOKEN), prints HTTP status, body in $WORK/api.body.
api_once() {
  gh api -i "$1" >"$WORK/api.out" 2>"$WORK/api.err" || true
  awk 'f{print} /^\r?$/{f=1}' "$WORK/api.out" >"$WORK/api.body"
  local code
  code="$(head -n1 "$WORK/api.out" | awk '{print $2}' | tr -d '\r')"
  printf '%s' "${code:-000}"
}

# with_retry <fn> <args...>: one retry after 5s on 429/5xx.
with_retry() {
  local code
  code="$("$@")"
  if [[ "$code" == 429 || "$code" =~ ^5[0-9][0-9]$ ]]; then
    echo "::warning::image-exists: HTTP ${code}, retrying once in 5s" >&2
    sleep 5
    code="$("$@")"
  fi
  printf '%s' "$code"
}

write_outputs() {
  {
    echo "exists=$1"
    echo "digest=$2"
  } >>"$GITHUB_OUTPUT"
  echo "image-exists: ${IMAGE}:${TAG} exists=$1${2:+ digest=$2}"
}

# D13: 403 from token exchange or manifest HEAD -> confirm via GitHub Packages API.
packages_api_fallback() {
  local stage="$1" code base type enc
  export GH_TOKEN="$REGISTRY_TOKEN"

  code="$(with_retry api_once "users/${OWNER}")"
  [[ "$code" == 200 ]] || fail "registry ${stage} returned 403 for ${IMAGE}:${TAG}; owner lookup GET /users/${OWNER} returned HTTP ${code}: $(head -c 300 "$WORK/api.err")"
  type="$(jq -r '.type // empty' "$WORK/api.body")"
  if [[ "$type" == "Organization" ]]; then base="orgs/${OWNER}"; else base="users/${OWNER}"; fi

  enc="$(jq -rn --arg n "$PKG_NAME" '$n|@uri')"
  code="$(with_retry api_once "${base}/packages/container/${enc}")"
  case "$code" in
    404)
      echo "image-exists: registry ${stage} returned 403, Packages API reports package '${PKG_NAME}' not found"
      write_outputs false ""
      exit 0
      ;;
    200) fail "registry ${stage} returned 403 for ${IMAGE}:${TAG}, but package '${PKG_NAME}' exists (Packages API 200): token lacks access" ;;
    *) fail "registry ${stage} returned 403 for ${IMAGE}:${TAG}; Packages API GET /${base}/packages/container/${enc} returned HTTP ${code}" ;;
  esac
}

# --- token exchange ---
code="$(with_retry curl_once "user = $(curl_quote "${REGISTRY_USERNAME}:${REGISTRY_TOKEN}")" \
  "https://ghcr.io/token?service=ghcr.io&scope=repository:${REPO_PATH}:pull")"
case "$code" in
  200) ;;
  403) packages_api_fallback "token exchange" ;;
  *) fail "token exchange for ${REPO_PATH} returned HTTP ${code}" ;;
esac
BEARER="$(jq -r '.token // empty' "$WORK/body" 2>/dev/null || true)"
[[ -n "$BEARER" ]] || fail "token exchange for ${REPO_PATH} returned no token"
echo "::add-mask::${BEARER}"
: >"$WORK/body"

# --- manifest HEAD ---
code="$(with_retry curl_once "header = $(curl_quote "Authorization: Bearer ${BEARER}")" \
  --head -H "Accept: ${ACCEPT}" "https://ghcr.io/v2/${REPO_PATH}/manifests/${TAG}")"
case "$code" in
  200)
    digest="$(grep -i '^docker-content-digest:' "$WORK/headers" | tail -n1 | cut -d: -f2- | tr -d ' \r')"
    [[ "$digest" =~ $DIGEST_RE ]] || fail "manifest HEAD for ${IMAGE}:${TAG} returned 200 without a valid Docker-Content-Digest"
    write_outputs true "$digest"
    ;;
  404) write_outputs false "" ;;
  403) packages_api_fallback "manifest HEAD" ;;
  *) fail "manifest HEAD for ${IMAGE}:${TAG} returned HTTP ${code}" ;;
esac
