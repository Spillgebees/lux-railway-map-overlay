# lux-railway-map-overlay Helm chart

This chart deploys the railway overlay tile server: nginx in front of Martin, serving the generated MBTiles together with the style, sprite, and glyphs that are built into the image. The [self-hosting guide](../../docs/self-hosting.md) describes the container, its endpoints, and its cache headers.

The chart is not published to a Helm repository. Install it from a checkout:

```bash
helm install railway-tiles ./charts/lux-railway-map-overlay -f my-values.yaml
```

## Set the image tag

`image.tag` defaults to the chart's `appVersion` (`0.1.0`), and no image has that tag. Set it to `latest` or to a `sha-<commit>` tag from [GHCR](https://github.com/Spillgebees/lux-railway-map-overlay/pkgs/container/lux-railway-map-overlay). A `sha-` tag gives reproducible rollouts.

## Choose where the MBTiles come from

The published image already contains the MBTiles. With that image you do not need a data volume:

```yaml
image:
  tag: latest

persistence:
  enabled: false
```

With `persistence.enabled: false`, the chart mounts an empty `emptyDir` at `/data` and the server uses the baked-in file.

To serve your own MBTiles, put `lux-railway-map-overlay.mbtiles` at the root of a volume. The chart mounts it read-only at `/data`. If you use the published image, also set `MBTILES_PATH`, because the baked-in file takes precedence over `/data`:

```yaml
persistence:
  existingClaim: lux-railway-map-overlay-data

env:
  MBTILES_PATH: /data/lux-railway-map-overlay.mbtiles
```

Without `existingClaim`, the chart creates a `20Gi` `ReadWriteOnce` PVC named `<release>-data`. You then have to copy the file into it yourself.

## Set the public URL

The server rewrites the URLs in `style.json` to `publicUrl`, so clients must be able to reach it. If `publicUrl` is empty, the chart builds it from the first ingress host: `https://` when `ingress.tls` is set, `http://` otherwise. Without an ingress it falls back to `http://localhost:3000`.

With cert-manager and the default TLS block (`ingress.certManager.addDefaultTls`), `ingress.tls` stays empty, so the derived URL starts with `http://`. Set `publicUrl` explicitly in that case.

## Example values

```yaml
image:
  tag: sha-187c96c

publicUrl: https://tiles.example.com

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

persistence:
  enabled: false
```

To manage TLS secrets yourself, set `ingress.tls` and leave `ingress.certManager.enabled` off. For a namespaced cert-manager issuer, set `ingress.certManager.issuer`, and optionally `issuerKind` and `issuerGroup`.

## Defaults worth knowing

- The pod runs as user and group `101`, with `runAsNonRoot`, a read-only root filesystem, no privilege escalation, all capabilities dropped, and the `RuntimeDefault` seccomp profile.
- nginx needs a writable `/tmp` for its PID, temp files, tile cache, and the rewritten `style.json`. The chart mounts an `emptyDir` there with `tmpVolume.sizeLimit: 64Mi`. The nginx tile cache is capped at 32 MiB, so it fits with room to spare.
- The container listens on port `8080`. The Service exposes it on port `80`.
- Startup, readiness, and liveness probes all call `/health`.
- `networkPolicy.enabled` is `true`. The policy allows ingress on port `8080` from anywhere and blocks all egress. The server needs no outbound traffic.
- The Deployment strategy is `Recreate`, which works with `ReadWriteOnce` volumes such as Azure Disk, EBS, or GCE persistent disks.

## Scaling

Keep `replicaCount: 1` while a `ReadWriteOnce` volume holds the MBTiles. Use more replicas only if your storage supports read-only mounts on several nodes, or if each replica has its own copy of the file. The baked-in image has its own copy, so with `persistence.enabled: false` you can raise `replicaCount` and switch `deploymentStrategy.type` to `RollingUpdate`. `podDisruptionBudget.enabled` adds a PodDisruptionBudget with `minAvailable: 1`.

## Attribution

Maps that use these tiles must show "© OpenStreetMap contributors". See [Attribution and license](../../README.md#attribution-and-license).
