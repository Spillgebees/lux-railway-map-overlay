# lux-railway-map-overlay Helm Chart

This chart deploys the production tile server image for Luxembourg Railway Infrastructure Vector Tile Overlay: nginx in front of Martin, serving the generated MBTiles and baked-in styles.

## Storage and deployment defaults

- The chart defaults the Deployment strategy to `Recreate`, which is compatible with `ReadWriteOnce` storage (e.g., Azure Disk CSI on AKS, EBS on EKS, or standard PDs on GKE). If your storage supports `ReadWriteMany`, you can switch to a `RollingUpdate` strategy with multiple replicas.
- The application runs as an unprivileged user (`101:101`) with `allowPrivilegeEscalation: false`, all Linux capabilities dropped, and `readOnlyRootFilesystem: true`.
- A writable `emptyDir` is mounted at `/tmp` for nginx PID/temp files and runtime-rewritten style metadata.
- The MBTiles volume is mounted read-only at `/data` and must contain `lux-railway-map-overlay.mbtiles`.

## Example values

```yaml
image:
  repository: ghcr.io/your-org/lux-railway-map-overlay
  tag: "2026-03-18"

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
  existingClaim: lux-railway-map-overlay-data
```

If you prefer to manage TLS secrets yourself, set `ingress.tls` explicitly and leave `ingress.certManager.enabled` disabled.

For a namespaced cert-manager issuer, use `ingress.certManager.issuer` and optionally `issuerKind` / `issuerGroup`.

## Notes

- Keep `replicaCount: 1` unless your storage supports multi-node read-only mounts or each replica has its own local copy of the MBTiles file.
- If you switch to a `ReadWriteMany` storage backend that performs well enough for your workload, you can consider multiple replicas.
- `publicUrl` should match the externally reachable URL used by clients, typically your ingress host.
