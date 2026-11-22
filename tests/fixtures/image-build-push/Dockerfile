# busybox 1.37.0, pinned by index digest.
FROM busybox:1.37.0@sha256:a7dbc319b1438115a207e11930dc4bb3e643dcb3ec0bdd694bb36cd8fad289ec

COPY app.txt /app.txt

# Cache marker. A random value is written once. A cached build reuses this
# layer, so the value stays identical across builds that hit the cache.
RUN cat /proc/sys/kernel/random/uuid > /cache-marker

ARG BUILD_VERSION
ARG BUILD_COMMIT
RUN printf 'BUILD_VERSION=%s\nBUILD_COMMIT=%s\n' "$BUILD_VERSION" "$BUILD_COMMIT" > /build-info
