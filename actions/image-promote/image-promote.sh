#!/usr/bin/env bash
# image-promote: add tags to an existing GHCR manifest by raw OCI manifest copy (no rebuild, no layer transfer).
# Env: IMAGE, SOURCE_TAG, TAGS (newline list), ALLOW_OVERWRITE, REGISTRY_TOKEN, REGISTRY_USERNAME.
# Writes digest/tags to $GITHUB_OUTPUT.
set -euo pipefail

IMAGE="${IMAGE:-}"
SOURCE_TAG="${SOURCE_TAG:-}"
TAGS="${TAGS:-}"
ALLOW_OVERWRITE="${ALLOW_OVERWRITE:-false}"
REGISTRY_TOKEN="${REGISTRY_TOKEN:-}"
REGISTRY_USERNAME="${REGISTRY_USERNAME:-}"
GITHUB_OUTPUT="${GITHUB_OUTPUT:-/dev/stdout}"

readonly IMAGE_RE='^ghcr\.io/[a-z0-9._-]+(/[a-z0-9._-]+)+$'
readonly TAG_RE='^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$'
readonly DIGEST_RE='^sha256:[0-9a-f]{64}$'
readonly ACCEPT='application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json'

fail() {
  echo "::error::image-promote: $*"
  exit 1
}

# --- validate (before any network call) ---
[[ -n "$IMAGE" ]] || fail "input 'image' is required"
[[ "$IMAGE" =~ $IMAGE_RE ]] || fail "input 'image' must match ${IMAGE_RE} (lowercase ghcr.io/<owner>/<name>, no tag), got '${IMAGE}'"
[[ -n "$SOURCE_TAG" ]] || fail "input 'source-tag' is required"
[[ "$SOURCE_TAG" =~ $TAG_RE ]] || fail "input 'source-tag' is not a valid OCI tag: '${SOURCE_TAG}'"
case "$ALLOW_OVERWRITE" in
  true | false) ;;
  *) fail "input 'allow-overwrite' must be 'true' or 'false', got '${ALLOW_OVERWRITE}'" ;;
esac
[[ -n "$REGISTRY_TOKEN" ]] || fail "input 'registry-token' is required"
[[ -n "$REGISTRY_USERNAME" ]] || fail "input 'registry-username' is required"

targets=()
while IFS= read -r line || [[ -n "$line" ]]; do
  tag="${line//$'\r'/}"
  tag="${tag#"${tag%%[![:space:]]*}"}"
  tag="${tag%"${tag##*[![:space:]]}"}"
  [[ -n "$tag" ]] || continue
  [[ "$tag" =~ $TAG_RE ]] || fail "input 'tags' contains an invalid OCI tag: '${tag}'"
  dup=false
  for t in "${targets[@]+"${targets[@]}"}"; do
    [[ "$t" == "$tag" ]] && dup=true
  done
  [[ "$dup" == true ]] || targets+=("$tag")
done <<<"$TAGS"
[[ "${#targets[@]}" -gt 0 ]] || fail "input 'tags' is required (newline list of target tags)"

REPO_PATH="${IMAGE#ghcr.io/}"
REGISTRY="https://ghcr.io/v2/${REPO_PATH}"

WORK="$(mktemp -d "${RUNNER_TEMP:-/tmp}/image-promote.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# Escape a value for a double-quoted curl config string.
curl_quote() {
  local v="${1//\\/\\\\}"
  printf '"%s"' "${v//\"/\\\"}"
}

# curl_once <config> <body-file> <curl args...>: prints HTTP status (000 on transport error).
# Credentials travel in <config> on stdin, never on the command line.
curl_once() {
  local config="$1" body="$2" code
  shift 2
  code="$(printf '%s\n' "$config" | curl -sS -K - -o "$body" -D "$WORK/headers" -w '%{http_code}' "$@")" || code="000"
  printf '%s' "${code:-000}"
}

# with_retry <fn> <args...>: one retry after 5s on 429/5xx.
with_retry() {
  local code
  code="$("$@")"
  if [[ "$code" == 429 || "$code" =~ ^5[0-9][0-9]$ ]]; then
    echo "::warning::image-promote: HTTP ${code}, retrying once in 5s" >&2
    sleep 5
    code="$("$@")"
  fi
  printf '%s' "$code"
}

# header_value <name>: last value of response header <name> from $WORK/headers.
header_value() {
  grep -i "^$1:" "$WORK/headers" | tail -n1 | cut -d: -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | tr -d '\r' || true
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

# --- token exchange (pull,push) ---
code="$(with_retry curl_once "user = $(curl_quote "${REGISTRY_USERNAME}:${REGISTRY_TOKEN}")" "$WORK/token.json" \
  "https://ghcr.io/token?service=ghcr.io&scope=repository:${REPO_PATH}:pull,push")"
[[ "$code" == 200 ]] || fail "token exchange (pull,push) for ${REPO_PATH} returned HTTP ${code}"
BEARER="$(jq -r '.token // empty' "$WORK/token.json" 2>/dev/null || true)"
rm -f "$WORK/token.json"
[[ -n "$BEARER" ]] || fail "token exchange for ${REPO_PATH} returned no token"
echo "::add-mask::${BEARER}"
AUTH="header = $(curl_quote "Authorization: Bearer ${BEARER}")"

# --- GET source manifest (raw bytes, Content-Type, digest) ---
MANIFEST="$WORK/manifest"
code="$(with_retry curl_once "$AUTH" "$MANIFEST" -H "Accept: ${ACCEPT}" "${REGISTRY}/manifests/${SOURCE_TAG}")"
case "$code" in
  200) ;;
  404) fail "source ${IMAGE}:${SOURCE_TAG} not found (HTTP 404); no tags created" ;;
  *) fail "GET source manifest ${IMAGE}:${SOURCE_TAG} returned HTTP ${code}; no tags created" ;;
