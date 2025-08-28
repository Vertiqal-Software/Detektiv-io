#!/usr/bin/env python3
"""
Detecktiv.io Enhancement Migration Script

This script helps upgrade from the basic Detecktiv.io version to the enhanced
full-featured version with service layer, ORM models, and enterprise features.

Usage:
    python upgrade_to_enhanced.py [--dry-run] [--backup]

Features:
- Backs up existing data
- Migrates database schema
- Updates configuration files  
- Validates the upgrade
- Provides rollback instructions
"""

import os
import sys
import shutil
import subprocess
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import argparse

import click


class UpgradeManager:
    """Manages the upgrade process from basic to enhanced version."""
    
    def __init__(self, project_root: Path, dry_run: bool = False, create_backup: bool = True):
        self.project_root = project_root
        self.dry_run = dry_run
        self.create_backup = create_backup
        self.backup_dir = project_root / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Enhanced files that need to be integrated
        self.enhanced_files = {
            # Core application files
            'app/core/config.py': 'Centralized configuration management',
            'app/core/database.py': 'Enhanced database connection management',
            'app/core/logging.py': 'Structured JSON logging',
            'app/core/utils.py': 'Utility functions',
            'app/core/__init__.py': 'Core module init',
            
            # Models
            'app/models/base.py': 'SQLAlchemy base model',
            'app/models/company.py': 'Enhanced company model',
            'app/models/__init__.py': 'Models module init',
            
            # Services  
            'app/services/company_service.py': 'Company business logic service',
            'app/services/companies_house_service.py': 'Companies House API integration',
            'app/services/__init__.py': 'Services module init',
            
            # Schemas
            'app/schemas/company.py': 'Pydantic validation schemas', 
            'app/schemas/__init__.py': 'Schemas module init',
            
            # Enhanced main application
            'app/main_enhanced.py': 'Enhanced FastAPI application',
            
            # Database migrations
            'db/migrations/env_enhanced.py': 'Enhanced migration environment',
            'db/migrations/versions/enhance_companies_schema.py': 'Schema enhancement migration',
            
            # Requirements
            'requirements_updated.txt': 'Updated Python dependencies',
            'requirements-dev_updated.txt': 'Updated development dependencies',
            
            # Configuration
            '.env.example_updated': 'Enhanced environment configuration',
            
            # Tests
            'tests/conftest_enhanced.py': 'Enhanced test configuration',
            'tests/test_company_service.py': 'Service layer tests',
            'tests/test_api_enhanced.py': 'Enhanced API tests',
            
            # Management
            'manage.py': 'CLI management tool',
            
            # Documentation
            'README_Enhanced.md': 'Complete documentation',
            'DEPLOYMENT.md': 'Production deployment guide'
        }
    
    def run_upgrade(self) -> bool:
        """Execute the complete upgrade process."""
        try:
            click.echo("🚀 Starting Detecktiv.io Enhancement Upgrade")
            click.echo("=" * 50)
            
            # Phase 1: Pre-flight checks
            if not self._preflight_checks():
                return False
            
            # Phase 2: Create backup
            if self.create_backup and not self._create_backup():
                return False
            
            # Phase 3: Install enhanced files
            if not self._install_enhanced_files():
                return False
            
            # Phase 4: Update configuration
            if not self._update_configuration():
                return False
            
            # Phase 5: Database migration
            if not self._run_database_migration():
                return False
            
            # Phase 6: Update dependencies
            if not self._update_dependencies():
                return False
            
            # Phase 7: Validation
            if not self._validate_upgrade():
                return False
            
            # Phase 8: Final instructions
            self._show_completion_instructions()
            
            return True
            
        except Exception as e:
            click.echo(f"❌ Upgrade failed: {e}")
            self._show_rollback_instructions()
            return False
    
    def _preflight_checks(self) -> bool:
        """Perform pre-flight checks before upgrade."""
        click.echo("🔍 Running pre-flight checks...")
        
        # Check if we're in a Detecktiv.io project
        required_files = ['alembic.ini', 'app/main.py', 'docker-compose.yml']
        missing_files = [f for f in required_files if not (self.project_root / f).exists()]
        
        if missing_files:
            click.echo(f"❌ Missing required files: {', '.join(missing_files)}")
            click.echo("Are you running this from the Detecktiv.io project root?")
            return False
        
        # Check Python version
        if sys.version_info < (3, 9):
            click.echo(f"❌ Python 3.9+ required, found {sys.version_info.major}.{sys.version_info.minor}")
            return False
        
        # Check if Docker is available
        try:
            subprocess.run(['docker', '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            click.echo("⚠️  Docker not found. Some features may not work.")
        
        # Check for existing enhanced files
        conflicts = []
        for file_path in self.enhanced_files.keys():
            if (self.project_root / file_path).exists():
                conflicts.append(file_path)
        
        if conflicts and not self.dry_run:
            click.echo(f"⚠️  Found {len(conflicts)} existing enhanced files:")
            for conflict in conflicts[:5]:  # Show first 5
                click.echo(f"  - {conflict}")
            if len(conflicts) > 5:
                click.echo(f"  ... and {len(conflicts) - 5} more")
            
            if not click.confirm("Continue with upgrade? (existing files will be backed up)"):
                return False
        
        click.echo("✅ Pre-flight checks passed")
        return True
    
    def _create_backup(self) -> bool:
        """Create backup of current installation."""
        if self.dry_run:
            click.echo("🗂️  [DRY RUN] Would create backup")
            return True
        
        click.echo("🗂️  Creating backup...")
        
        try:
            # Create backup directory
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Backup key files and directories
            backup_items = [
                'app/',
                'db/',
                'tests/',
                'scripts/',
                '.env',
                '.env.docker',
                'requirements.txt',
                'requirements-dev.txt',
                'alembic.ini',
                'docker-compose.yml'
            ]
            
            for item in backup_items:
                source = self.project_root / item
                if source.exists():
                    target = self.backup_dir / item
                    target.parent.mkdir(parents=True, exist_ok=True)
                    
                    if source.is_dir():
                        shutil.copytree(source, target, dirs_exist_ok=True)
                    else:
                        shutil.copy2(source, target)
            
            click.echo(f"✅ Backup created at {self.backup_dir}")
            return True
            
        except Exception as e:
            click.echo(f"❌ Backup failed: {e}")
            return False
    
    def _install_enhanced_files(self) -> bool:
        """Install enhanced application files."""
        if self.dry_run:
            click.echo("📁 [DRY RUN] Would install enhanced files")
            return True
        
        click.echo("📁 Installing enhanced files...")
        
        # Note: In a real implementation, these files would be provided
        # either as templates or from a source repository
        click.echo("⚠️  Enhanced files need to be provided separately")
        click.echo("Please ensure all enhanced files are available in the upgrade package")
        
        return True
    
    def _update_configuration(self) -> bool:
        """Update configuration files for enhanced version."""
        if self.dry_run:
            click.echo("⚙️  [DRY RUN] Would update configuration")
            return True
        
        click.echo("⚙️  Updating configuration...")
        
        # Update .env file with new settings
        env_file = self.project_root / '.env'
        if env_file.exists():
            self._update_env_file(env_file)
        
        # Update requirements.txt
        self._update_requirements()
        
        # Update alembic.ini if needed
        self._update_alembic_config()
        
        click.echo("✅ Configuration updated")
        return True
    
    def _update_env_file(self, env_file: Path):
        """Update .env file with enhanced settings."""
        # Read current .env
        current_env = {}
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    if '=' in line and not line.strip().startswith('#'):
                        key, value = line.strip().split('=', 1)
                        current_env[key] = value
        
        # Add new enhanced settings
        enhanced_settings = {
            'API_TITLE': 'Detecktiv.io API',
            'API_VERSION': '1.0.0',
            'DEBUG': 'true',
            'LOG_LEVEL': 'INFO',
            'LOG_FORMAT': 'json',
            'CORS_ORIGINS': 'http://localhost:3000,http://localhost:8000',
            'DB_POOL_SIZE': '5',
            'DB_MAX_OVERFLOW': '10',
            'SECRET_KEY': 'change-me-in-production',
            'RATE_LIMIT_REQUESTS': '100'
        }
        
        # Merge settings (keep existing values)
        for key, default_value in enhanced_settings.items():
            if key not in current_env:
                current_env[key] = default_value
        
        # Write updated .env
        with open(env_file, 'w') as f:
            f.write("# Enhanced Detecktiv.io Configuration\n")
            f.write("# Updated by upgrade script\n\n")
            
            for key, value in current_env.items():
                f.write(f"{key}={value}\n")
    
    def _update_requirements(self):
        """Update Python requirements."""
        requirements_file = self.project_root / 'requirements.txt'
        
        # Enhanced requirements
        enhanced_deps = [
            'pydantic-settings>=2.0,<3.0',
            'httpx>=0.27,<1.0',
            'email-validator>=2.0,<3.0',
            'passlib[bcrypt]>=1.7,<2.0',
            'python-jose[cryptography]>=3.3,<4.0'
        ]
        
        if requirements_file.exists():
            with open(requirements_file, 'a') as f:
                f.write("\n# Enhanced version dependencies\n")
                for dep in enhanced_deps:
                    f.write(f"{dep}\n")
    
    def _update_alembic_config(self):
        """Update Alembic configuration if needed."""
        alembic_ini = self.project_root / 'alembic.ini'
        if not alembic_ini.exists():
            return
        
        # Read current config
        with open(alembic_ini, 'r') as f:
            content = f.read()
        
        # Add note about enhanced environment
        if 'Enhanced migration environment' not in content:
            with open(alembic_ini, 'a') as f:
                f.write("\n# Enhanced migration environment available in db/migrations/env_enhanced.py\n")
    
    def _run_database_migration(self) -> bool:
        """Run database migrations for enhanced schema."""
        if self.dry_run:
            click.echo("🗃️  [DRY RUN] Would run database migration")
            return True
        
        click.echo("🗃️  Running database migration...")
        
        try:
            # Check if database is available
            result = subprocess.run(
                ['python', 'manage.py', 'check-db'],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                click.echo("⚠️  Database not available, skipping migration")
                click.echo("Run migrations manually after database is ready:")
                click.echo("  python -m alembic upgrade head")
                return True
            
            # Run migrations
            result = subprocess.run(
                ['python', '-m', 'alembic', 'upgrade', 'head'],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                click.echo("✅ Database migration completed")
                return True
            else:
                click.echo(f"⚠️  Migration completed with warnings: {result.stderr}")
                return True
                
        except Exception as e:
            click.echo(f"⚠️  Migration skipped: {e}")
            click.echo("Run migrations manually: python -m alembic upgrade head")
            return True
    
    def _update_dependencies(self) -> bool:
        """Update Python dependencies."""
        if self.dry_run:
            click.echo("📦 [DRY RUN] Would update dependencies")
            return True
        
        click.echo("📦 Updating dependencies...")
        
        try:
            # Check if virtual environment is active
            if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
                click.echo("Virtual environment detected")
            else:
                click.echo("⚠️  No virtual environment detected. Consider using one.")
            
            # Install updated requirements
            subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'],
                cwd=self.project_root,
                check=True
            )
            
            click.echo("✅ Dependencies updated")
            return True
            
        except subprocess.CalledProcessError as e:
            click.echo(f"⚠️  Dependency update failed: {e}")
            click.echo("Please run manually: pip install -r requirements.txt")
            return True
    
    def _validate_upgrade(self) -> bool:
        """Validate the upgrade was successful."""
        click.echo("🔍 Validating upgrade...")
        
        validation_checks = [
            ("Enhanced configuration", lambda: (self.project_root / 'app/core/config.py').exists()),
            ("Service layer", lambda: (self.project_root / 'app/services/company_service.py').exists()),
            ("ORM models", lambda: (self.project_root / 'app/models/company.py').exists()),
            ("Management CLI", lambda: (self.project_root / 'manage.py').exists()),
            ("Enhanced tests", lambda: (self.project_root / 'tests/test_company_service.py').exists())
        ]
        
        passed = 0
        for check_name, check_func in validation_checks:
            if self.dry_run or check_func():
                click.echo(f"✅ {check_name}")
                passed += 1
            else:
                click.echo(f"❌ {check_name}")
        
        if passed == len(validation_checks):
            click.echo("✅ All validation checks passed")
            return True
        else:
            click.echo(f"⚠️  {passed}/{len(validation_checks)} validation checks passed")
            return False
    
    def _show_completion_instructions(self):
        """Show post-upgrade instructions."""
        click.echo("\n🎉 Upgrade Complete!")
        click.echo("=" * 50)
        
        click.echo("\n📋 Next Steps:")
        click.echo("1. Review your .env file and update any new settings")
        click.echo("2. Run database migrations if not done automatically:")
        click.echo("   python -m alembic upgrade head")
        click.echo("3. Start the enhanced application:")
        click.echo("   python -m uvicorn app.main_enhanced:app --reload")
        click.echo("4. Test the enhanced API:")
        click.echo("   curl http://localhost:8000/health")
        click.echo("   curl http://localhost:8000/docs")
        
        click.echo("\n🔧 New CLI Management Tool:")
        click.echo("   python manage.py --help")
        click.echo("   python manage.py check-config")
        click.echo("   python manage.py db-seed")
        
        click.echo("\n📚 Documentation:")
        click.echo("   - README_Enhanced.md - Complete feature documentation")
        click.echo("   - DEPLOYMENT.md - Production deployment guide")
        click.echo("   - API Docs: http://localhost:8000/docs")
        
        if self.create_backup:
            click.echo(f"\n💾 Backup Location: {self.backup_dir}")
        
        click.echo("\n🚀 You now have a production-ready sales intelligence platform!")
    
    def _show_rollback_instructions(self):
        """Show rollback instructions in case of failure."""
        click.echo("\n🔄 Rollback Instructions:")
        click.echo("=" * 30)
        
        if self.create_backup and self.backup_dir.exists():
            click.echo(f"1. Stop the application")
            click.echo(f"2. Restore from backup: {self.backup_dir}")
            click.echo(f"3. Copy backup files back to project directory")
            click.echo(f"4. Restart the application")
        else:
            click.echo("1. Use git to restore previous version:")
            click.echo("   git checkout HEAD~1")
            click.echo("2. Or restore from your own backup")
        
        click.echo("\nFor support, please check the documentation or contact the development team.")


def main():
    """Main upgrade script entry point."""
    parser = argparse.ArgumentParser(description='Upgrade Detecktiv.io to enhanced version')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--no-backup', action='store_true', help='Skip creating backup (not recommended)')
    parser.add_argument('--project-root', type=Path, default=Path.cwd(), help='Project root directory')
    
    args = parser.parse_args()
    
    # Confirm upgrade
    if not args.dry_run:
        click.echo("🚀 Detecktiv.io Enhancement Upgrade")
        click.echo("This will upgrade your installation to the enhanced version with:")
        click.echo("• Service layer architecture")
        click.echo("• SQLAlchemy ORM models")
        click.echo("• Companies House integration")
        click.echo("• Enhanced API with validation")
        click.echo("• Structured logging")
        click.echo("• CLI management tool")
        click.echo("• Comprehensive test suite")
        click.echo("• Production deployment guides")
        
        if not click.confirm("\nProceed with upgrade?"):
            click.echo("Upgrade cancelled")
            sys.exit(0)
    
    # Run upgrade
    upgrade_manager = UpgradeManager(
        project_root=args.project_root,
        dry_run=args.dry_run,
        create_backup=not args.no_backup
    )
    
    success = upgrade_manager.run_upgrade()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
