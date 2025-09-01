# detecktiv.io - Quick Start Guide

> **Fixed and Ready to Run!** This guide gets you up and running in under 10 minutes.

## 🎯 What Was Fixed

The main issues preventing startup were:

1. **Import Path Confusion** - Simplified to a single database connection approach
2. **Missing Dependencies** - Updated requirements files with all needed packages  
3. **Complex Test Setup** - Streamlined test configuration
4. **Database Connection Issues** - Robust connection handling with proper error messages
5. **Environment Configuration** - Clear, complete .env setup

## 🚀 Quick Start (Choose Your Path)

### Option A: Using the New Startup Script (Recommended)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env
# Edit .env with your database credentials

# 3. Start everything with diagnostics
python start.py
```

The startup script will:
- ✅ Check all dependencies
- ✅ Test database connection  
- ✅ Run migrations automatically
- ✅ Start the API with helpful URLs
- ❌ Show clear error messages if anything fails

### Option B: Manual Step-by-Step

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env
# Edit .env - see configuration section below

# 3. Start database (if using Docker)
docker compose up -d postgres

# 4. Run migrations
python -m alembic upgrade head

# 5. Start the API
python -m uvicorn app.main:app --reload --port 8000
```

## ⚙️ Environment Configuration

Edit your `.env` file with these settings:

```bash
# For local development (database running on your machine)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-password-here
POSTGRES_DB=detecktiv
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# For Docker Compose (database in container)
POSTGRES_USER=postgres  
POSTGRES_PASSWORD=your-password-here
POSTGRES_DB=detecktiv
POSTGRES_HOST=postgres  # <- Use container name
POSTGRES_PORT=5432
```

## 🧪 Running Tests

```bash
# Set up test environment
export RUN_DB_TESTS=1
export POSTGRES_PASSWORD=your-password

# Run all tests
python -m pytest -v

# Run just the API tests
python -m pytest tests/test_companies.py -v

# Run with the task runner
./task test
```

## 📋 Verification Steps

Once running, verify everything works:

1. **Health Check**: http://localhost:8000/health
2. **Database Health**: http://localhost:8000/health/db  
3. **API Documentation**: http://localhost:8000/docs
4. **Create a Company**: 
   ```bash
   curl -X POST "http://localhost:8000/companies" \
        -H "Content-Type: application/json" \
        -d '{"name": "Test Company", "website": "https://example.com"}'
   ```

## 🐛 Troubleshooting

### "Database connection failed"

**Problem**: Can't connect to PostgreSQL

**Solutions**:
```bash
# Check if PostgreSQL is running
docker compose ps
# or
sudo systemctl status postgresql

# Start PostgreSQL with Docker
docker compose up -d postgres

# Test connection manually
psql -h localhost -p 5432 -U postgres -d detecktiv

# Check your .env file has correct credentials
cat .env
```

### "Import Error" or "Module Not Found"

**Problem**: Missing Python dependencies

**Solutions**:
```bash
# Install dependencies
pip install -r requirements.txt

# If you're using virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

### "Migration Failed"

**Problem**: Alembic migrations not working

**Solutions**:
```bash
# Check Alembic can see the database
python -m alembic current

# Reset migrations (⚠️ destroys data)
python -m alembic downgrade base
python -m alembic upgrade head

# Check migration files exist
ls db/migrations/versions/
```

### "Port Already in Use"

**Problem**: Port 8000 is busy

**Solutions**:
```bash
# Use a different port
python -m uvicorn app.main:app --port 8001

# Or kill process using port 8000
lsof -ti:8000 | xargs kill -9  # Linux/Mac
netstat -ano | findstr :8000   # Windows
```

## 🔧 Development Tools

### Using the Task Runner

```powershell
# Start the stack
./task up

# Run migrations
./task migrate

# Run tests
./task test

# View logs
./task logs

# Connect to database
./task psql
```

### Database Management

```bash
# Connect to database
./task psql

# Create a backup
./task backup

# Restore latest backup (⚠️ destructive)
./task restore-latest

# View current migration
./task db-current
```

## 📊 API Usage Examples

### Create a Company
```bash
curl -X POST "http://localhost:8000/companies" \
  -H "Content-Type: application/json" \
  -d '{"name": "Acme Corp", "website": "https://acme.com"}'
```

### Get All Companies
```bash
curl "http://localhost:8000/companies"
```

### Get Specific Company
```bash
curl "http://localhost:8000/companies/1"
```

## 🐳 Docker Commands

### Development Stack
```bash
# Start everything
docker compose up -d

# View logs
docker compose logs -f

# Stop everything  
docker compose down

# Rebuild images
docker compose build
```

### Production Stack
```bash
# Use production config
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## 🧪 Test Database Setup

For running tests with database:

```bash
# Set environment variables
export RUN_DB_TESTS=1
export POSTGRES_PASSWORD=your-password
export POSTGRES_HOST=127.0.0.1

# Run tests
python -m pytest -v
```

## 💡 Performance Tips

1. **Use connection pooling** in production (already configured)
2. **Enable query logging** for debugging: set `echo=True` in `get_engine()`
3. **Monitor with pgAdmin**: http://localhost:5050 (when running Docker stack)
4. **Check slow queries**: Query `pg_stat_statements` view

## 🔒 Security Notes

- **Never commit** real passwords to git
- **Use environment variables** for secrets in production
- **Enable CORS** properly for your domain
- **Use HTTPS** in production
- **Implement rate limiting** for public APIs

## 📈 Next Steps

Once you have the basic setup working:

1. **Add authentication** (JWT or session-based)
2. **Implement rate limiting** 
3. **Add logging and monitoring**
4. **Set up CI/CD pipelines**
5. **Configure production deployment**

## 🆘 Still Having Issues?

1. **Run the diagnostic script**: `python start.py` 
2. **Check the logs**: `docker compose logs api`
3. **Verify environment**: Use the debug endpoint at `/debug/env` (when `DEBUG=true`)
4. **Test each component**: Database → Migrations → Import → API

The new setup is much more robust and should give you clear error messages for any remaining issues!
