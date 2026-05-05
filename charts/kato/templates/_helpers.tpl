{{/*
Expand the name of the chart.
*/}}
{{- define "kato.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "kato.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "kato.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "kato.labels" -}}
helm.sh/chart: {{ include "kato.chart" . }}
{{ include "kato.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: api
app.kubernetes.io/part-of: kato
{{- end }}

{{/*
Selector labels
*/}}
{{- define "kato.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kato.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "kato.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "kato.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Service account for the bootstrap Job — falls back to main SA when not overridden.
*/}}
{{- define "kato.bootstrapServiceAccountName" -}}
{{- default (include "kato.serviceAccountName" .) .Values.bootstrap.serviceAccountName }}
{{- end }}

{{/*
Name of the chart-rendered Secret (only used when secrets.create=true).
*/}}
{{- define "kato.credentialsSecretName" -}}
{{- printf "%s-credentials" (include "kato.fullname" .) }}
{{- end }}

{{/*
Image reference. Honors image.tag override, falls back to Chart.AppVersion.
*/}}
{{- define "kato.image" -}}
{{- $tag := default .Chart.AppVersion .Values.image.tag }}
{{- printf "%s:%s" .Values.image.repository $tag }}
{{- end }}

{{/*
Bootstrap image — same as main image unless overridden via bootstrap.image.repository / bootstrap.image.tag.
*/}}
{{- define "kato.bootstrapImage" -}}
{{- $bi := .Values.bootstrap.image | default dict }}
{{- $repo := default .Values.image.repository (get $bi "repository") }}
{{- $tag := default (default .Chart.AppVersion .Values.image.tag) (get $bi "tag") }}
{{- printf "%s:%s" $repo $tag }}
{{- end }}

{{/*
Resolve the Secret name and key holding the ClickHouse password.
Returns "name|key". When secrets.create=true and no existingSecret is set,
falls back to the chart-rendered credentials Secret. Empty when neither applies.
*/}}
{{- define "kato.clickhousePasswordRef" -}}
{{- if .Values.clickhouse.auth.existingSecret -}}
{{- printf "%s|%s" .Values.clickhouse.auth.existingSecret .Values.clickhouse.auth.passwordKey -}}
{{- else if and .Values.secrets.create .Values.clickhouse.auth.password -}}
{{- printf "%s|clickhouse-password" (include "kato.credentialsSecretName" .) -}}
{{- end -}}
{{- end }}

{{/*
Resolve the Secret/key holding the Redis URL (preferred path).
Empty when component-wise mode is in use.
*/}}
{{- define "kato.redisUrlRef" -}}
{{- if .Values.redis.urlExistingSecret -}}
{{- printf "%s|%s" .Values.redis.urlExistingSecret .Values.redis.urlKey -}}
{{- else if and .Values.secrets.create .Values.redis.auth.password -}}
{{- printf "%s|redis-url" (include "kato.credentialsSecretName" .) -}}
{{- end -}}
{{- end }}

{{/*
Resolve the Secret/key holding the Redis password (component-wise mode).
*/}}
{{- define "kato.redisPasswordRef" -}}
{{- if .Values.redis.auth.existingSecret -}}
{{- printf "%s|%s" .Values.redis.auth.existingSecret .Values.redis.auth.passwordKey -}}
{{- end -}}
{{- end }}

{{/*
Resolve the Secret/key holding the Qdrant API key.
*/}}
{{- define "kato.qdrantApiKeyRef" -}}
{{- if .Values.qdrant.auth.existingSecret -}}
{{- printf "%s|%s" .Values.qdrant.auth.existingSecret .Values.qdrant.auth.apiKeyKey -}}
{{- else if and .Values.secrets.create .Values.qdrant.auth.apiKey -}}
{{- printf "%s|qdrant-api-key" (include "kato.credentialsSecretName" .) -}}
{{- end -}}
{{- end }}

{{/*
Render the container env block for KATO. Used by both the main Deployment
and the bootstrap Job so connection envs are identical.
*/}}
{{- define "kato.connectionEnv" -}}
{{- /* ClickHouse */ -}}
{{- $chRef := include "kato.clickhousePasswordRef" . -}}
{{- if .Values.clickhouse.auth.existingSecret }}
- name: CLICKHOUSE_USER
  valueFrom:
    secretKeyRef:
      name: {{ .Values.clickhouse.auth.existingSecret }}
      key: {{ .Values.clickhouse.auth.userKey }}
{{- else if .Values.clickhouse.auth.username }}
- name: CLICKHOUSE_USER
  value: {{ .Values.clickhouse.auth.username | quote }}
{{- end }}
{{- if $chRef }}
- name: CLICKHOUSE_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ (split "|" $chRef)._0 }}
      key: {{ (split "|" $chRef)._1 }}
{{- end }}
{{- /* Redis: URL mode preferred, component fallback */ -}}
{{- $redisUrlRef := include "kato.redisUrlRef" . -}}
{{- $redisPwRef := include "kato.redisPasswordRef" . -}}
{{- if $redisUrlRef }}
- name: REDIS_URL
  valueFrom:
    secretKeyRef:
      name: {{ (split "|" $redisUrlRef)._0 }}
      key: {{ (split "|" $redisUrlRef)._1 }}
{{- else if $redisPwRef }}
- name: REDIS_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ (split "|" $redisPwRef)._0 }}
      key: {{ (split "|" $redisPwRef)._1 }}
{{- end }}
{{- /* Qdrant API key */ -}}
{{- $qdRef := include "kato.qdrantApiKeyRef" . -}}
{{- if $qdRef }}
- name: QDRANT_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ (split "|" $qdRef)._0 }}
      key: {{ (split "|" $qdRef)._1 }}
{{- end }}
{{- end }}

{{/*
Render the volumes for the CA bundle and writable scratch dirs.
*/}}
{{- define "kato.volumes" -}}
- name: tmp
  emptyDir: {}
- name: cache
  emptyDir: {}
{{- if .Values.tls.caBundle.existingConfigMap }}
- name: ca-bundle
  configMap:
    name: {{ .Values.tls.caBundle.existingConfigMap }}
{{- else if .Values.tls.caBundle.existingSecret }}
- name: ca-bundle
  secret:
    secretName: {{ .Values.tls.caBundle.existingSecret }}
{{- end }}
{{- with .Values.extraVolumes }}
{{- toYaml . | nindent 0 }}
{{- end }}
{{- end }}

{{/*
Render the volumeMounts (matched against kato.volumes).
*/}}
{{- define "kato.volumeMounts" -}}
- name: tmp
  mountPath: /tmp
- name: cache
  mountPath: /app/.cache
{{- if or .Values.tls.caBundle.existingConfigMap .Values.tls.caBundle.existingSecret }}
- name: ca-bundle
  mountPath: /etc/ssl/kato-ca
  readOnly: true
{{- end }}
{{- with .Values.extraVolumeMounts }}
{{- toYaml . | nindent 0 }}
{{- end }}
{{- end }}
