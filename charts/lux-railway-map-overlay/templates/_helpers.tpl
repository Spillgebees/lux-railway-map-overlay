{{- define "lux-railway-map-overlay.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "lux-railway-map-overlay.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := include "lux-railway-map-overlay.name" . -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "lux-railway-map-overlay.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "lux-railway-map-overlay.labels" -}}
helm.sh/chart: {{ include "lux-railway-map-overlay.chart" . }}
app.kubernetes.io/name: {{ include "lux-railway-map-overlay.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ include "lux-railway-map-overlay.imageTag" . | trunc 63 | trimSuffix "-" | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "lux-railway-map-overlay.selectorLabels" -}}
app.kubernetes.io/name: {{ include "lux-railway-map-overlay.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "lux-railway-map-overlay.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "lux-railway-map-overlay.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
Image tag: image.tag, or the chart appVersion. The published chart sets
appVersion to its release version. The in-tree Chart.yaml keeps the 0.0.0
placeholder, and no image has that tag.
*/}}
{{- define "lux-railway-map-overlay.imageTag" -}}
{{- $tag := toString (default .Chart.AppVersion .Values.image.tag) -}}
{{- if eq $tag "0.0.0" -}}
{{- fail "image.tag resolves to the placeholder 0.0.0, which is not a published image. Install the published chart (helm install <release> oci://ghcr.io/spillgebees/charts/lux-railway-map-overlay --version <version>), or set image.tag to a published tag such as latest, sha-<commit>, or a release version." -}}
{{- end -}}
{{- $tag -}}
{{- end -}}

{{/*
"true" when the Ingress gets a TLS block, either from ingress.tls or from the
cert-manager default. Mirrors the tls logic in ingress.yaml.
*/}}
{{- define "lux-railway-map-overlay.ingressTls" -}}
{{- if or .Values.ingress.tls (and .Values.ingress.certManager.enabled .Values.ingress.certManager.addDefaultTls) -}}
true
{{- end -}}
{{- end -}}

{{/*
Deployment strategy: deploymentStrategy.type if set. Otherwise Recreate while
a PVC is mounted (a ReadWriteOnce volume can block the new pod from starting)
and RollingUpdate when the pod serves the MBTiles baked into the image.
*/}}
{{- define "lux-railway-map-overlay.strategyType" -}}
{{- if .Values.deploymentStrategy.type -}}
{{- .Values.deploymentStrategy.type -}}
{{- else if .Values.persistence.enabled -}}
Recreate
{{- else -}}
RollingUpdate
{{- end -}}
{{- end -}}

{{- define "lux-railway-map-overlay.publicUrl" -}}
{{- if .Values.publicUrl -}}
{{- .Values.publicUrl -}}
{{- else if and .Values.ingress.enabled (gt (len .Values.ingress.hosts) 0) -}}
{{- $host := (index .Values.ingress.hosts 0).host -}}
{{- if include "lux-railway-map-overlay.ingressTls" . -}}
{{- printf "https://%s" $host -}}
{{- else -}}
{{- printf "http://%s" $host -}}
{{- end -}}
{{- else -}}
http://localhost:3000
{{- end -}}
{{- end -}}
