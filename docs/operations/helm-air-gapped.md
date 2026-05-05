# Air-gapped / Mirrored Helm Install

For enterprises whose Kubernetes clusters cannot reach `ghcr.io` directly, the chart and image must be mirrored into your internal registry first.

## Step 1 — Mirror the container image

```bash
# Pull on a host with internet access
docker pull ghcr.io/sevakavakians/kato:3.10.1
docker tag  ghcr.io/sevakavakians/kato:3.10.1 \
            registry.internal.example.com/kato/kato:3.10.1
docker push registry.internal.example.com/kato/kato:3.10.1
```

Or, with `crane` (faster, no daemon required):

```bash
crane copy ghcr.io/sevakavakians/kato:3.10.1 \
           registry.internal.example.com/kato/kato:3.10.1
```

## Step 2 — Mirror the Helm chart

Pull from the public OCI registry, then push to your internal one:

```bash
helm registry login ghcr.io   # only needed once
helm pull oci://ghcr.io/sevakavakians/charts/kato --version 0.1.0
# This produces kato-0.1.0.tgz in the current directory.

helm registry login registry.internal.example.com
helm push kato-0.1.0.tgz oci://registry.internal.example.com/charts
```

Alternative: download the `kato-0.1.0.tgz` artifact from the [GitHub Release](https://github.com/intelligent-artifacts/kato/releases) page and copy it into your network. The release attachment is byte-identical to the OCI artifact.

## Step 3 — Override `image.repository` in values

```yaml
image:
  repository: registry.internal.example.com/kato/kato
  tag: "3.10.1"
  pullSecrets:
    - name: internal-registry-pull   # if your registry requires auth
```

If you also want the bootstrap Job to use an alternate image (e.g., a hardened/scanned variant), set `bootstrap.image`:

```yaml
bootstrap:
  enabled: true
  image:
    repository: registry.internal.example.com/kato/kato-hardened
    tag: "3.10.1"
```

## Step 4 — Install from the mirrored chart

```bash
helm install kato oci://registry.internal.example.com/charts/kato \
  --version 0.1.0 \
  --namespace kato --create-namespace \
  -f values.yaml \
  --atomic --timeout 5m
```

Or from the `.tgz` directly (no registry login needed):

```bash
helm install kato ./kato-0.1.0.tgz \
  --namespace kato --create-namespace \
  -f values.yaml \
  --atomic --timeout 5m
```

## Verifying provenance

The container image is signed via cosign keyless. To verify before mirroring:

```bash
cosign verify ghcr.io/sevakavakians/kato:3.10.1 \
  --certificate-identity-regexp '.*' \
  --certificate-oidc-issuer-regexp '.*'
```

(Chart-level provenance signing — `cosign sign` on the OCI artifact, or Helm GPG provenance — is on the v0.2.0 roadmap.)

The KATO release also publishes an SPDX SBOM as a GitHub Release attachment for vendor risk reviews.

## Notes

- Egress for the `pre-install` Job: the bootstrap Job needs reachability to ClickHouse, Redis, and Qdrant. Confirm your `NetworkPolicy` (if `networkPolicy.enabled=true`) lists those CIDRs in `egressCIDRs`.
- DNS-only egress restrictions: NetworkPolicy egress works on IPs/CIDRs, not DNS hostnames. If your platform team can only give you DNS names, leave `egressCIDRs: []` and rely on the platform's underlying network controls.
