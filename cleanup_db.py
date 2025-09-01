#!/usr/bin/env python3
"""
Database cleanup and setup script for detecktiv.io
Use this if you have database issues from the old setup
"""
import os
import sys
import time
from pathlib import Path
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

def load_environment():
    """Load environment variables."""
    env_file = Path(".env")
    if env_file.exists():
        load_dotenv(env_file)
        print("✅ Loaded .env file")
    else:
        print("⚠️  No .env file found")

def get_db_config():
    """Get database configuration from environment."""
    return {
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', ''),
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('POSTGRES_PORT', '5432')),
        'database': os.getenv('POSTGRES_DB', 'detecktiv'),
    }

def test_postgres_connection():
    """Test if we can connect to PostgreSQL server (not specific database)."""
    config = get_db_config()
    try:
        # Connect to postgres system database first
        conn = psycopg2.connect(
            user=config['user'],
            password=config['password'],
            host=config['host'],
            port=config['port'],
            database='postgres'
        )
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Cannot connect to PostgreSQL server: {e}")
        return False

def database_exists(db_name):
    """Check if a database exists."""
    config = get_db_config()
    try:
        conn = psycopg2.connect(
            user=config['user'],
            password=config['password'],
            host=config['host'],
            port=config['port'],
            database='postgres'
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (db_name,)
            )
            exists = cur.fetchone() is not None
        
        conn.close()
        return exists
    except Exception as e:
        print(f"❌ Error checking database existence: {e}")
        return False

def create_database(db_name):
    """Create the database if it doesn't exist."""
    config = get_db_config()
    try:
        conn = psycopg2.connect(
            user=config['user'],
            password=config['password'],
            host=config['host'],
            port=config['port'],
            database='postgres'
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{db_name}"')
        
        conn.close()
        print(f"✅ Created database '{db_name}'")
        return True
    except psycopg2.errors.DuplicateDatabase:
        print(f"✅ Database '{db_name}' already exists")
        return True
    except Exception as e:
        print(f"❌ Failed to create database: {e}")
        return False

def drop_database(db_name):
    """Drop the database (use with caution!)."""
    config = get_db_config()
    try:
        conn = psycopg2.connect(
            user=config['user'],
            password=config['password'],
            host=config['host'],
            port=config['port'],
            database='postgres'
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        # Terminate active connections to the database
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = %s
                  AND pid <> pg_backend_pid()
            """, (db_name,))
            
            cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        
        conn.close()
        print(f"✅ Dropped database '{db_name}'")
        return True
    except Exception as e:
        print(f"❌ Failed to drop database: {e}")
        return False

def clean_alembic_table():
    """Clean up the alembic_version table if needed."""
    config = get_db_config()
    try:
        conn = psycopg2.connect(**config)
        with conn.cursor() as cur:
            # Check if alembic_version table exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'alembic_version'
                )
            """)
            
            if cur.fetchone()[0]:
                cur.execute("DROP TABLE alembic_version")
                conn.commit()
                print("✅ Cleaned up alembic_version table")
            else:
                print("✅ No alembic_version table to clean up")
        
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Failed to clean alembic table: {e}")
        return False

def reset_database():
    """Complete database reset - USE WITH CAUTION!"""
    config = get_db_config()
    db_name = config['database']
    
    print(f"🔄 Resetting database '{db_name}'...")
    print("⚠️  This will destroy all data!")
    
    response = input("Are you sure? Type 'yes' to continue: ")
    if response.lower() != 'yes':
        print("❌ Aborted")
        return False
    
    # Drop and recreate database
    if not drop_database(db_name):
        return False
    
    time.sleep(1)  # Brief pause
    
    if not create_database(db_name):
        return False
    
    print("✅ Database reset complete")
    return True

def setup_fresh_database():
    """Set up a fresh database."""
    config = get_db_config()
    db_name = config['database']
    
    print(f"🔧 Setting up fresh database '{db_name}'...")
    
    # Create database if it doesn't exist
    if not database_exists(db_name):
        if not create_database(db_name):
            return False
    else:
        print(f"✅ Database '{db_name}' already exists")
    
    return True

def run_migrations():
    """Run Alembic migrations."""
    print("🔄 Running migrations...")
    
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print("✅ Migrations completed")
            return True
        else:
            print(f"❌ Migration failed:")
            print(result.stdout)
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Migration error: {e}")
        return False

def main():
    """Main cleanup and setup process."""
    print("=" * 60)
    print("🔍 detecktiv.io Database Cleanup & Setup")
    print("=" * 60)
    
    # Load environment
    load_environment()
    
    # Test PostgreSQL connection
    if not test_postgres_connection():
        print("\n💡 Make sure PostgreSQL is running:")
        print("   docker compose up -d postgres")
        print("   # or")
        print("   sudo systemctl start postgresql")
        sys.exit(1)
    
    print("✅ PostgreSQL server is running")
    
    # Show menu
    print("\nWhat would you like to do?")
    print("1. Fresh setup (create database if needed)")
    print("2. Reset database (⚠️  destroys all data)")
    print("3. Clean up Alembic table only")
    print("4. Run migrations only")
    print("5. Exit")
    
    choice = input("\nEnter choice (1-5): ").strip()
    
    if choice == "1":
        if setup_fresh_database():
            run_migrations()
    elif choice == "2":
        if reset_database():
            run_migrations()
    elif choice == "3":
        clean_alembic_table()
    elif choice == "4":
        run_migrations()
    elif choice == "5":
        print("👋 Goodbye!")
    else:
        print("❌ Invalid choice")
        sys.exit(1)
    
    print("\n✅ Done! Try running: python start.py")

if __name__ == "__main__":
    main()
