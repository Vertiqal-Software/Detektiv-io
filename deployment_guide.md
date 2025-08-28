# Detecktiv.io Production Deployment Guide

> **Complete deployment guide for taking Detecktiv.io from development to production.**

## 🎯 Overview

This guide covers deploying Detecktiv.io as a production-ready UK IT sales intelligence platform with:
- High availability and scalability
- Security best practices
- Monitoring and observability
- Automated backups
- CI/CD integration

## 🏗️ Architecture Options

### Option 1: Docker Compose (Recommended for Small-Medium Scale)
- Single server deployment
- Docker containers for all services
- PostgreSQL with persistent volumes
- nginx reverse proxy
- SSL termination with Let's Encrypt

### Option 2: Kubernetes (Enterprise Scale)
- Multi-node cluster deployment
- Auto-scaling capabilities  
- Service mesh integration
- Multiple availability zones

### Option 3: Cloud Native (AWS/Azure/GCP)
- Managed database services
- Container orchestration (ECS/AKS/Cloud Run)
- Managed monitoring and logging
- Automatic scaling

## 🚀 Quick Production Setup (Docker Compose)

### 1. Server Requirements

**Minimum Specifications:**
- CPU: 2 vCPU
- RAM: 4GB
- Storage: 50GB SSD
- OS: Ubuntu 20.04+ or CentOS 8+

**Recommended Specifications:**
- CPU: 4 vCPU
- RAM: 8GB
- Storage: 100GB SSD + separate backup volume
- Network: 1Gbps with DDoS protection

### 2. Initial Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker and Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Install nginx
sudo apt install nginx -y

# Install certbot for SSL
sudo apt install certbot python3-certbot-nginx -y
```

### 3. Application Deployment

```bash
# Clone the repository
git clone https://github.com/your-org/detecktiv-io.git
cd detecktiv-io

# Create production environment file
cp .env.example .env
cp .env.docker.example .env.docker

# Configure production settings (see Configuration section below)
nano .env
nano .env.docker
```

### 4. Production Configuration

Create `.env` file with production values:

```bash
# Application Settings
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=your-super-secure-jwt-key-minimum-32-characters-long

# Database (Production)
POSTGRES_USER=detecktiv_prod
POSTGRES_PASSWORD=your-very-strong-database-password-here
POSTGRES_DB=detecktiv_prod
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_SSLMODE=require

# Companies House API
COMPANIES_HOUSE_API_KEY=your-production-companies-house-api-key

# Security
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
RATE_LIMIT_REQUESTS=100

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Email (for notifications - configure SMTP)
SMTP_HOST=smtp.yourdomain.com
SMTP_PORT=587
SMTP_USER=noreply@yourdomain.com
SMTP_PASSWORD=your-smtp-password
SMTP_TLS=true
```

### 5. SSL Certificate Setup

```bash
# Get SSL certificate
sudo certbot --nginx -d yourdomain.com -d api.yourdomain.com

# Test automatic renewal
sudo certbot renew --dry-run
```

### 6. Deploy the Application

```bash
# Deploy with production configuration
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Run database migrations
docker-compose exec api python -m alembic upgrade head

# Create initial admin user (if implementing auth)
docker-compose exec api python manage.py create-admin-user

# Verify deployment
curl https://api.yourdomain.com/health
```

## 🛡️ Security Checklist

### Database Security
- [ ] Use strong passwords (20+ characters)
- [ ] Enable SSL/TLS connections
- [ ] Restrict database access to application only
- [ ] Regular security updates
- [ ] Encrypt database backups

### API Security
- [ ] Use HTTPS only (HTTP redirects)
- [ ] Configure proper CORS origins
- [ ] Implement rate limiting
- [ ] Add security headers
- [ ] Regular dependency updates
- [ ] API key rotation policy

### Infrastructure Security
- [ ] Firewall configuration (only ports 80, 443, 22)
- [ ] SSH key-only authentication
- [ ] Fail2ban for intrusion prevention
- [ ] Regular OS security updates
- [ ] Log monitoring and alerting

### Application Security
```bash
# Run security scan
docker-compose exec api bandit -r app/
docker-compose exec api safety check

# Check for secrets in code
detect-secrets scan --all-files
```

## 📊 Monitoring & Observability

### 1. Application Monitoring

Add monitoring stack to `docker-compose.prod.yml`:

```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/usr/share/prometheus/console_libraries'
      - '--web.console.templates=/usr/share/prometheus/consoles'
    
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - grafana-storage:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=your-grafana-password

volumes:
  grafana-storage:
```

### 2. Log Management

Configure centralized logging:

```yaml
services:
  api:
    logging:
      driver: "json-file"
      options:
        max-size: "200m"
        max-file: "10"
