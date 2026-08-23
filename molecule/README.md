<!--
SPDX-FileCopyrightText: 2018-2025 Slavi Pantaleev
SPDX-FileCopyrightText: 2019-2022 Aaron Raimist
SPDX-FileCopyrightText: 2019-2023 MDAD project contributors
SPDX-FileCopyrightText: 2023 QEDeD
SPDX-FileCopyrightText: 2024 Fabio Bonelli
SPDX-FileCopyrightText: 2024 Nikita Chernyi
SPDX-FileCopyrightText: 2024-2026 Suguru Hirahara
SPDX-FileCopyrightText: 2026 Slavi Pantaleev

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Molecule Testing

This role supports [Molecule](https://docs.ansible.com/projects/molecule/), an Ansible testing framework designed for developing and testing Ansible collections, playbooks, and roles.

## Prerequisites

To utilize Molecule you need to prepare several requirements:

- **x86** computer running one of these operating systems that make use of [systemd](https://systemd.io/):
  - **Archlinux**
  - **CentOS**, **Rocky Linux**, **AlmaLinux**, or possibly other RHEL alternatives (although your mileage may vary)
  - **Debian** (10/Buster or newer)
  - **Ubuntu** (18.04 or newer, although [20.04 may be problematic](https://github.com/mother-of-all-self-hosting/mash-playbook/blob/main/docs/ansible.md#supported-ansible-versions) if you run the Ansible playbook on it)
- `root` access on the computer which Molecule runs against
- [Ansible](http://ansible.com/) program
- [Python](https://www.python.org/)
  - Most distributions install Python by default, but some don't (e.g. Ubuntu 18.04) and require manual installation (something like `apt-get install python3`)
- [Docker](https://www.docker.com)
  - Access to Docker UNIX socket (`/var/run/docker.sock`) is required by default

## Installation

To set up the environment for using Molecule, run the command below on the terminal:

```bash
python3 -m venv ./molecule/venv
source ./molecule/venv/bin/activate
pip3 install -r ./molecule/requirements.txt
```

## Scenarios

Currently these testing scenarios are available:

### `default`

Tests a standard Docker Registry Proxy installation.

Docker Registry Proxy is a pass-through proxy, so a registry has to be behind it for there to be anything to test. The scenario runs one of its own on a network of its own, which the role's container is attached to via `docker_registry_proxy_container_additional_networks_custom`, and seeds a small but genuine container image straight into it. Nothing here talks to Docker Hub or to any other registry on the internet.

Before the role runs, the scenario records that the host has no proxy, and then runs the stock container image with no configuration at all as a negative control. That control is put through the very same battery of requests as the role's container, and turns away every one of them — 402 to every read, even from the address the role later admits, and 403 to every write — so nothing that gets through further down can be mistaken for something the image does by itself.

It then checks that the systemd service is active, that the proxy answers `/_health` on `docker_registry_proxy_port` (deliberately set to something other than the image's own default, which the control still listens on), and that the seeded image comes back through the proxy with every digest matching what was seeded. A repository the upstream does not have answers `404 NAME_UNKNOWN` through the proxy, which a proxy that made its answers up could not produce. A blob written through the proxy from a trusted address is then read back directly from the upstream registry, and the upload location the proxy handed out is checked to point at the proxy rather than at the backend it hides.

The role's admission rules are checked from both sides: a client in `docker_registry_proxy_allowed_ips` gets in whatever its user agent, one carrying a user agent in `docker_registry_proxy_allowed_uas` gets in whatever its address, one in neither list is refused with `402`, and a client allowed to read is still refused with `403` when it tries to write. The `/metrics` endpoint refuses an unauthenticated request and, with `docker_registry_proxy_metrics_login` and `docker_registry_proxy_metrics_password`, reports the very refusals and admissions asserted on above.

Finally, the role is installed twice, with `docker_registry_proxy_cache_disabled` off and then on, to show that the setting reaches the running process: the same request answers `MISS` and then `HIT` while caching is on, and carries no `X-Cache` header at all once it is off — while still being served from the upstream either way. The running version is compared against `docker_registry_proxy_version` via the container image's `org.opencontainers.image.version` label, which is the honest surface here: the binary has no `--version` (an unrecognized argument simply starts the server) and the image has no shell to run one with.

## Running

By default it is configured to run the scenarios on Ubuntu 26.04.

```bash
molecule test --scenario-name default
```

You can utilize other distributions by setting one to the `MOLECULE_DISTRO` environment variable:

```bash
# Ubuntu 24.04
MOLECULE_DISTRO=ubuntu2404 molecule test --scenario-name default

# Debian 13
MOLECULE_DISTRO=debian13 molecule test --scenario-name default

# Debian 12
MOLECULE_DISTRO=debian12 molecule test --scenario-name default
```
