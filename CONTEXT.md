# SentinelOps Context

Last updated: 2026-04-09

This file is the quick recovery note for future sessions. It captures what the project is, what changed, and the current working assumptions so we do not have to rebuild the context from scratch.

## What SentinelOps is

SentinelOps is a mini observability platform for small teams. It collects traces and metrics from instrumented Python apps, stores telemetry in ClickHouse, exposes a FastAPI backend for auth and API access, and serves a React dashboard for traces, anomalies, infrastructure, and container views.

## Current repo layout

- `sentinelops-nf`: main product repo, backend, frontend, docker compose, deployment workflows
- `sentinelops-python-sdk`: separate Python SDK repo for instrumentation and metric collection

## Important decisions

- Deployment is now through a VM/Droplet workflow over SSH, not DigitalOcean App Platform.
- The main deployment workflow is GitHub Actions and runs on push to `main`.
- The local demo account is `demo@sentinelops.local` with password `demo123`.
- Traces and anomalies are tenant-scoped by API key.
- Container metrics require Docker socket access on the target VM.

## Main commits in `sentinelops-nf`

- `5b91fe7` - `feat: add local demo monitoring pipeline`
  - added local demo wiring, container monitoring plumbing, backend endpoint work, and Docker-based demo setup
- `1bada06` - `feat: redesign observability dashboard`
  - replaced the dashboard UI with a more polished layout, better hierarchy, and clearer empty states
- `187d840` - `ci: add automatic DigitalOcean deployment workflow`
  - added the first DigitalOcean App Platform workflow
- `a89c254` - `fix(ci): repair workflow YAML indentation`
  - fixed invalid workflow indentation
- `739c86d` - `fix(ci): harden DigitalOcean workflow prechecks`
  - added explicit secret validation and Node 24 compatibility env
- `fa467f7` - `ci: switch production deploy to VM over SSH`
  - introduced the SSH-based droplet workflow and documented the VM deployment secrets
- `403936d` - `fix(ci): auto-stash vm local changes before pull`
  - made the SSH deploy script tolerate dirty working trees on the VM
- `8a92a7c` - `fix(ci): sync sdk repository on vm before build`
  - attempted to resolve the SDK source on the VM before build
- `e2d7c28` - `fix(ci): harden vm deploy script error handling`
  - added explicit logs and safer shell handling in the deploy script
- `ad7cf1d` - `fix(ci): remove obsolete sdk sync step from vm deploy`
  - removed the old SDK mirror logic from the VM deploy script
- `172474d` - `fix(app): install git in flask image for sdk fetch`
  - allowed the Flask image to install the SDK from a Git repository
- `2dcd2c0` - `fix(app): vendor sdk source for reliable container metrics`
  - vendored the SDK source into this repo so the VM build does not depend on external SDK write access

## SDK repo status

- Local SDK repo was updated with container metrics support and version bump to `0.1.3`.
- The direct push to `NFETUE-Labs/sentinelops-python-sdk` was blocked by repository permissions from this environment.
- To keep the system working, the SDK source was vendored into `sentinelops-nf` under `vendor/sentinelops-sdk-src`.

## Current technical state

- Flask demo app initializes SentinelOps with `SENTINELOPS_API_KEY=demo-api-key`.
- Docker socket is mounted into the demo app container for container monitoring.
- The VM deployment workflow is the active production path.
- The last validated CI/CD run succeeded before the SDK-vendoring follow-up changes.

## Useful files

- [docker-compose.yml](docker-compose.yml)
- [app/Dockerfile](app/Dockerfile)
- [app/main.py](app/main.py)
- [backend/main.py](backend/main.py)
- [.github/workflows/deploy-vm.yml](.github/workflows/deploy-vm.yml)
- [vendor/sentinelops-sdk-src/sentinelops/core.py](vendor/sentinelops-sdk-src/sentinelops/core.py)

## Next things to remember

- If the dashboard shows `traces > 0` but `containers = 0`, verify Docker socket access and the container collection path in the SDK.
- If the VM deploy breaks, check the deploy job logs first, then the Flask image build.
- If we want the SDK to live fully in the separate repo again, we need write access to `NFETUE-Labs/sentinelops-python-sdk`.