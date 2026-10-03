# lux-railway-map-overlay Helm chart

This chart deploys the railway overlay tile server: nginx in front of Martin, serving the generated MBTiles together with the style, sprite, and glyphs that are built into the image. The [self-hosting guide](../../docs/self-hosting.md) describes the container, its endpoints, and its cache headers.

## Install

CI publishes the chart to GHCR as an OCI artifact, once per image build. Pick a version from the [chart package page](https://github.com/Spillgebees/lux-railway-map-overlay/pkgs/container/charts%2Flux-railway-map-overlay) and install it:

```bash
helm install railway-tiles oci://ghcr.io/spillgebees/charts/lux-railway-map-overlay \
  --version 2026.1003.76 -f my-values.yaml
```

Without `--version`, Helm installs the newest chart.

## Versions and image tags

The chart and the image share one version, `<year>.<month * 100 + day>.<run number>`. A build on 3 October 2026 in workflow run 76 is `2026.1003.76`. The chart's `appVersion` is that version and `image.tag` defaults to `appVersion`, so each chart installs the image built in the same run. Upgrading the chart moves you to newer data. CI never overwrites a version tag.

Set `image.tag` only to run a different image, for example `latest` or a `sha-<commit>` tag from [GHCR](https://github.com/Spillgebees/lux-railway-map-overlay/pkgs/container/lux-railway-map-overlay).

The `Chart.yaml` in the repository has the placeholder version `0.0.0`, and no image has that tag. Installing from a checkout fails with an error unless you set `image.tag`:

```bash
helm install railway-tiles ./charts/lux-railway-map-overlay --set image.tag=latest
```

The chart ships a `values.schema.json`. Helm rejects unknown keys and invalid values, such as a misspelled `persistence` or an unsupported `image.pullPolicy`, before it renders anything.

## Choose where the MBTiles come from

The published image already contains the MBTiles, so by default the chart mounts no data volume (`persistence.enabled: false`).

To serve your own MBTiles, put `lux-railway-map-overlay.mbtiles` at the root of a volume. The chart mounts it read-only at `/data`. If you use the published image, also set `MBTILES_PATH`, because the baked-in file takes precedence over `/data`:

```yaml
persistence:
  enabled: true
  existingClaim: lux-railway-map-overlay-data

env:
  MBTILES_PATH: /data/lux-railway-map-overlay.mbtiles
```

Without `existingClaim`, the chart creates a `20Gi` `ReadWriteOnce` PVC named `<release>-data`. You then have to copy the file into it yourself.

## Set the public URL

The server rewrites the URLs in `style.json` to `publicUrl`, so clients must be able to reach it. If `publicUrl` is empty, the chart builds it from the first ingress host. It uses `https://` when the Ingress has TLS, either from `ingress.tls` or from the cert-manager default TLS block (`ingress.certManager.enabled` with `addDefaultTls`), and `http://` otherwise. Without an ingress it falls back to `http://localhost:3000`.

## Example values

```yaml
ingress:
  enabled: true
  className: nginx
  hosts:
    - host: tiles.example.com
      paths:
        - path: /
          pathType: Prefix
  certManager:
    enabled: true
    clusterIssuer: letsencrypt-prod
```

With these values the derived `publicUrl` is `https://tiles.example.com`.

To manage TLS secrets yourself, set `ingress.tls` and leave `ingress.certManager.enabled` off. For a namespaced cert-manager issuer, set `ingress.certManager.issuer`, and optionally `issuerKind` and `issuerGroup`.

## Defaults worth knowing

- The chart requires Kubernetes 1.25 or newer.
- The pod runs as user and group `101`, with `runAsNonRoot`, a read-only root filesystem, no privilege escalation, all capabilities dropped, and the `RuntimeDefault` seccomp profile.
- nginx needs a writable `/tmp` for its PID, temp files, tile cache, and the rewritten `style.json`. The chart mounts an `emptyDir` there with `tmpVolume.sizeLimit: 64Mi`. The nginx tile cache is capped at 32 MiB, so it fits with room to spare.
- The container listens on port `8080`. The Service exposes it on port `80`. The container also serves metrics on port `9090`, which the chart leaves unexposed unless `metrics.enabled` is set.
- Startup, readiness, and liveness probes all call `/health`.
- `networkPolicy.enabled` is `true`. The policy allows ingress on port `8080` from anywhere and blocks all egress. The server needs no outbound traffic. Port `9090` accepts traffic only from the peers in `metrics.networkPolicy.from`.
- The Deployment strategy is `RollingUpdate` without a data volume and `Recreate` with one, because a `ReadWriteOnce` volume such as Azure Disk, EBS, or a GCE persistent disk attaches to one node at a time. Set `deploymentStrategy.type` to override it.

## Metrics

The container serves Martin's Prometheus metrics at `/metrics` on port `9090`. The public port `8080` does not serve them. `metrics.enabled` adds a `metrics` container port and a ClusterIP Service named `<release>-lux-railway-map-overlay-metrics`. It is a separate Service so that a `LoadBalancer` or `NodePort` type on the main Service never exposes the metrics.

With the Prometheus Operator installed, `metrics.serviceMonitor.enabled` adds a ServiceMonitor that scrapes that Service. The chart renders it only when the cluster serves the `monitoring.coreos.com/v1` API. With `helm template`, pass `--api-versions monitoring.coreos.com/v1`. Add the labels your Prometheus selects ServiceMonitors by to `metrics.serviceMonitor.labels`.

The NetworkPolicy blocks port `9090` unless you list the scrapers in `metrics.networkPolicy.from`. The entries are NetworkPolicy peers:

```yaml
metrics:
  enabled: true
  serviceMonitor:
    enabled: true
    labels:
      release: prometheus
  networkPolicy:
    from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: monitoring
        podSelector:
          matchLabels:
            app.kubernetes.io/name: prometheus
```

Without the NetworkPolicy (`networkPolicy.enabled: false`), any pod in the cluster can reach port `9090` on the pod IP, whether or not `metrics.enabled` is set.

## Scaling

With the default baked-in data, every replica has its own copy of the MBTiles, so you can raise `replicaCount` as far as you like. Keep `replicaCount: 1` while a `ReadWriteOnce` volume holds the MBTiles, unless your storage supports read-only mounts on several nodes.

`podDisruptionBudget.enabled` adds a PodDisruptionBudget with `minAvailable: 1`. Enable it only with two or more replicas. With one replica it blocks node drains.

## Attribution

Maps that use these tiles must show "© OpenStreetMap contributors". See [Attribution and license](../../README.md#attribution-and-license).
