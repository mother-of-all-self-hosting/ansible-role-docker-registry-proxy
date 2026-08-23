# SPDX-FileCopyrightText: 2026 Slavi Pantaleev
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Seeds a registry, then exercises a Docker Registry Proxy in front of it.

Usage: probe-registry-proxy.py seed  <config JSON path>
       probe-registry-proxy.py probe <config JSON path>

Both modes print a JSON report of what was answered at every step, so that the
Molecule verifier can assert on it rather than on this script's exit code. A
refusal is a result to report, not a crash: which requests the proxy turns away
is exactly what the verifier wants to know.

`seed` pushes a tiny but genuine container image straight into the upstream
registry, bypassing the proxy, and reports the digests it pushed. `probe` then
asks the proxy for that same image and re-hashes everything that comes back, so
a proxy that hands over the wrong bytes cannot pass.

The image is pushed over the registry HTTP API rather than with `docker push`,
so that the media type is pinned rather than being whatever the Docker version
the test happens to run against would produce. This part is adapted from the
`ansible-role-docker-registry` role's `roundtrip-registry.py`.

Everything the proxy serves comes from a registry container on the scenario's
own network. Nothing here talks to Docker Hub or to any other registry on the
internet.

On the client IP the proxy sees: Docker Registry Proxy extracts it from the
`X-Forwarded-For` header whenever the peer is on a loopback, link-local or
private network - which is how it runs in production, behind Traefik. Sending
that header is therefore not a trick to get around anything; it is what lets
this script choose which client the proxy believes it is talking to, and so
exercise `docker_registry_proxy_allowed_ips` and friends with fixed,
documentation-range addresses instead of whatever the Docker bridge happens to
number its gateway.
"""

import base64
import gzip
import hashlib
import io
import json
import sys
import tarfile
import urllib.error
import urllib.request

MANIFEST_MEDIA_TYPE = "application/vnd.docker.distribution.manifest.v2+json"

mode, config_path = sys.argv[1], sys.argv[2]

with open(config_path) as config_file:
    config = json.load(config_file)


def request(base_url, path, method="GET", body=None, content_type=None,
            accept=None, forwarded_for=None, user_agent=None, authorization=None):
    # An upload location handed back by a registry may be absolute or relative.
    url = path if path.startswith("http") else base_url + path

    http_request = urllib.request.Request(url, data=body, method=method)
    if content_type is not None:
        http_request.add_header("Content-Type", content_type)
    if accept is not None:
        http_request.add_header("Accept", accept)
    if forwarded_for is not None:
        http_request.add_header("X-Forwarded-For", forwarded_for)
    if user_agent is not None:
        http_request.add_header("User-Agent", user_agent)
    if authorization is not None:
        http_request.add_header("Authorization", authorization)

    try:
        response = urllib.request.urlopen(http_request)
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()
    except urllib.error.URLError as error:
        # Nothing listening, or a refused connection. Reported rather than
        # raised, so that the verifier sees it as a result.
        return 0, {}, str(error.reason).encode()

    with response:
        return response.status, dict(response.headers), response.read()


def digest_of(blob):
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def error_code_of(body):
    """Pulls the Docker-style error code out of a refusal body, if there is one."""
    try:
        return json.loads(body)["errors"][0]["code"]
    except (ValueError, KeyError, IndexError, TypeError):
        return None


def seed():
    """Pushes a genuine container image directly into the upstream registry."""
    upstream_url = config["upstream_url"]
    repository = config["repository"]

    def push_blob(blob):
        status, headers, _ = request(upstream_url, "/v2/%s/blobs/uploads/" % repository, "POST")
        if status != 202:
            raise SystemExit("starting a blob upload answered %d" % status)

        location = headers["Location"]
        separator = "&" if "?" in location else "?"
        status, _, _ = request(
            upstream_url,
            location + separator + "digest=" + digest_of(blob),
            "PUT",
            body=blob,
            content_type="application/octet-stream",
        )
        if status != 201:
            raise SystemExit("completing a blob upload answered %d" % status)

        return digest_of(blob)

    # A real (if minuscule) layer, so that what the proxy passes through is a
    # genuine container image rather than a blob the registry happens to hold.
    marker = ("%s:%s\n" % (repository, config["tag"])).encode()

    layer_tar = io.BytesIO()
    with tarfile.open(fileobj=layer_tar, mode="w") as archive:
        entry = tarfile.TarInfo("marker")
        entry.size = len(marker)
        archive.addfile(entry, io.BytesIO(marker))
    layer = gzip.compress(layer_tar.getvalue(), mtime=0)

    image_config = json.dumps({
        "architecture": "amd64",
        "os": "linux",
        "config": {},
        "rootfs": {"type": "layers", "diff_ids": [digest_of(layer_tar.getvalue())]},
    }).encode()

    config_digest = push_blob(image_config)
    layer_digest = push_blob(layer)

    manifest = json.dumps({
        "schemaVersion": 2,
        "mediaType": MANIFEST_MEDIA_TYPE,
        "config": {
            "mediaType": "application/vnd.docker.container.image.v1+json",
            "size": len(image_config),
            "digest": config_digest,
        },
        "layers": [{
            "mediaType": "application/vnd.docker.image.rootfs.diff.tar.gzip",
            "size": len(layer),
            "digest": layer_digest,
        }],
    }).encode()

    status, _, _ = request(
        upstream_url,
        "/v2/%s/manifests/%s" % (repository, config["tag"]),
        "PUT",
        body=manifest,
        content_type=MANIFEST_MEDIA_TYPE,
    )
    if status != 201:
        raise SystemExit("pushing the manifest answered %d" % status)

    return {
        "manifest_digest": digest_of(manifest),
        "config_digest": config_digest,
        "config_size": len(image_config),
        "layer_digest": layer_digest,
        "layer_size": len(layer),
    }


def probe():
    """Exercises the proxy: pass-through, filtering, caching and metrics."""
    proxy_url = config["proxy_url"]
    repository = config["repository"]
    seeded = config["seeded"]

    allowed_ip = config["allowed_ip"]
    denied_ua = config["denied_ua"]

    def as_read(path, forwarded_for, user_agent, accept=None):
        status, headers, body = request(
            proxy_url, path, accept=accept,
            forwarded_for=forwarded_for, user_agent=user_agent,
        )
        return status, headers, body

    def summarize(status, headers, body):
        return {
            "status": status,
            "x_cache": headers.get("X-Cache"),
            "docker_distribution_api_version": headers.get("Docker-Distribution-Api-Version"),
            "error_code": error_code_of(body),
        }

    report = {}

    # -----------------------------------------------------------------
    # The process is up. `/_health` is registered before the filtering
    # middleware, so it answers whatever the allow lists say.
    # -----------------------------------------------------------------
    status, headers, body = request(proxy_url, "/_health")
    report["health"] = dict(summarize(status, headers, body),
                            body=body.decode("utf-8", "replace").strip())

    # -----------------------------------------------------------------
    # Pass-through: is a registry really on the other side?
    # -----------------------------------------------------------------
    status, headers, body = as_read("/v2/", allowed_ip, denied_ua)
    report["api_root"] = summarize(status, headers, body)

    # Asked for by tag, the way a `docker pull` would, and re-hashed against
    # what `seed` pushed straight into the upstream.
    status, headers, body = as_read(
        "/v2/%s/manifests/%s" % (repository, config["tag"]),
        allowed_ip, denied_ua, accept=MANIFEST_MEDIA_TYPE,
    )
    manifest_digest = headers.get("Docker-Content-Digest")
    report["manifest_get"] = dict(summarize(status, headers, body), **{
        "digest_header": manifest_digest,
        "digest_matches_body": manifest_digest == digest_of(body),
        "digest_matches_seeded": manifest_digest == seeded["manifest_digest"],
        "media_type": (json.loads(body).get("mediaType") if status == 200 else None),
    })

    blob_get = {}
    for name in ("config", "layer"):
        digest = seeded["%s_digest" % name]
        status, headers, body = as_read(
            "/v2/%s/blobs/%s" % (repository, digest), allowed_ip, denied_ua,
        )
        blob_get[name] = dict(summarize(status, headers, body), **{
            "size": len(body),
            "digest_matches": digest_of(body) == digest,
        })
    report["blob_get"] = blob_get

    # A repository the upstream does not have. A proxy that made its answers up
    # rather than asking the upstream could not produce this.
    status, headers, body = as_read(
        "/v2/%s/manifests/latest" % config["absent_repository"],
        allowed_ip, denied_ua, accept=MANIFEST_MEDIA_TYPE,
    )
    report["absent_repository"] = summarize(status, headers, body)

    # -----------------------------------------------------------------
    # Caching. The cache key is the method, the URL and the Accept header -
    # never the client - so the nonce is what keeps each pass's cache probe
    # from being answered out of an earlier pass's entry.
    # -----------------------------------------------------------------
    cache_path = "/v2/%s/tags/list?n=%s" % (repository, config["cache_nonce"])
    first = summarize(*as_read(cache_path, allowed_ip, denied_ua))
    second = summarize(*as_read(cache_path, allowed_ip, denied_ua))
    report["cache"] = {"path": cache_path, "first": first, "second": second}

    # -----------------------------------------------------------------
    # Who is let in. Each probe uses a client address of its own, because the
    # proxy remembers both its allows and its denials per address.
    # -----------------------------------------------------------------
    report["auth"] = {
        # In the allow list, so the user agent never gets looked at.
        "allowed_by_ip": summarize(*as_read("/v2/", allowed_ip, denied_ua)),
        # Not in the allow list, but carrying an allowed user agent.
        "allowed_by_ua": summarize(*as_read(
            "/v2/", config["ua_allowed_ip"], config["allowed_ua"])),
        # Neither, so nothing lets this one through.
        "denied": summarize(*as_read("/v2/", config["denied_ip"], denied_ua)),
        # Writes are decided by the trusted list instead, and a read-allowed
        # address is not thereby trusted to write.
        "untrusted_write": summarize(*request(
            proxy_url, "/v2/", "PUT",
            forwarded_for=config["untrusted_ip"], user_agent=denied_ua)),
        # A method that is neither a read nor a write.
        "unsupported_method": summarize(*request(
            proxy_url, "/v2/", "TRACE",
            forwarded_for=allowed_ip, user_agent=denied_ua)),
    }

    # -----------------------------------------------------------------
    # A write, made through the proxy from a trusted address. Where the bytes
    # ended up is checked on the upstream itself, by the verifier.
    # -----------------------------------------------------------------
    trusted_ip = config["trusted_ip"]
    payload = ("written-through-the-proxy:%s\n" % config["cache_nonce"]).encode()

    status, headers, body = request(
        proxy_url, "/v2/%s/blobs/uploads/" % repository, "POST",
        forwarded_for=trusted_ip, user_agent=denied_ua,
    )
    write_through = dict(summarize(status, headers, body),
                         location=headers.get("Location"),
                         digest=digest_of(payload),
                         size=len(payload))

    if status == 202:
        location = headers["Location"]
        separator = "&" if "?" in location else "?"
        put_status, put_headers, put_body = request(
            proxy_url, location + separator + "digest=" + digest_of(payload), "PUT",
            body=payload, content_type="application/octet-stream",
            forwarded_for=trusted_ip, user_agent=denied_ua,
        )
        write_through["blob_put"] = summarize(put_status, put_headers, put_body)

    report["write_through"] = write_through

    # -----------------------------------------------------------------
    # Metrics, behind the basic auth the role configures. The counters name the
    # very addresses probed above, so this is the running process reporting on
    # the requests this script just made.
    # -----------------------------------------------------------------
    status, headers, body = request(proxy_url, "/metrics")
    report["metrics"] = {"unauthenticated": summarize(status, headers, body)}

    credentials = "%s:%s" % (config["metrics_login"], config["metrics_password"])
    status, headers, body = request(
        proxy_url, "/metrics",
        authorization="Basic " + base64.b64encode(credentials.encode()).decode(),
    )
    text = body.decode("utf-8", "replace")
    report["metrics"]["authenticated"] = dict(summarize(status, headers, body), **{
        "counts_denied_client": ('drp_auth_failures{ip="%s"}' % config["denied_ip"]) in text,
        "counts_allowed_client": ('drp_auth_successes{ip="%s"}' % allowed_ip) in text,
    })

    return report


if mode == "seed":
    print(json.dumps(seed(), indent=2))
elif mode == "probe":
    print(json.dumps(probe(), indent=2))
else:
    raise SystemExit("unknown mode %s" % mode)
