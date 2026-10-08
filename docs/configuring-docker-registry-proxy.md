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

# Setting up Docker Registry Purger

This is an [Ansible](https://www.ansible.com/) role which installs [Docker Registry Purger](https://github.com/devture/docker-registry-purger) to run as a [Docker](https://www.docker.com/) container wrapped in a systemd service.

Docker Registry Purger is a small tool used for purging a private Docker registry's old tags.

See the project's [documentation](https://github.com/devture/docker-registry-purger/blob/main/README.md) to learn what Docker Registry Purger does and why it might be useful to you.

## Prerequisites

To run a Docker Registry Purger instance it is necessary to prepare a container registry.

If you are looking for an Ansible role for Distribution Registry, you can check out [ansible-role-docker-registry](https://github.com/mother-of-all-self-hosting/ansible-role-docker-registry) maintained by the [Mother-of-All-Self-Hosting (MASH)](https://github.com/mother-of-all-self-hosting) team.

## Adjusting the playbook configuration

To enable Docker Registry Purger with this role, add the following configuration to your `vars.yml` file.

**Note**: the path should be something like `inventory/host_vars/mash.example.com/vars.yml` if you use the [MASH Ansible playbook](https://github.com/mother-of-all-self-hosting/mash-playbook).

```yaml
########################################################################
#                                                                      #
# docker_registry_purger                                               #
#                                                                      #
########################################################################

docker_registry_purger_enabled: true

########################################################################
#                                                                      #
# /docker_registry_purger                                              #
#                                                                      #
########################################################################
```

### Specify a full URL to the container registry

It is also necessary to set a URL to a container registry instance by adding the following configuration to your `vars.yml` file. Make sure to replace `registry.example.com` with your own value.

```yaml
docker_registry_purger_registry_url: "https://registry.example.com"
```

### Configuring the schedule (optional)

By default the service is configured to run `registry-purger.timer` at 06:30 AM on Sunday (UTC). To adjust the schedule, add the following configuration to your `vars.yml` file:

```yaml
docker_registry_purger_schedule: SCHEDULE_IN_SYSTEMD_TIMER_CALENDAR

# Specify the timezone
docker_registry_purger_environment_variables_tz: UTC
```

Refer to [this page](https://www.freedesktop.org/software/systemd/man/latest/systemd.time.html) for details about the timestamps syntax.

### Extending the configuration

There are some additional things you may wish to configure about the service.

Take a look at:

- [`defaults/main.yml`](../defaults/main.yml) for some variables that you can customize via your `vars.yml` file. You can override settings (even those that don't have dedicated playbook variables) using the `docker_registry_purger_environment_variables_additional_variables` variable

Refer to [the official documentation](https://github.com/devture/docker-registry-purger/blob/main/README.md#environment-variables) for a complete list of Docker Registry Purger's config options that you can put in `docker_registry_purger_environment_variables_additional_variables`.

## Installing

After configuring the playbook, run the installation command of your playbook as below:

```sh
ansible-playbook -i inventory/hosts setup.yml --tags=setup-all,start
```

If you use the MASH playbook, the shortcut commands with the [`just` program](https://github.com/mother-of-all-self-hosting/mash-playbook/blob/main/docs/just.md) are also available: `just install-all` or `just setup-all`

## Usage

After running the command for installation, Docker Registry Purger becomes available, and runs per the schedule to purge registry's old tags.

## Troubleshooting

### Check the service's logs

You can find the logs in [systemd-journald](https://www.freedesktop.org/software/systemd/man/systemd-journald.service.html) by logging in to the server with SSH and running `journalctl -fu docker-registry-purger` (or how you/your playbook named the service, e.g. `mash-docker-registry-purger`).
