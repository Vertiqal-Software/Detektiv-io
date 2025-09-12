# Contributing to Detecktiv.io

Thank you for your interest in contributing to Detecktiv.io! This document provides guidelines and instructions for contributors.

## Development Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- Git

### Local Development

1. Clone the repository:
```bash
git clone https://github.com/your-org/detecktiv-io.git
cd detecktiv-io
```

2. Set up Python environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Start development services:
```bash
docker-compose up -d
```

## Code Standards

### Python
- Follow PEP 8 style guidelines
- Use type hints for all function signatures
- Maximum line length: 88 characters (Black default)
- Run `black`, `isort`, and `flake8` before committing

### TypeScript/React
- Use TypeScript for all new code
- Follow ESLint configuration
- Use functional components with hooks
- Implement proper error boundaries

### Security
- Never commit secrets or API keys
- Use environment variables for configuration
- Follow OWASP security guidelines
- Implement proper input validation

## Git Workflow

### Branch Naming
- `feature/description` - New features
- `fix/description` - Bug fixes
- `chore/description` - Maintenance tasks
- `docs/description` - Documentation updates

### Commit Messages
Follow [Conventional Commits](https://www.conventionalcommits.org/):
```
type(scope): description

Examples:
feat(api): add company financial analysis endpoint
fix(auth): resolve token expiration handling
docs(readme): update installation instructions
```

### Pull Requests
1. Create a feature branch from `main`
2. Make your changes with appropriate tests
3. Run the test suite: `pytest`
4. Update documentation if needed
5. Create a pull request with:
   - Clear description of changes
   - Link to related issues
   - Screenshots for UI changes

## Testing

### Backend Tests
```bash
cd apps/api
pytest tests/
```

### Frontend Tests
```bash
cd apps/web
npm test
```

### Integration Tests
```bash
docker-compose -f docker-compose.test.yml up --build
```

## Code Review Process

1. All code changes require review
2. Reviews focus on:
   - Code quality and standards
   - Security implications
   - Performance impact
   - Test coverage
3. Address review feedback promptly
4. Maintain a respectful and collaborative tone

## Deployment

- `main` branch auto-deploys to staging
- Production deployments require manual approval
- Follow semantic versioning for releases

## Getting Help

- Create an issue for bugs or feature requests
- Join our Discord for development discussions
- Check existing documentation and ADRs

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.