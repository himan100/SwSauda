# Docker Setup Guide for SwSauda

This guide explains how to set up MongoDB and Redis using Docker for the SwSauda project.

## Prerequisites

- Docker installed on your system
- Docker Compose installed (usually comes with Docker Desktop)

## Services Included

The `docker-compose.yml` file sets up the following services:

### Core Services
1. **MongoDB** (Port 27017)
   - Image: mongo:7.0
   - Container name: `swsauda_mongodb`
   - Credentials: admin/admin123
   - Persistent data storage with Docker volumes
   - Backup folder mounted at `/backups`

2. **Redis** (Port 6379)
   - Image: redis:7.2-alpine
   - Container name: `swsauda_redis`
   - Persistent data storage with AOF (Append-Only File)
   - Memory limit: 256MB with LRU eviction policy

### Optional Management UIs
3. **MongoDB Express** (Port 8081)
   - Web-based MongoDB admin interface
   - Access: http://localhost:8081
   - Login: admin/admin123

4. **Redis Commander** (Port 8082)
   - Web-based Redis admin interface
   - Access: http://localhost:8082

## Quick Start

### 1. Start All Services
```bash
docker-compose up -d
```

This will:
- Download the required Docker images (first time only)
- Create the containers
- Start MongoDB and Redis in the background
- Start the optional management UIs

### 2. Check Service Status
```bash
docker-compose ps
```

All services should show as "healthy" after a few seconds.

### 3. View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f mongodb
docker-compose logs -f redis
```

### 4. Stop Services
```bash
docker-compose down
```

### 5. Stop and Remove All Data
```bash
docker-compose down -v
```
**Warning**: This will delete all MongoDB and Redis data!

## Starting Only Core Services

If you don't want the management UIs:

```bash
docker-compose up -d mongodb redis
```

## Environment Configuration

The `.env` file has been configured to work with Docker services:

```env
# MongoDB with authentication
MONGODB_URL=mongodb://admin:admin123@localhost:27017

# Redis
REDIS_URL=redis://localhost:6379
```

## Data Persistence

Data is stored in Docker volumes:
- `mongodb_data`: MongoDB database files
- `mongodb_config`: MongoDB configuration
- `redis_data`: Redis AOF files

These volumes persist even when containers are stopped.

## Backup Directory

The `./Backups` directory is mounted to MongoDB container at `/backups`, allowing:
- Database backups to be stored on your host machine
- Easy access to backup files from both host and container

## Accessing Services

### MongoDB
```bash
# Using mongosh from host (if installed)
mongosh mongodb://admin:admin123@localhost:27017

# Using mongosh from container
docker exec -it swsauda_mongodb mongosh -u admin -p admin123

# Using MongoDB Express UI
# Open browser: http://localhost:8081
```

### Redis
```bash
# Using redis-cli from host (if installed)
redis-cli

# Using redis-cli from container
docker exec -it swsauda_redis redis-cli

# Using Redis Commander UI
# Open browser: http://localhost:8082
```

## Health Checks

Both services have health checks configured:
- **MongoDB**: Pings the database every 10 seconds
- **Redis**: Pings the Redis server every 10 seconds

Check health status:
```bash
docker inspect swsauda_mongodb | grep -A 10 Health
docker inspect swsauda_redis | grep -A 10 Health
```

## Troubleshooting

### Services won't start
```bash
# Check if ports are already in use
sudo netstat -tlnp | grep -E '27017|6379|8081|8082'

# Or use lsof
lsof -i :27017
lsof -i :6379
```

### MongoDB authentication issues
Make sure your `.env` file has the correct credentials:
```env
MONGODB_URL=mongodb://admin:admin123@localhost:27017
```

### Reset everything
```bash
# Stop and remove containers, networks, and volumes
docker-compose down -v

# Start fresh
docker-compose up -d
```

### View container resource usage
```bash
docker stats swsauda_mongodb swsauda_redis
```

## Production Considerations

For production deployment:

1. **Change default credentials** in `docker-compose.yml`
2. **Use Docker secrets** for sensitive data
3. **Configure backup strategy** for MongoDB
4. **Increase memory limits** for Redis if needed
5. **Use external volumes** for better performance
6. **Disable management UIs** or restrict access
7. **Enable MongoDB authentication** for all databases
8. **Configure Redis persistence** settings based on requirements

## Useful Commands

```bash
# Restart a specific service
docker-compose restart mongodb

# Rebuild and restart services
docker-compose up -d --build

# Execute command in container
docker exec -it swsauda_mongodb bash
docker exec -it swsauda_redis sh

# Copy files to/from container
docker cp swsauda_mongodb:/data/db/backup.tar.gz ./backup.tar.gz

# View volume details
docker volume inspect swsauda_mongodb_data

# Clean up unused Docker resources
docker system prune -a --volumes
```

## Integration with SwSauda Application

The application is configured to automatically connect to these Docker services. Simply:

1. Start Docker services: `docker-compose up -d`
2. Install Python dependencies: `pip install -r requirements.txt`
3. Run the application: `python main.py` or `uvicorn main:app --reload`

The application will connect to MongoDB and Redis using the URLs specified in `.env`.
