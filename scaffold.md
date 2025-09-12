```
repo-root/
├─ apps/
│  └─ web/
│     └─ src/
│        └─ pages/
│           ├─ _app.tsx
│           ├─ _document.tsx
│           ├─ 404.tsx
│           ├─ 500.tsx
│           ├─ index.tsx
│           ├─ auth/
│           │  ├─ login.tsx
│           │  ├─ register.tsx
│           │  ├─ verify-email.tsx
│           │  ├─ mfa.tsx
│           │  ├─ sso/
│           │  │  ├─ start.tsx
│           │  │  └─ callback.tsx
│           │  └─ reset/
│           │     ├─ request.tsx
│           │     └─ change.tsx
│           ├─ app/
│           │  ├─ index.tsx
│           │  ├─ dashboards/
│           │  │  ├─ index.tsx
│           │  │  ├─ exec.tsx
│           │  │  ├─ manager.tsx
│           │  │  ├─ rep.tsx
│           │  │  ├─ builder.tsx
│           │  │  └─ shared/
│           │  │     └─ [dashboardId].tsx
│           │  ├─ companies/
│           │  │  ├─ index.tsx
│           │  │  ├─ import.tsx
│           │  │  └─ [companyId].tsx
│           │  ├─ alerts/
│           │  │  └─ index.tsx
│           │  ├─ insights/
│           │  │  └─ [companyId].tsx
│           │  ├─ reports/
│           │  │  └─ index.tsx
│           │  ├─ search/
│           │  │  └─ index.tsx
│           │  ├─ integrations/
│           │  │  ├─ salesforce/
│           │  │  │  ├─ connect.tsx
│           │  │  │  ├─ callback.tsx
│           │  │  │  ├─ mapping.tsx
│           │  │  │  ├─ sync.tsx
│           │  │  │  └─ settings.tsx
│           │  │  └─ dynamics/
│           │  │     ├─ connect.tsx
│           │  │     ├─ callback.tsx
│           │  │     ├─ mapping.tsx
│           │  │     ├─ sync.tsx
│           │  │     └─ settings.tsx
│           │  ├─ settings/
│           │  │  ├─ index.tsx
│           │  │  ├─ notifications.tsx
│           │  │  ├─ api-keys.tsx
│           │  │  ├─ webhooks.tsx
│           │  │  ├─ org.tsx
│           │  │  ├─ users.tsx
│           │  │  ├─ roles.tsx
│           │  │  ├─ feature-flags.tsx
│           │  │  ├─ billing.tsx
│           │  │  ├─ retention.tsx
│           │  │  └─ audit-log.tsx
│           │  └─ admin/
│           │     ├─ index.tsx
│           │     ├─ tenants.tsx
│           │     ├─ dlq.tsx
│           │     ├─ feature-flags.tsx
│           │     └─ impersonate.tsx
│           ├─ legal/
│           │  ├─ privacy.tsx
│           │  ├─ terms.tsx
│           │  └─ cookies.tsx
│           └─ api/
│              ├─ health.ts
│              └─ integrations/
│                 ├─ salesforce/
│                 │  └─ callback.ts
│                 └─ dynamics/
│                    └─ callback.ts
├─ .editorconfig
├─ .gitattributes
├─ .gitignore
├─ .pre-commit-config.yaml
├─ .env.example
├─ LICENSE
├─ Makefile
├─ README.md
├─ scaffold.md
├─ .dockerignore
├─ SECURITY.md
├─ CHANGELOG.md
├─ CONTRIBUTING.md
├─ CODE_OF_CONDUCT.md
├─ .gitleaks.toml
├─ .sops.yaml
├─ .spectral.yaml
├─ .devcontainer/
│  ├─ devcontainer.json
│  └─ Dockerfile
├─ docker/
│  ├─ dev/
│  │  ├─ backend.Dockerfile
│  │  ├─ workers.Dockerfile
│  │  └─ web.Dockerfile
│  ├─ prod/
│  │  ├─ backend.Dockerfile
│  │  ├─ workers.Dockerfile
│  │  └─ web.Dockerfile
│  └─ scripts/
│     ├─ healthcheck.sh
│     ├─ migrate.sh
│     └─ wait-for.sh
├─ docker-compose.dev.yml
├─ docker-compose.staging.yml
├─ docker-compose.prod.yml
├─ ops/
│  ├─ helm/
│  │  └─ .keep
│  ├─ k8s/
│  │  ├─ base/
│  │  │  ├─ backend-deploy.yaml
│  │  │  ├─ ingress.yaml
│  │  │  ├─ namespace.yaml
│  │  │  ├─ postgres.yaml
│  │  │  ├─ redis.yaml
│  │  │  ├─ web-deploy.yaml
│  │  │  ├─ workers-deploy.yaml
│  │  │  ├─ networkpolicy.yaml
│  │  │  ├─ pdb-api.yaml
│  │  │  ├─ pdb-workers.yaml
│  │  │  ├─ pdb-web.yaml
│  │  │  ├─ hpa-api.yaml
│  │  │  ├─ hpa-workers.yaml
│  │  │  ├─ hpa-web.yaml
│  │  │  └─ otel-collector.yaml
│  │  └─ overlays/
│  │     ├─ dev/
│  │     │  ├─ kustomization.yaml
│  │     │  └─ externalsecrets.yaml
│  │     ├─ staging/
│  │     │  ├─ kustomization.yaml
│  │     │  └─ externalsecrets.yaml
│  │     └─ prod/
│  │        ├─ kustomization.yaml
│  │        └─ externalsecrets.yaml
│  ├─ runbooks/
│  │  ├─ alerts-catalog.md
│  │  ├─ db-restore.md
│  │  ├─ deploy-rollback.md
│  │  ├─ incident-response.md
│  │  ├─ oncall-playbook.md
│  │  ├─ sar-export.md
│  │  └─ slo.md
│  └─ prometheus/
│     └─ prometheusrule-core.yaml
├─ infra/
│  ├─ terraform/
│  │  ├─ envs/
│  │  │  ├─ dev/
│  │  │  │  ├─ backend.tf
│  │  │  │  ├─ main.tf
│  │  │  │  ├─ outputs.tf
│  │  │  │  └─ variables.tf
│  │  │  ├─ staging/
│  │  │  │  ├─ backend.tf
│  │  │  │  ├─ main.tf
│  │  │  │  ├─ outputs.tf
│  │  │  │  └─ variables.tf
│  │  │  └─ prod/
│  │  │     ├─ backend.tf
│  │  │     ├─ main.tf
│  │  │     ├─ outputs.tf
│  │  │     └─ variables.tf
│  │  └─ modules/
│  │     ├─ ecr/
│  │     │  └─ .keep
│  │     ├─ elasticache-redis/
│  │     │  └─ .keep
│  │     ├─ rds-postgres/
│  │     │  └─ .keep
│  │     ├─ s3-docs/
│  │     │  └─ .keep
│  │     └─ vpc/
│  │        └─ .keep
│  └─ README.md
├─ security/
│  ├─ app/
│  │  ├─ csp.json
│  │  ├─ pii-redaction-rules.json
│  │  └─ security-headers.json
│  ├─ compliance/
│  │  ├─ iso27001-statement-of-applicability.md
│  │  ├─ soc2-controls-matrix.md
│  │  └─ gdpr/
│  │     ├─ cookie-policy.md
│  │     ├─ dpa-template.md
│  │     ├─ dpia-template.md
│  │     ├─ privacy-policy.md
│  │     └─ ropas.csv
│  ├─ policies/
│  │  ├─ access-control-policy.md
│  │  ├─ crypto-policy.md
│  │  ├─ incident-response-policy.md
│  │  ├─ logging-monitoring-policy.md
│  │  ├─ secure-development-policy.md
│  │  └─ vendor-management-policy.md
│  └─ threat-model/
│     ├─ data-flow-diagram.md
│     └─ stride-diagram.md
├─ docs/
│  ├─ api.md
│  ├─ architecture.md
│  ├─ data-lineage.md
│  ├─ index.md
│  ├─ llm-prompts.md
│  ├─ mkdocs.yml
│  ├─ quotas-limits.md
│  ├─ tenancy.md
│  ├─ webhooks.md
│  ├─ scim.md
│  ├─ sso-okta.md
│  ├─ sso-azure-ad.md
│  ├─ onboarding.md
│  ├─ api-versioning.md
│  ├─ testing-strategy.md
│  └─ adrs/
│     ├─ 0001-template.md
│     └─ 0001-record-architecture-decisions.md
├─ .github/
│  ├─ workflows/
│  │  ├─ ci-backend.yml
│  │  ├─ ci-web.yml
│  │  ├─ dast.yml
│  │  ├─ deploy-prod.yml
│  │  ├─ deploy-staging.yml
│  │  ├─ sbom.yml
│  │  └─ trivy-scan.yml
│  ├─ CODEOWNERS
│  ├─ dependabot.yml
│  ├─ ISSUE_TEMPLATE/
│  │  ├─ bug_report.md
│  │  └─ feature_request.md
│  └─ PULL_REQUEST_TEMPLATE.md
├─ packages/
│  ├─ python-common/
│  │  ├─ pyproject.toml
│  │  └─ vdi_common/
│  │     ├─ __init__.py
│  │     ├─ logging.py
│  │     ├─ observability.py
│  │     ├─ pii.py
│  │     ├─ tenancy.py
│  │     ├─ utils.py
│  │     └─ schemas.py
│  └─ ts-common/
│     ├─ package.json
│     ├─ src/
│     │  ├─ api-types.ts
│     │  └─ date.ts
│     └─ openapi-client-gen.md
└─ apps/
   ├─ api/
   │  ├─ pyproject.toml
   │  ├─ wsgi.py
   │  ├─ pytest.ini
   │  ├─ mypy.ini
   │  ├─ app/
   │  │  ├─ __init__.py
   │  │  ├─ config/
   │  │  │  ├─ base.py
   │  │  │  ├─ dev.py
   │  │  │  ├─ staging.py
   │  │  │  └─ prod.py
   │  │  ├─ extensions/
   │  │  │  ├─ auth.py
   │  │  │  ├─ cache.py
   │  │  │  ├─ cors.py
   │  │  │  ├─ db.py
   │  │  │  ├─ limiter.py
   │  │  │  ├─ logging.py
   │  │  │  └─ otel.py
   │  │  ├─ middleware/
   │  │  │  ├─ impersonation.py
   │  │  │  ├─ request_id.py
   │  │  │  ├─ security_headers.py
   │  │  │  └─ tenant.py
   │  │  ├─ models/
   │  │  │  ├─ __init__.py
   │  │  │  ├─ api_key.py
   │  │  │  ├─ audit_log.py
   │  │  │  ├─ company.py
   │  │  │  ├─ entitlement.py
   │  │  │  ├─ event.py
   │  │  │  ├─ feature_flag.py
   │  │  │  ├─ filing.py
   │  │  │  ├─ financial.py
   │  │  │  ├─ insight.py
   │  │  │  ├─ legal_hold.py
   │  │  │  ├─ membership.py
   │  │  │  ├─ meter_event.py
   │  │  │  ├─ officer.py
   │  │  │  ├─ org.py
   │  │  │  ├─ outbox.py
   │  │  │  ├─ person.py
   │  │  │  ├─ release_marker.py
   │  │  │  ├─ retention_policy.py
   │  │  │  ├─ tender.py
   │  │  │  ├─ tenant.py
   │  │  │  ├─ user.py
   │  │  │  └─ website.py
   │  │  ├─ schemas/
   │  │  │  ├─ __init__.py
   │  │  │  ├─ alerts.py
   │  │  │  ├─ auth.py
   │  │  │  ├─ companies.py
   │  │  │  ├─ insights.py
   │  │  │  └─ orgs.py
   │  │  ├─ routes/
   │  │  │  ├─ __init__.py
   │  │  │  ├─ admin/
   │  │  │  │  ├─ __init__.py
   │  │  │  │  ├─ audit.py
   │  │  │  │  ├─ dlq.py
   │  │  │  │  ├─ feature_flags.py
   │  │  │  │  └─ tenants.py
   │  │  │  ├─ health.py
   │  │  │  ├─ auth.py
   │  │  │  ├─ orgs.py
   │  │  │  ├─ invites.py
   │  │  │  ├─ billing.py
   │  │  │  ├─ companies.py
   │  │  │  ├─ dossiers.py
   │  │  │  ├─ alerts.py
   │  │  │  ├─ webhooks.py
   │  │  │  └─ public/
   │  │  │     ├─ __init__.py
   │  │  │     └─ v1/
   │  │  │        ├─ __init__.py
   │  │  │        ├─ companies.py
   │  │  │        ├─ events.py
   │  │  │        ├─ insights.py
   │  │  │        └─ keys.py
   │  │  ├─ services/
   │  │  │  ├─ __init__.py
   │  │  │  ├─ ai_guard.py
   │  │  │  ├─ billing.py
   │  │  │  ├─ companies_house.py
   │  │  │  ├─ documents.py
   │  │  │  ├─ dynamics.py
   │  │  │  ├─ insights.py
   │  │  │  ├─ keywords.py
   │  │  │  ├─ linkedin.py
   │  │  │  ├─ metering.py
   │  │  │  ├─ opencorporates.py
   │  │  │  ├─ s3_storage.py
   │  │  │  ├─ salesforce.py
   │  │  │  ├─ scim.py
   │  │  │  ├─ sso.py
   │  │  │  ├─ tenders.py
   │  │  │  ├─ website_monitor.py
   │  │  │  └─ webhooks.py
   │  │  ├─ utils/
   │  │  │  ├─ __init__.py
   │  │  │  ├─ diff.py
   │  │  │  ├─ http.py
   │  │  │  └─ time.py
   │  │  └─ openapi/
   │  │     └─ openapi.yaml
   │  ├─ alembic/
   │  │  ├─ env.py
   │  │  └─ versions/
   │  │     ├─ 0001_init.py
   │  │     ├─ 0002_companies.py
   │  │     ├─ 0003_filings.py
   │  │     ├─ 0004_insights_alerts.py
   │  │     └─ 0005_rls_policies.py
   │  └─ tests/
   │     ├─ __init__.py
   │     ├─ test_auth.py
   │     ├─ test_companies.py
   │     ├─ test_tenancy.py
   │     └─ test_alerts.py
   ├─ workers/
   │  ├─ pyproject.toml
   │  ├─ celery_app.py
   │  ├─ beat_schedule.yaml
   │  ├─ tasks/
   │  │  ├─ __init__.py
   │  │  ├─ detect_changes.py
   │  │  ├─ fetch_companies_house.py
   │  │  ├─ fetch_opencorporates.py
   │  │  ├─ fetch_tenders.py
   │  │  ├─ generate_insights.py
   │  │  ├─ parse_documents.py
   │  │  ├─ persist_outbox.py
   │  │  ├─ purge_data.py
   │  │  ├─ scrape_website.py
   │  │  └─ send_notifications.py
   │  └─ tests/
   │     ├─ __init__.py
   │     └─ test_tasks.py
   └─ web/
      ├─ next.config.js
      ├─ package.json
      ├─ postcss.config.js
      ├─ tailwind.config.ts
      ├─ tsconfig.json
      ├─ public/
      │  ├─ favicon.ico
      │  ├─ logos/
      │  │  ├─ detecktiv-logo.svg
      │  │  └─ vdi-logo.svg
      │  ├─ brand/
      │  │  ├─ og-image.png
      │  │  └─ social-card.png
      │  └─ .well-known/
      │     └─ security.txt
      └─ src/
         ├─ components/
         │  ├─ layout/
         │  │  ├─ AppShell.tsx
         │  │  ├─ Header.tsx
         │  │  └─ Sidebar.tsx
         │  ├─ ui/
         │  │  ├─ Button.tsx
         │  │  ├─ Card.tsx
         │  │  ├─ Badge.tsx
         │  │  ├─ Tooltip.tsx
         │  │  └─ Modal.tsx
         │  ├─ charts/
         │  │  ├─ FinancialTrend.tsx
         │  │  └─ Sparkline.tsx
         │  ├─ company/
         │  │  ├─ CompanyHeader.tsx
         │  │  ├─ FinancialsCard.tsx
         │  │  ├─ OfficersCard.tsx
         │  │  ├─ WebsiteChangesCard.tsx
         │  │  ├─ TendersCard.tsx
         │  │  ├─ CompetitorMentionsCard.tsx
         │  │  └─ InsightsGoldenCircle.tsx
         │  ├─ alerts/
         │  │  ├─ AlertsFeed.tsx
         │  │  └─ AlertRow.tsx
         │  ├─ forms/
         │  │  ├─ CompanySearch.tsx
         │  │  └─ PreferencesForm.tsx
         │  ├─ skeletons/
         │  │  ├─ CompanySkeleton.tsx
         │  │  └─ ListSkeleton.tsx
         │  └─ icons/
         │     ├─ SuccessIcon.tsx
         │     ├─ WarningIcon.tsx
         │     └─ CriticalIcon.tsx
         ├─ lib/
         │  ├─ apiClient.ts
         │  ├─ auth.ts
         │  ├─ config.ts
         │  ├─ format.ts
         │  ├─ featureFlags.ts
         │  ├─ crm.ts
         │  └─ guard.ts
         ├─ services/
         │  ├─ auth.ts
         │  ├─ companies.ts
         │  ├─ alerts.ts
         │  ├─ insights.ts
         │  └─ integrations.ts
         ├─ store/
         │  ├─ useUser.ts
         │  ├─ useCompanies.ts
         │  ├─ useAlerts.ts
         │  └─ useTenant.ts
         ├─ styles/
         │  ├─ globals.css
         │  └─ tokens.css
         ├─ theme/
         │  ├─ tokens.ts
         │  └─ typography.ts
         └─ i18n/
            ├─ index.ts
            └─ en-GB.json
```