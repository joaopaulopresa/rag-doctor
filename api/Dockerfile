# syntax=docker/dockerfile:1.7
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app

# ragbench is installed from its (private) repository over SSH. The key is a build secret:
# it is mounted for this step only and never stored in a layer. GitHub's host key is pinned.
COPY pyproject.toml uv.lock ./
RUN --mount=type=secret,id=ragbench_ssh_key,target=/run/secrets/ragbench_ssh_key \
    mkdir -p /root/.ssh \
    && echo "github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl" > /root/.ssh/known_hosts \
    && GIT_SSH_COMMAND="ssh -i /run/secrets/ragbench_ssh_key -o IdentitiesOnly=yes" \
       uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

EXPOSE 8000
CMD ["uvicorn", "ragdoctor.main:app", "--host", "0.0.0.0", "--port", "8000"]
