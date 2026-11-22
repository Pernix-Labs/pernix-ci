#!/usr/bin/env bash
# image-build-push: prepare build inputs + registry login, then publish outputs.
#
# Usage:
#   image-build-push.sh prepare   # validate, compute tag/labels/build-args/cache, docker login (push=true only)
#   image-build-push.sh outputs   # validate digest, write image/tag/digest/ref outputs
#
# All inputs arrive via environment variables (see action.yml). Never `set -x`.
set -euo pipefail

IMAGE_RE='^ghcr\.io/[a-z0-9._-]+(/[a-z0-9._-]+)+$'
SHA_RE='^[0-9a-f]{40}$'
DIGEST_RE='^sha256:[0-9a-f]{64}$'
BUILD_ARG_RE='^[A-Za-z_][A-Za-z0-9_]*='

# SemVer 2.0 (https://semver.org), translated to POSIX ERE.
SEMVER_NUM='(0|[1-9][0-9]*)'
SEMVER_PRE_ID='(0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*)'
SEMVER_BUILD_ID='[0-9a-zA-Z-]+'
SEMVER_RE="^${SEMVER_NUM}\.${SEMVER_NUM}\.${SEMVER_NUM}(-${SEMVER_PRE_ID}(\.${SEMVER_PRE_ID})*)?(\+${SEMVER_BUILD_ID}(\.${SEMVER_BUILD_ID})*)?$"

fail() {
  echo "::error::$*"
  exit 1
}

require() {
  local name="$1" value="$2"
  [[ -n "$value" ]] || fail "input '${name}' is required"
}

# Write a single-line output.
set_output() {
  printf '%s=%s\n' "$1" "$2" >>"$GITHUB_OUTPUT"
}

# Write a multi-line output with a random delimiter.
set_output_multiline() {
  local name="$1" value="$2" delim
  delim="EOF_$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
  {
    printf '%s<<%s\n' "$name" "$delim"
    printf '%s\n' "$value"
    printf '%s\n' "$delim"
  } >>"$GITHUB_OUTPUT"
}

cmd_prepare() {
  local image="${IMAGE:-}" context="${CONTEXT:-}" dockerfile="${DOCKERFILE:-}"
  local sha="${SHA:-}" version="${VERSION:-}" build_args="${BUILD_ARGS:-}"
  local platforms="${PLATFORMS:-}" cache="${CACHE:-}" push="${PUSH:-true}" source_url="${SOURCE_URL:-}"
  local registry_token="${REGISTRY_TOKEN:-}" registry_username="${REGISTRY_USERNAME:-}"

  # --- validate (no side effects before this block completes) ---
  require image "$image"
  [[ "$image" =~ $IMAGE_RE ]] ||
    fail "input 'image' must be a lowercase ghcr.io image without tag (e.g. ghcr.io/pernix-labs/foo), got '${image}'"

  require context "$context"
  [[ -d "$context" ]] || fail "input 'context' must be an existing directory, got '${context}'"

  if [[ -z "$dockerfile" ]]; then
    dockerfile="${context%/}/Dockerfile"
  fi
  [[ -f "$dockerfile" ]] || fail "input 'dockerfile' must be an existing file, got '${dockerfile}'"

  require sha "$sha"
  [[ "$sha" =~ $SHA_RE ]] || fail "input 'sha' must be a 40-char lowercase hex commit sha, got '${sha}'"

  if [[ -n "$version" ]]; then
    [[ "$version" =~ $SEMVER_RE ]] || fail "input 'version' must be empty or SemVer 2.0 (e.g. 1.2.3, 1.2.3-rc.1), got '${version}'"
  fi

  require platforms "$platforms"
  [[ "$platforms" =~ ^[A-Za-z0-9/_.,-]+$ ]] ||
    fail "input 'platforms' must be a comma-separated platform list (e.g. linux/amd64), got '${platforms}'"

  case "$cache" in
    true | false) ;;
    *) fail "input 'cache' must be 'true' or 'false', got '${cache}'" ;;
  esac

  case "$push" in
    true | false) ;;
    *) fail "input 'push' must be 'true' or 'false', got '${push}'" ;;
  esac
  if [[ "$push" == "false" && "$platforms" == *,* ]]; then
    fail "input 'platforms' must be a single platform when 'push' is false (docker load), got '${platforms}'"
  fi

  require source-url "$source_url"
  [[ "$source_url" =~ ^https?://[^[:space:]]+$ ]] || fail "input 'source-url' must be an http(s) URL, got '${source_url}'"

  if [[ "$push" == "true" ]]; then
    require registry-token "$registry_token"
    require registry-username "$registry_username"
  fi

  local user_args="" line
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "${line//[[:space:]]/}" ]] && continue
    [[ "$line" =~ $BUILD_ARG_RE ]] || fail "input 'build-args' line must be KEY=VALUE, got '${line%%=*}'"
    user_args+="${line}"$'\n'
  done <<<"$build_args"

  # --- compute ---
  local tag="sha-${sha}"
  local effective_version="${version:-0.0.0-sha.${sha:0:7}}"
  local image_path="${image#ghcr.io/}"

  local labels
  labels="org.opencontainers.image.revision=${sha}
