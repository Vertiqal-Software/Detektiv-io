# Detecktiv.io MVP - Demo Setup Guide

🚀 **Complete Containerized Demo Ready!**

## Quick Start (5 minutes)

### Prerequisites
- Docker Desktop installed and running
- Ports 80, 4173, 5432, and 8000 available

### 1. Launch the System
```bash
# In the project root directory
docker-compose up -d
```

### 2. Verify System Health
```bash
python health_check.py
```

### 3. Access the Application
- **Main Application**: http://localhost
- **Direct Frontend**: http://localhost:4173
- **API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

### 4. Demo Login
- **Email**: admin@detecktiv.io
- **Password**: any password (mock authentication)

---

## System Architecture

### 🐳 Docker Containers
- **detecktiv-postgres**: PostgreSQL database (port 5432)
- **detecktiv-api**: FastAPI backend (port 8000)
- **detecktiv-frontend**: React/Vite frontend (port 4173)
- **detecktiv-caddy**: Reverse proxy (port 80)

### 🔄 Failover System
- **Primary**: Real API endpoints with PostgreSQL data
- **Fallback**: Rich mock data for seamless demo experience
- **Auto-switching**: Frontend automatically falls back to mock data if API fails

---

## Demo Features

### ✅ Working Functionality
- **Authentication**: Mock login system with multiple user types
- **Companies Management**: View, search, and manage company data
- **User Management**: Full CRUD operations for users
- **Analytics Dashboard**: Rich visualizations and metrics
- **Companies House Integration**: Mock UK company search
- **Responsive UI**: Modern, professional interface

### 📊 Demo Data
- **5 Sample Companies**: Realistic UK tech companies with full details
- **3 Sample Users**: Admin, regular users with different permissions
- **Analytics Data**: Pipeline metrics, lead tracking, revenue data
- **Companies House Data**: Mock UK company registry responses

---

## Troubleshooting

### Common Issues

#### 1. Port Conflicts
```bash
# Check if ports are in use
netstat -an | findstr "80\|8000\|4173\|5432"

# Stop other services if needed
docker-compose down
```

#### 2. Container Health Issues
```bash
# Check container status
docker ps

# Restart specific container
docker restart detecktiv-api

# View logs
docker logs detecktiv-api
```

#### 3. Frontend Not Loading
```bash
# Rebuild frontend container
docker-compose up --build frontend
```

### 🔧 Manual Recovery
If containers fail to start automatically:

```bash
# 1. Stop everything
docker-compose down

# 2. Clean up
docker system prune -f

# 3. Rebuild and start
docker-compose up --build -d

# 4. Wait for health checks
sleep 30

# 5. Verify
python health_check.py
```

---

## Development Mode

For development with hot reloading:

```bash
# Stop containerized frontend
docker stop detecktiv-frontend

# Start local development server
cd frontend
npm install
npm run dev
# Frontend available at http://localhost:5173
```

---

## Production Deployment

### Environment Variables
Key variables in `.env.docker`:
- `POSTGRES_PASSWORD`: Database password
- `CORS_ALLOW_ORIGINS`: Allowed frontend origins
- `VITE_USE_MOCK_DATA`: Enable/disable mock data fallback

### Security Notes
- Change default passwords in production
- Configure proper CORS origins
- Use HTTPS in production (Caddy supports automatic TLS)
- Review JWT configuration for production use

---

## Demo Script

### 1. Login Flow
1. Navigate to http://localhost
2. Enter email: `admin@detecktiv.io`
3. Enter any password
4. Show successful login and navigation

### 2. Companies Management
1. Navigate to Companies section
2. Show list of companies with search/filter
3. Click on company to view details
4. Demonstrate responsive design

### 3. Analytics Dashboard
1. Navigate to Analytics
2. Show metrics cards (companies, leads, pipeline)
3. Demonstrate interactive charts
4. Show CSV export functionality

### 4. User Management
1. Navigate to Users section
2. Show user list with permissions
3. Demonstrate role-based access

### 5. System Resilience
1. Stop API container: `docker stop detecktiv-api`
2. Show frontend still works with mock data
3. Restart API: `docker start detecktiv-api`
4. Show real data returns

---

## Technical Highlights

### 🏗️ Architecture Benefits
- **Microservices**: Independently scalable components
- **Containerization**: Consistent deployment across environments
- **API-First**: RESTful API with OpenAPI documentation
- **Modern Frontend**: React 18 with TypeScript, Tailwind CSS
- **Reverse Proxy**: Caddy for routing and potential TLS termination

### 🔒 Security Features
- JWT-based authentication
- CORS protection
- SQL injection prevention (SQLAlchemy ORM)
- XSS protection (React escaping)
- Security headers via Caddy

### 📈 Performance Features
- Database connection pooling
- Frontend build optimization
- Container health checks
- Automatic failover to mock data
- Efficient API pagination

---

## Support

For issues or questions:
1. Check container logs: `docker logs [container-name]`
2. Run health check: `python health_check.py`
3. Review this documentation
4. Check Docker Desktop for container status

**System Status**: ✅ Ready for Professional Demo