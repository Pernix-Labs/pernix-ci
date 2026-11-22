# Secret fixture (design D9). The secret-pattern string (GitHub PAT format,
# <prefix>_<36 alnum>) is assembled at build time from build-arg fragments the
# self-test generates. The repo holds no literal that matches the pattern.
# The value is a random, non-functional test string.
FROM busybox:1.37.0@sha256:a7dbc319b1438115a207e11930dc4bb3e643dcb3ec0bdd694bb36cd8fad289ec

ARG SECRET_PREFIX
ARG SECRET_BODY
RUN test -n "$SECRET_PREFIX" && test -n "$SECRET_BODY" && \
    mkdir -p /app && \
    printf 'GITHUB_TOKEN=%s_%s\n' "$SECRET_PREFIX" "$SECRET_BODY" > /app/config.env