org.opencontainers.image.version=${effective_version}
org.opencontainers.image.source=${source_url}"

  # BUILD_VERSION / BUILD_COMMIT go last so they override user-supplied values.
  local all_args
  all_args="${user_args}BUILD_VERSION=${effective_version}
BUILD_COMMIT=${sha}"

  local cache_from="" cache_to=""
  if [[ "$cache" == "true" ]]; then
    cache_from="type=gha,scope=${image_path}"
    cache_to="type=gha,mode=max,scope=${image_path}"
  fi

  set_output tag "$tag"
  set_output tags "${image}:${tag}"
  set_output version "$effective_version"
  set_output dockerfile "$dockerfile"
  set_output cache-from "$cache_from"
  set_output cache-to "$cache_to"
  set_output_multiline labels "$labels"
  set_output_multiline build-args "$all_args"

  # --- side effect: registry login (creds persist in ~/.docker/config.json, D12) ---
  if [[ "$push" == "true" ]]; then
    printf '%s' "$registry_token" | docker login ghcr.io --username "$registry_username" --password-stdin >/dev/null ||
      fail "docker login to ghcr.io failed for user '${registry_username}'"
  fi

  echo "Prepared ${image}:${tag} (version ${effective_version}, cache ${cache})"
}

cmd_outputs() {
  local image="${IMAGE:-}" tag="${TAG:-}" digest="${DIGEST:-}" push="${PUSH:-true}"

  require image "$image"
  require tag "$tag"
  # push=false: nothing is in the registry, so digest is the local image id.
  if [[ "$push" == "false" ]]; then
    digest="${IMAGE_ID:-}"
  fi
  [[ "$digest" =~ $DIGEST_RE ]] || fail "build-push did not return a valid digest for ${image}:${tag}, got '${digest}'"

  # push=false: ref is the local tag.
  local ref="${image}@${digest}"
  if [[ "$push" == "false" ]]; then
    ref="${image}:${tag}"
  fi

  set_output image "$image"
  set_output tag "$tag"
  set_output digest "$digest"
  set_output ref "$ref"

  {
    echo "### image-build-push"
    echo ""
    echo "| Field | Value |"
    echo "|---|---|"
    echo "| image | \`${image}\` |"
    echo "| tag | \`${tag}\` |"
    echo "| digest | \`${digest}\` |"
  } >>"${GITHUB_STEP_SUMMARY:-/dev/null}"
}

main() {
  case "${1:-}" in
    prepare) cmd_prepare ;;
    outputs) cmd_outputs ;;
    *) fail "usage: image-build-push.sh prepare|outputs" ;;
  esac
}

main "$@"
