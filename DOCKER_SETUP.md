# Docker Setup for SwSauda

This project is containerized using Docker and Docker Compose.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) installed
- [Docker Compose](https://docs.docker.com/compose/install/) installed

## Quick Start

We have provided a helper script `manage_docker.sh` to make it easy to manage the application.

1.  **Make the script executable** (if not already):
    ```bash
    chmod +x manage_docker.sh
    ```

2.  **Start the application**:
    ```bash
    ./manage_docker.sh start
    ```
    The application will be available at: [http://localhost:8500](http://localhost:8500)
    API Documentation: [http://localhost:8500/docs](http://localhost:8500/docs)

3.  **Stop the application**:
    ```bash
    ./manage_docker.sh stop
    ```

## Commands

The `manage_docker.sh` script supports the following commands:

- `start`: Builds and starts the containers in the background.
- `stop`: Stops the running containers.
- `restart`: Restarts the containers.
- `reset`: Stops and removes containers and networks (preserves database data).
- `clean`: **WARNING** - Stops and removes everything including database data (volumes) and images. Use this for a fresh start.
- `logs`: Follows the logs of the running containers.

## Services

- **Web (FastAPI)**: Runs on port 8500 (internal 8000).
- **MongoDB**: Database service (internal port 27017).
- **Redis**: Caching service (internal port 6379).

## Configuration

Environment variables are defined in `docker-compose.yml`. You can also create a `.env` file if needed, but defaults are set in the compose file.
