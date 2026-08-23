#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Slavi Pantaleev
#
# SPDX-License-Identifier: AGPL-3.0-or-later

# Exercises bin/compute-next-tag.sh against throwaway git repositories.
#
# Usage: bin/test-compute-next-tag.sh
#
# Every scenario creates a repository in a temporary directory, gives it role
# files and a release history, and then replays a series of merges through the
# real script, tagging as it goes just like the autotag workflow does. This
# repository is never touched and no network access is needed.

set -euo pipefail

script_under_test="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/compute-next-tag.sh"

failures=0
workdir=''

cleanup() {
	cd /
	if [ -n "$workdir" ]; then
		rm -rf "$workdir"
		workdir=''
	fi
}

trap cleanup EXIT

# Starts a scenario with a repository at Docker Registry Proxy v1.2.6 which has
# already seen two releases of it (v1.2.6-0 and v1.2.6-1).
#
# The defaults file is deliberately awkward. Everything above the real version
# would be picked up by a looser reading of the file - a Renovate annotation, a
# commented-out version, and a variable whose name merely starts the same way -
# and everything below it is derived from the real version rather than being a
# version of its own. Only the leaf literal may ever decide the tag.
scenario() {
	echo "$1"

	cleanup
	workdir="$(mktemp -d)"

	mkdir -p "$workdir/bin" "$workdir/defaults" "$workdir/meta" "$workdir/tasks" "$workdir/templates"
	cp "$script_under_test" "$workdir/bin/"
	cd "$workdir"

	git init -q -b main .
	git config user.email 'test@example.com'
	git config user.name 'Test'
	git config commit.gpgsign false

	cat > defaults/main.yml <<-'EOF'
		---
		# Superseded, kept around for reference:
		# docker_registry_proxy_version: v9.9.9
		docker_registry_proxy_version_note: v8.8.8

		# renovate: datasource=docker depName=ghcr.io/etkecc/docker-registry-proxy versioning=semver
		docker_registry_proxy_version: v1.2.6

		docker_registry_proxy_container_image_tag: "{{ docker_registry_proxy_version }}"
		docker_registry_proxy_container_image_self_build_repo_version: "{{ docker_registry_proxy_version if docker_registry_proxy_version != 'latest' else 'main' }}"
	EOF

	printf 'placeholder\n' > meta/main.yml
	printf 'placeholder\n' > tasks/main.yml
	printf 'placeholder\n' > templates/env.j2
	printf 'placeholder\n' > README.md

	git add -A
	git commit -qm 'Initial commit'

	local release_number
	for release_number in 0 1; do
		git tag "v1.2.6-$release_number"
	done
}

# Applies a change, commits it, and tags whatever the script says it should be.
# Prints the tag, or nothing when the script decided against a release.
merge() {
	local change="$1" tag

	eval "$change"
	git add -A
	git commit -qm 'Merge'

	tag="$(bin/compute-next-tag.sh 2>/dev/null)"

	if [ -n "$tag" ]; then
		git tag "$tag"
	fi

	printf '%s' "$tag"
}

expect() {
	local description="$1" expected="$2" actual="$3"

	if [ "$actual" = "$expected" ]; then
		printf '  ok   | %s -> %s\n' "$description" "${actual:-no release}"
	else
		printf '  FAIL | %s -> expected %s, got %s\n' "$description" "${expected:-no release}" "${actual:-no release}"
		failures=$((failures + 1))
	fi
}

bump_version="sed -i 's|^docker_registry_proxy_version: v1.2.6|docker_registry_proxy_version: v1.2.7|' defaults/main.yml"
revert_version="sed -i 's|^docker_registry_proxy_version: v1.2.7|docker_registry_proxy_version: v1.2.6|' defaults/main.yml"
edit_task="printf 'a task\n' >> tasks/main.yml"
edit_template="printf 'a line\n' >> templates/env.j2"
edit_meta="printf 'a platform\n' >> meta/main.yml"
edit_readme="printf 'documentation\n' >> README.md"
edit_script="printf '# a comment\n' >> bin/compute-next-tag.sh"
edit_annotation="sed -i 's|versioning=semver|versioning=semver-coerced|' defaults/main.yml"
edit_derived="sed -i 's|docker_registry_proxy_container_image_tag: .*|docker_registry_proxy_container_image_tag: latest|' defaults/main.yml"

# The version the tag is built from must be the leaf literal, never the
# commented-out version, the look-alike variable, the Renovate annotation, or
# any of the variables derived from it.
scenario 'The version is read from the leaf literal alone'
expect 'a task'                v1.2.6-2 "$(merge "$edit_task")"
expect 'the annotation edited' v1.2.6-3 "$(merge "$edit_annotation")"
expect 'a derived variable'    v1.2.6-4 "$(merge "$edit_derived")"

# The two merge orders below apply the same updates and must each end up with
# every update released exactly once, whichever order they arrive in.

scenario 'A version bump merged before other role changes'
expect 'version bump' v1.2.7-0 "$(merge "$bump_version")"
expect 'task edit'    v1.2.7-1 "$(merge "$edit_task")"
expect 'template'     v1.2.7-2 "$(merge "$edit_template")"

scenario 'A version bump merged after other role changes'
expect 'task edit'    v1.2.6-2 "$(merge "$edit_task")"
expect 'version bump' v1.2.7-0 "$(merge "$bump_version")"

scenario 'Commits that do not affect the role'
expect 'README'   ''       "$(merge "$edit_readme")"
expect 'a script' ''       "$(merge "$edit_script")"
expect 'meta'     v1.2.6-2 "$(merge "$edit_meta")"

scenario 'Release numbers past 9'
for release_number in 2 3 4 5 6 7 8 9 10; do
	git tag "v1.2.6-$release_number"
done
expect 'a task' v1.2.6-11 "$(merge "$edit_task")"

scenario 'Reverting to an already released version'
merge "$bump_version" > /dev/null
# The role is now identical to what v1.2.6-1 already published, so there is
# nothing new to release.
expect 'a revert' ''       "$(merge "$revert_version")"

scenario 'Reverting to an already released version, with a change'
merge "$bump_version" > /dev/null
expect 'a revert' v1.2.6-2 "$(merge "$revert_version && $edit_task")"

if [ "$failures" -gt 0 ]; then
	echo >&2 "$failures scenario(s) behaved unexpectedly"
	exit 1
fi

echo 'All scenarios behaved as expected'
