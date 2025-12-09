#!/bin/bash

# Define colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print usage
usage() {
    echo "Usage: $0 {start|stop|restart|reset|clean|logs}"
    echo
    echo "Commands:"
    echo "  start   - Build and start the containers in detached mode"
    echo "  stop    - Stop the running containers"
    echo "  restart - Restart the containers"
    echo "  reset   - Stop and remove containers and networks (keeps volumes)"
    echo "  clean   - Stop and remove containers, networks, volumes, and images (Full cleanup)"
    echo "  logs    - View the logs of the containers"
    exit 1
}

# Check if docker compose is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: docker is not installed.${NC}"
    exit 1
fi

# Determine if we should use "docker compose" or "docker-compose"
# User asked for "docker compose", checking availability just in case
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
else
    echo -e "${RED}Error: docker compose (or docker-compose) is not installed.${NC}"
    exit 1
fi

echo -e "${YELLOW}Using command: $DOCKER_COMPOSE_CMD${NC}"

case "$1" in
    start)
        echo -e "${GREEN}Starting application...${NC}"
        $DOCKER_COMPOSE_CMD up -d --build
        echo -e "${GREEN}Application started on port 8500!${NC}"
        ;;
    stop)
        echo -e "${YELLOW}Stopping application...${NC}"
        $DOCKER_COMPOSE_CMD stop
        echo -e "${GREEN}Application stopped.${NC}"
        ;;
    restart)
        echo -e "${YELLOW}Restarting application...${NC}"
        $DOCKER_COMPOSE_CMD restart
        echo -e "${GREEN}Application restarted.${NC}"
        ;;
    reset)
        echo -e "${YELLOW}Resetting application (removing containers/networks)...${NC}"
        $DOCKER_COMPOSE_CMD down
        echo -e "${GREEN}Reset complete. Run './manage_docker.sh start' to start again.${NC}"
        ;;
    clean)
        echo -e "${RED}Cleaning up everything (containers, networks, volumes, images)...${NC}"
        read -p "Are you sure you want to delete all data? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            $DOCKER_COMPOSE_CMD down -v --rmi local --remove-orphans
            echo -e "${GREEN}Cleanup complete.${NC}"
        else
            echo -e "${YELLOW}Cleanup cancelled.${NC}"
        fi
        ;;
    logs)
        $DOCKER_COMPOSE_CMD logs -f
        ;;
    *)
        usage
        ;;
esac
