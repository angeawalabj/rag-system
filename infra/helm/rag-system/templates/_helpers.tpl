{{/*
_helpers.tpl — Fonctions partagées pour tous les templates Helm.
Convention : {{ include "rag-system.xxx" . }}
*/}}

{{/* Nom complet du chart */}}
{{- define "rag-system.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "rag-system.fullname" -}}
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

{{/* Chart label : name-version */}}
{{- define "rag-system.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Labels communs (metadata.labels) */}}
{{- define "rag-system.labels" -}}
helm.sh/chart: {{ include "rag-system.chart" . }}
{{ include "rag-system.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: rag-system
{{- end }}

{{/* Selector labels (spec.selector.matchLabels) */}}
{{- define "rag-system.selectorLabels" -}}
app.kubernetes.io/name: {{ include "rag-system.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* ──── Labels par service ──────────────────────────────────────────────── */}}

{{- define "rag-system.ingestion.labels" -}}
{{ include "rag-system.labels" . }}
app.kubernetes.io/component: ingestion
{{- end }}

{{- define "rag-system.ingestion.selectorLabels" -}}
{{ include "rag-system.selectorLabels" . }}
app.kubernetes.io/component: ingestion
{{- end }}

{{- define "rag-system.ragApi.labels" -}}
{{ include "rag-system.labels" . }}
app.kubernetes.io/component: rag-api
{{- end }}

{{- define "rag-system.ragApi.selectorLabels" -}}
{{ include "rag-system.selectorLabels" . }}
app.kubernetes.io/component: rag-api
{{- end }}

{{- define "rag-system.frontend.labels" -}}
{{ include "rag-system.labels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{- define "rag-system.frontend.selectorLabels" -}}
{{ include "rag-system.selectorLabels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{- define "rag-system.ollama.labels" -}}
{{ include "rag-system.labels" . }}
app.kubernetes.io/component: ollama
{{- end }}

{{- define "rag-system.ollama.selectorLabels" -}}
{{ include "rag-system.selectorLabels" . }}
app.kubernetes.io/component: ollama
{{- end }}

{{/* ──── URLs internes ────────────────────────────────────────────────────── */}}

{{/* URL Qdrant interne au cluster */}}
{{- define "rag-system.qdrantUrl" -}}
{{- if .Values.qdrant.enabled -}}
http://{{ .Release.Name }}-qdrant:6333
{{- else -}}
{{ .Values.externalQdrantUrl | default "http://qdrant:6333" }}
{{- end }}
{{- end }}

{{/* URL Redis interne */}}
{{- define "rag-system.redisUrl" -}}
{{- if .Values.redis.enabled -}}
redis://{{ .Release.Name }}-redis-master:6379/0
{{- else -}}
{{ .Values.externalRedisUrl | default "redis://redis:6379/0" }}
{{- end }}
{{- end }}

{{/* URL PostgreSQL interne */}}
{{- define "rag-system.postgresHost" -}}
{{- if .Values.postgresql.enabled -}}
{{ .Release.Name }}-postgresql
{{- else -}}
{{ .Values.externalPostgresHost | default "postgres" }}
{{- end }}
{{- end }}

{{/* URL Ollama interne */}}
{{- define "rag-system.ollamaUrl" -}}
{{- if .Values.ollama.enabled -}}
http://{{ include "rag-system.fullname" . }}-ollama:11434
{{- else -}}
{{ .Values.externalOllamaUrl | default "http://ollama:11434" }}
{{- end }}
{{- end }}

{{/* URL OTel Collector */}}
{{- define "rag-system.otelEndpoint" -}}
{{- if .Values.otelCollector.enabled -}}
http://{{ .Release.Name }}-opentelemetry-collector:4317
{{- else -}}
{{ .Values.externalOtelEndpoint | default "http://localhost:4317" }}
{{- end }}
{{- end }}

{{/* ──── Image helpers ────────────────────────────────────────────────────── */}}

{{- define "rag-system.image" -}}
{{- $registry := .global.imageRegistry | default "" -}}
{{- $repo := .image.repository -}}
{{- $tag := .image.tag | default "latest" -}}
{{- if $registry -}}
{{ $registry }}/{{ $repo }}:{{ $tag }}
{{- else -}}
{{ $repo }}:{{ $tag }}
{{- end }}
{{- end }}
