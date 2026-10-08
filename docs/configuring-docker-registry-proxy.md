<!--
SPDX-FileCopyrightText: 2020 Aaron Raimist
SPDX-FileCopyrightText: 2020 Chris van Dijk
SPDX-FileCopyrightText: 2020 Dominik Zajac
SPDX-FileCopyrightText: 2020 Mickaël Cornière
SPDX-FileCopyrightText: 2020-2024 MDAD project contributors
SPDX-FileCopyrightText: 2020-2024 Slavi Pantaleev
SPDX-FileCopyrightText: 2022 François Darveau
SPDX-FileCopyrightText: 2022 Julian Foad
SPDX-FileCopyrightText: 2022 Warren Bailey
SPDX-FileCopyrightText: 2023 Antonis Christofides
SPDX-FileCopyrightText: 2023 Felix Stupp
SPDX-FileCopyrightText: 2023 Pierre 'McFly' Marty
SPDX-FileCopyrightText: 2024-2026 Suguru Hirahara

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Setting up Docker Registry Proxy

This is an [Ansible](https://www.ansible.com/) role which installs [Docker Registry Proxy](https://github.com/etkecc/docker-registry-proxy) to run as a [Docker](https://www.docker.com/) container wrapped in a systemd service.

Docker Registry Proxy is a pass-through Docker registry (distribution) proxy with metadata caching, Docker-compatible errors, Prometheus metrics, etc.

See the project's [documentation](https://github.com/etkecc/docker-registry-proxy/blob/main/README.md) to learn what Docker Registry Proxy does and why it might be useful to you.

## Adjusting the playbook configuration

To enable Docker Registry Proxy with this role, add the following configuration to your `vars.yml` file.

**Note**: the path should be something like `inventory/host_vars/mash.example.com/vars.yml` if you use the [MASH Ansible playbook](https://github.com/mother-of-all-self-hosting/mash-playbook).

```yaml
########################################################################
#                                                                      #
# docker_registry_proxy                                                #
#                                                                      #
########################################################################

docker_registry_proxy_enabled: true

########################################################################
#                                                                      #
# /docker_registry_proxy                                               #
#                                                                      #
########################################################################
```

### Set the hostname

To enable the Docmost instance you need to set the hostname as well. To do so, add the following configuration to your `vars.yml` file. Make sure to replace `example.com` with your own value.

```yaml
docker_registry_proxy_hostname: "example.com"
```

After adjusting the hostname, make sure to adjust your DNS records to point the domain to your server.

**Note**: hosting Docmost under a subpath (by configuring the `docmost_path_prefix` variable) does not seem to be possible due to Docmost's technical limitations.

### Configuring allowed IP addresses (optional)

It is possible to specify the IP addresses allowed to access the registry (GET, HEAD, OPTIONS requests only) by adding the following configuration to your `vars.yml` file:

```yaml
docker_registry_proxy_allowed_ips: []
```

### Configuring allowed User Agents (optional)

It is also possible to specify the User Agent names allowed to access the registry (GET, HEAD, OPTIONS requests only) by adding the following configuration to your `vars.yml` file (adapt to your needs):

```yaml
docker_registry_proxy_allowed_uas:
  - docker
```

### Configuring trusted IP addresses (optional)

To specify IP addresses trusted to access the registry (PATCH, POST, PUT, DELETE requests only), add the following configuration to your `vars.yml` file:

```yaml
docker_registry_proxy_trusted_ips: []
```

### Extending the configuration

There are some additional things you may wish to configure about the service.

Take a look at:

- [`defaults/main.yml`](../defaults/main.yml) for some variables that you can customize via your `vars.yml` file. You can override settings (even those that don't have dedicated playbook variables) using the `docker_registry_proxy_environment_variables_additional_variables` variable

Refer to [the official documentation](https://github.com/etkecc/docker-registry-proxy/blob/main/README.md) for a complete list of Docker Registry Proxy's config options that you can put in `docker_registry_proxy_environment_variables_additional_variables`.

## Installing

After configuring the playbook, run the installation command of your playbook as below:

```sh
ansible-playbook -i inventory/hosts setup.yml --tags=setup-all,start
```

If you use the MASH playbook, the shortcut commands with the [`just` program](https://github.com/mother-of-all-self-hosting/mash-playbook/blob/main/docs/just.md) are also available: `just install-all` or `just setup-all`

## Usage

After running the command for installation, Docker Registry Proxy becomes available at the specified hostname like `https://example.com`.

## Troubleshooting

### Check the service's logs

You can find the logs in [systemd-journald](https://www.freedesktop.org/software/systemd/man/systemd-journald.service.html) by logging in to the server with SSH and running `journalctl -fu docker-registry-proxy` (or how you/your playbook named the service, e.g. `mash-docker-registry-proxy`).
