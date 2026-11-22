# Build context: repository root (release-units `context: .`).
# Bases pinned by multi-arch index digest. Bump the runtime-deps digest when
# image-scan reports HIGH/CRITICAL CVEs.
FROM --platform=$BUILDPLATFORM mcr.microsoft.com/dotnet/sdk:10.0-noble@sha256:bef136a371963aaa46ec97882845ef6f54dec15728bb4b128b1c2a400ffbc9b4 AS build
ARG TARGETARCH
WORKDIR /src
COPY global.json Directory.Build.props Directory.Packages.props ./
COPY src/Shared/ src/Shared/
COPY src/Svc/ src/Svc/
RUN case "$TARGETARCH" in \
      amd64) rid=linux-x64 ;; \
      arm64) rid=linux-arm64 ;; \
      *) echo "unsupported TARGETARCH '$TARGETARCH'" >&2; exit 1 ;; \
    esac \
 && dotnet publish src/Svc/Svc.csproj -c Release -r "$rid" --self-contained true -o /out

FROM mcr.microsoft.com/dotnet/runtime-deps:10.0-noble-chiseled@sha256:40eba5db69594d517c3a61e96bdacc2e3d6f8c99a44b52d55edee844d33518d0
ARG BUILD_VERSION
ARG BUILD_COMMIT
LABEL org.opencontainers.image.version=$BUILD_VERSION \
      org.opencontainers.image.revision=$BUILD_COMMIT
ENV BUILD_VERSION=$BUILD_VERSION \
    BUILD_COMMIT=$BUILD_COMMIT
WORKDIR /app
COPY --from=build /out/ ./
COPY deploy/svc.conf /etc/svc/svc.conf
ENTRYPOINT ["/app/Svc"]
