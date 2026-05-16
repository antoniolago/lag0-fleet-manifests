FROM ghcr.io/openclaw/openclaw:latest

USER root

# Go
ARG GO_VERSION=1.23.6
RUN curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" \
    | tar -C /usr/local -xzf -

# .NET SDK
ARG DOTNET_CHANNEL=9.0
RUN curl -fsSL https://dot.net/v1/dotnet-install.sh \
    | bash -s -- --channel "${DOTNET_CHANNEL}" --install-dir /usr/share/dotnet \
    && ln -s /usr/share/dotnet/dotnet /usr/local/bin/dotnet

# Docker CLI (client only — daemon runs in the DinD sidecar)
ARG DOCKER_VERSION=27.5.1
RUN curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_VERSION}.tgz" \
    | tar -C /usr/local/bin --strip-components=1 -xzf - docker/docker

# Rust (via rustup, installed for the openclaw user)
# Skipped by default — uncomment if needed:
# USER 1000
# RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# Ensure all tools are on PATH
ENV PATH="/usr/local/go/bin:/usr/share/dotnet:${PATH}"
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1
ENV GOPATH="/home/openclaw/go"
ENV PATH="${GOPATH}/bin:${PATH}"

USER 1000
