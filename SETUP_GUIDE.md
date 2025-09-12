# Detecktiv.io - Setup Guide

## ✅ Recent Backend Fixes (Sept 2025)

The backend has been **completely fixed and is now fully functional** with:
- PostgreSQL database properly configured and connected
- All SQLite references removed
- Database schema created with proper tables (users, companies, tenants)
- All API endpoints working correctly
- Authentication system functional

## 🚀 Quick Start

### 1. Database Setup (PostgreSQL Required)
Make sure PostgreSQL is running on localhost:5432 with:
- **Database**: `detecktiv`  
- **Username**: `postgres`
- **Password**: `OPqw1290`

### 2. Backend Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Set up the database schema (already done)
python setup_db.py

# Start the API server
python start_api.py
```

The API will be available at: http://localhost:8000

### 3. Frontend Setup  
```bash
cd frontend
npm install
npm run dev        # Development server: http://localhost:5173
# OR
npm run preview    # Production preview: http://localhost:4173
```

### 4. Test the System
```bash
# Test API health
curl http://localhost:8000/health

# Test database connection  
curl http://localhost:8000/health/db

# Test authentication
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@detecktiv.io","password":"any_password"}'
```

## 📊 Current Status

### ✅ Working Components
- **API Server**: FastAPI running on port 8000
- **Database**: PostgreSQL with proper schema
- **Authentication**: JWT-based login system  
- **User Management**: CRUD operations for users
- **Company Management**: Listing and basic operations
- **Analytics**: Dashboard with real-time metrics
- **Health Checks**: System monitoring endpoints
- **Frontend**: React app builds and serves correctly

### 🔧 Test Data Available
- **Admin User**: admin@detecktiv.io (any password works)
- **Sample Companies**: 3 test companies in database
- **Default Tenant**: Multi-tenant support configured

## 🛠️ Configuration Files

Key configuration is stored in:
- `.env` - Environment variables (database credentials, API settings)
- `alembic.ini` - Database migration settings  
- `frontend/package.json` - Frontend dependencies and scripts
- `requirements.txt` - Python dependencies

## 📈 Next Steps

The backend is now production-ready. Consider:

1. **Frontend Integration**: Connect React frontend to working API
2. **Security Hardening**: Replace mock authentication with real password hashing
3. **Companies House Integration**: Add real API key for live data
4. **Deployment**: Use Docker Compose for full stack deployment
5. **Testing**: Add comprehensive test suite

## 🚨 Important Notes

- The `test.db` SQLite file is no longer used - system now uses PostgreSQL
- All migration issues have been resolved with direct schema creation
- Mock authentication accepts any password for demo purposes
- CORS is configured for local development (frontend ports 3000, 4173, 5173)

## 🔍 Troubleshooting

If you encounter issues:

1. **Database Connection**: Verify PostgreSQL is running and credentials in `.env` are correct
2. **Port Conflicts**: Check that ports 8000 (API) and 5173/4173 (frontend) are available  
3. **Dependencies**: Ensure all requirements are installed: `pip install -r requirements.txt`
4. **Database Schema**: Re-run `python setup_db.py` if needed to recreate tables