# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |

## Reporting a Vulnerability

We take the security of our software seriously. If you believe you have found a security vulnerability, please report it to us as described below.

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please send an email to security@detecktiv.io. Include the following information:

- Type of issue (e.g. buffer overflow, SQL injection, cross-site scripting, etc.)
- Full paths of source file(s) related to the manifestation of the issue
- The location of the affected source code (tag/branch/commit or direct URL)
- Any special configuration required to reproduce the issue
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit the issue

## Response Timeline

- We will acknowledge receipt of your vulnerability report within 2 business days
- We will provide an initial assessment within 5 business days
- We will work with you to understand and resolve the issue promptly

## Security Best Practices

- All secrets are managed via SOPS encryption and ExternalSecrets operator
- Database access uses row-level security (RLS) for multi-tenant isolation
- All API endpoints require authentication unless explicitly public
- CSP headers are enforced on all web responses
- Regular dependency updates via Dependabot
- Automated security scanning via CodeQL and Trivy