esac
CONTENT_TYPE="$(header_value content-type)"
[[ -n "$CONTENT_TYPE" ]] || fail "GET source manifest ${IMAGE}:${SOURCE_TAG} returned no Content-Type"
DIGEST="sha256:$(sha256_file "$MANIFEST")"
REMOTE_DIGEST="$(header_value docker-content-digest)"
if [[ -n "$REMOTE_DIGEST" && "$REMOTE_DIGEST" != "$DIGEST" ]]; then
  fail "source manifest bytes hash to ${DIGEST} but registry reports ${REMOTE_DIGEST}"
fi
[[ "$DIGEST" =~ $DIGEST_RE ]] || fail "could not compute source digest"
echo "image-promote: source ${IMAGE}:${SOURCE_TAG} digest=${DIGEST} content-type=${CONTENT_TYPE}"

# head_digest <tag>: sets HEAD_CODE and HEAD_DIGEST for <tag>.
head_digest() {
  HEAD_CODE="$(with_retry curl_once "$AUTH" /dev/null --head -H "Accept: ${ACCEPT}" "${REGISTRY}/manifests/$1")"
  HEAD_DIGEST=""
  if [[ "$HEAD_CODE" == 200 ]]; then
    HEAD_DIGEST="$(header_value docker-content-digest)"
    [[ "$HEAD_DIGEST" =~ $DIGEST_RE ]] || fail "HEAD ${IMAGE}:$1 returned 200 without a valid Docker-Content-Digest"
  fi
}

# --- check every target before the first write ---
to_put=()
conflicts=()
for tag in "${targets[@]}"; do
  head_digest "$tag"
  case "$HEAD_CODE" in
    404) to_put+=("$tag") ;;
    200)
      if [[ "$HEAD_DIGEST" == "$DIGEST" ]]; then
        echo "image-promote: ${IMAGE}:${tag} already at ${DIGEST}, skipping"
      elif [[ "$ALLOW_OVERWRITE" == true ]]; then
        echo "::warning::image-promote: overwriting ${IMAGE}:${tag} (${HEAD_DIGEST} -> ${DIGEST})"
        to_put+=("$tag")
      else
        conflicts+=("${tag}=${HEAD_DIGEST}")
      fi
      ;;
    *) fail "HEAD target ${IMAGE}:${tag} returned HTTP ${HEAD_CODE}; no tags created" ;;
  esac
done
if [[ "${#conflicts[@]}" -gt 0 ]]; then
  fail "target tags exist on a different digest than source ${DIGEST} (set allow-overwrite=true to replace): ${conflicts[*]}; no tags created"
fi

# --- PUT identical bytes ---
for tag in "${to_put[@]+"${to_put[@]}"}"; do
  code="$(with_retry curl_once "$AUTH" "$WORK/put.body" -X PUT -H "Content-Type: ${CONTENT_TYPE}" \
    --data-binary "@${MANIFEST}" "${REGISTRY}/manifests/${tag}")"
  [[ "$code" == 201 || "$code" == 200 ]] || fail "PUT ${IMAGE}:${tag} returned HTTP ${code}: $(head -c 300 "$WORK/put.body")"
  echo "image-promote: tagged ${IMAGE}:${tag}"
done

# --- verify every target resolves to source digest ---
for tag in "${targets[@]}"; do
  head_digest "$tag"
  [[ "$HEAD_CODE" == 200 ]] || fail "verify HEAD ${IMAGE}:${tag} returned HTTP ${HEAD_CODE}"
  [[ "$HEAD_DIGEST" == "$DIGEST" ]] || fail "digest mismatch for ${IMAGE}:${tag}: expected ${DIGEST}, got ${HEAD_DIGEST}"
done

delim="EOF_$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
{
  echo "digest=${DIGEST}"
  echo "tags<<${delim}"
  printf '%s\n' "${targets[@]}"
  echo "${delim}"
} >>"$GITHUB_OUTPUT"

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    echo "### image-promote"
    echo
    echo "Source \`${IMAGE}:${SOURCE_TAG}\` → \`${DIGEST}\`"
    echo
    for tag in "${targets[@]}"; do echo "- \`${IMAGE}:${tag}\`"; done
  } >>"$GITHUB_STEP_SUMMARY"
fi
echo "image-promote: ${#targets[@]} tag(s) at ${DIGEST}"