```

### 3. Health Checks

Implement comprehensive health monitoring:

```bash
# Add to crontab
*/5 * * * * curl -f https://api.yourdomain.com/health/ready || echo "API health check failed" | mail -s "Alert" admin@yourdomain.com
```

## 💾 Backup Strategy

### 1. Database Backups

```bash
# Create backup script: backup-db-prod.sh
#!/bin/bash
BACKUP_DIR="/backups/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/detecktiv_prod_$DATE.sql"

mkdir -p $BACKUP_DIR

# Create backup
docker-compose exec -T postgres pg_dump -U detecktiv_prod -d detecktiv_prod > $BACKUP_FILE

# Compress backup
gzip $BACKUP_FILE

# Remove backups older than 30 days
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete

# Upload to cloud storage (optional)
# aws s3 cp $BACKUP_FILE.gz s3://your-backup-bucket/postgres/
```

```bash
# Make executable and add to crontab
chmod +x backup-db-prod.sh
crontab -e
# Add: 0 2 * * * /path/to/backup-db-prod.sh
```

### 2. Application Data Backups

```bash
# Backup application files
tar -czf app-backup-$(date +%Y%m%d).tar.gz \
  --exclude='.git' \
  --exclude='data' \
  --exclude='logs' \
  --exclude='.env' \
  /path/to/detecktiv-io/
```

## 🔄 CI/CD Pipeline

### GitHub Actions Production Deployment

```yaml
# .github/workflows/deploy-prod.yml
name: Production Deployment

on:
  push:
    tags:
      - 'v*'

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Deploy to Production Server
        uses: appleboy/ssh-action@v0.1.5
        with:
          host: ${{ secrets.PROD_HOST }}
          username: ${{ secrets.PROD_USER }}
          key: ${{ secrets.PROD_SSH_KEY }}
          script: |
            cd /opt/detecktiv-io
            git pull origin main
            docker-compose -f docker-compose.yml -f docker-compose.prod.yml pull
            docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
            docker-compose exec -T api python -m alembic upgrade head
```

## 📈 Scaling Considerations

### Horizontal Scaling

```yaml
# docker-compose.scale.yml
services:
  api:
    deploy:
      replicas: 3
  
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - api
```

### Database Scaling

```yaml
# Add read replica for heavy read workloads
services:
  postgres-replica:
    image: postgres:16
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres-replica-data:/var/lib/postgresql/data
```

## 🚨 Troubleshooting

### Common Issues

**1. Database Connection Issues**
```bash
# Check database logs
docker-compose logs postgres

# Test connection
docker-compose exec api python manage.py check-db
```

**2. SSL Certificate Issues**
```bash
# Renew certificates manually
sudo certbot renew --force-renewal

# Check certificate status
sudo certbot certificates
```

**3. Performance Issues**
```bash
# Monitor resource usage
docker stats

# Check application metrics
curl https://api.yourdomain.com/metrics
```

**4. High Memory Usage**
```bash
# Restart services to clear memory
docker-compose restart

# Check for memory leaks
docker-compose exec api python -c "import psutil; print(psutil.virtual_memory())"
```

### Log Analysis

```bash
# View application logs
docker-compose logs -f api

# Search for errors
docker-compose logs api | grep ERROR

# Monitor database performance
docker-compose exec postgres psql -U detecktiv_prod -d detecktiv_prod -c "SELECT * FROM pg_stat_activity;"
```

## 📋 Maintenance Tasks

### Daily Tasks
- [ ] Check application health endpoints
- [ ] Review error logs
- [ ] Monitor disk space usage
- [ ] Verify backup completion

### Weekly Tasks
- [ ] Security updates
- [ ] Performance review
- [ ] Database maintenance (VACUUM, ANALYZE)
- [ ] Log rotation and cleanup

### Monthly Tasks
- [ ] Full backup verification
- [ ] Security audit
- [ ] Dependency updates
- [ ] Capacity planning review

## 🆘 Disaster Recovery

### Backup Restoration

```bash
# Stop application
docker-compose down

# Restore database
gunzip < /backups/detecktiv_prod_20240115_020000.sql.gz | \
docker-compose exec -T postgres psql -U detecktiv_prod -d detecktiv_prod

# Restart application
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Emergency Procedures

1. **Application Down**: Check logs, restart containers, verify database connectivity
2. **Database Issues**: Restore from latest backup, check disk space, restart PostgreSQL
3. **SSL Expiry**: Renew certificates, restart nginx
4. **High Load**: Scale horizontally, optimize queries, add caching

## 📞 Support Contacts

- **Technical Issues**: DevOps team
- **Security Incidents**: Security team  
- **Database Issues**: DBA team
- **Business Critical**: On-call escalation

---

## 📚 Additional Resources

- [PostgreSQL Production Guide](https://www.postgresql.org/docs/current/admin.html)
- [Docker Production Guide](https://docs.docker.com/config/containers/start-containers-automatically/)
- [nginx Security Guide](https://nginx.org/en/docs/http/securing_http.html)
- [Companies House API Documentation](https://developer.company-information.service.gov.uk/)

Remember to customize this deployment for your specific infrastructure and requirements!
