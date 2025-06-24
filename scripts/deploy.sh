#!/bin/bash

# Trojan Trading Analytics - Production Deployment Script
# This script deploys the complete analytics system with monitoring

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="trojan-trading-analytics"
DOCKER_COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env"
BACKUP_DIR="./backups"
LOG_FILE="./deployment.log"

# Functions
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check if Docker Compose is installed
    if ! command -v docker-compose &> /dev/null; then
        error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check if .env file exists
    if [[ ! -f "$ENV_FILE" ]]; then
        error ".env file not found. Please create one based on .env.example"
        exit 1
    fi
    
    # Check if docker-compose.yml exists
    if [[ ! -f "$DOCKER_COMPOSE_FILE" ]]; then
        error "docker-compose.yml not found."
        exit 1
    fi
    
    # Check if Helius API key is set
    if ! grep -q "HELIUS_API_KEY=" "$ENV_FILE" || grep -q "HELIUS_API_KEY=$" "$ENV_FILE"; then
        error "HELIUS_API_KEY is not set in .env file. Please add your Helius API key."
        exit 1
    fi
    
    success "All prerequisites met!"
}

# Create backup
create_backup() {
    log "Creating backup..."
    
    mkdir -p "$BACKUP_DIR"
    BACKUP_NAME="backup_$(date +%Y%m%d_%H%M%S)"
    
    # Backup database if running
    if docker-compose ps postgres | grep -q "Up"; then
        log "Backing up database..."
        docker-compose exec -T postgres pg_dump -U postgres market_data > "$BACKUP_DIR/${BACKUP_NAME}_database.sql"
        success "Database backup created: $BACKUP_DIR/${BACKUP_NAME}_database.sql"
    fi
    
    # Backup configuration files
    tar -czf "$BACKUP_DIR/${BACKUP_NAME}_config.tar.gz" \
        "$ENV_FILE" \
        "$DOCKER_COMPOSE_FILE" \
        "docker/" \
        "scripts/" \
        2>/dev/null || true
    
    success "Configuration backup created: $BACKUP_DIR/${BACKUP_NAME}_config.tar.gz"
}

# Setup environment
setup_environment() {
    log "Setting up environment..."
    
    # Create necessary directories
    mkdir -p logs data/postgres data/redis data/kafka data/prometheus data/grafana
    
    # Set proper permissions
    chmod 755 logs data
    
    # Ensure Helius configuration is valid
    source "$ENV_FILE"
    if [[ -z "${HELIUS_API_KEY:-}" ]]; then
        error "HELIUS_API_KEY environment variable is not set"
        exit 1
    fi
    
    success "Environment setup complete!"
}

# Deploy services
deploy_services() {
    log "Deploying services..."
    
    # Pull latest images
    log "Pulling Docker images..."
    docker-compose pull
    
    # Build custom images
    log "Building application images..."
    docker-compose build --no-cache
    
    # Start infrastructure services first
    log "Starting infrastructure services..."
    docker-compose up -d postgres redis zookeeper kafka
    
    # Wait for infrastructure to be ready
    log "Waiting for infrastructure services to be ready..."
    sleep 30
    
    # Start application services
    log "Starting application services..."
    docker-compose up -d api kafka-consumer celery-worker celery-beat
    
    # Start monitoring services
    log "Starting monitoring services..."
    docker-compose up -d prometheus grafana flower
    
    # Start optional services
    log "Starting optional services..."
    docker-compose up -d adminer kafka-ui
    
    success "All services deployed!"
}

# Health checks
perform_health_checks() {
    log "Performing health checks..."
    
    # Wait for services to start
    sleep 30
    
    # Check API health
    log "Checking API health..."
    for i in {1..30}; do
        if curl -f -s http://localhost:8000/health > /dev/null; then
            success "API is healthy!"
            break
        fi
        if [[ $i -eq 30 ]]; then
            error "API health check failed after 30 attempts"
            return 1
        fi
        log "Waiting for API to be ready... (attempt $i/30)"
        sleep 10
    done
    
    # Check database connection
    log "Checking database connection..."
    if docker-compose exec -T postgres pg_isready -U postgres > /dev/null; then
        success "Database is ready!"
    else
        error "Database health check failed"
        return 1
    fi
    
    # Check Redis connection
    log "Checking Redis connection..."
    if docker-compose exec -T redis redis-cli ping | grep -q "PONG"; then
        success "Redis is ready!"
    else
        error "Redis health check failed"
        return 1
    fi
    
    # Check Kafka
    log "Checking Kafka..."
    if docker-compose exec -T kafka kafka-topics --bootstrap-server localhost:29092 --list > /dev/null; then
        success "Kafka is ready!"
    else
        error "Kafka health check failed"
        return 1
    fi
    
    # Test API endpoints
    log "Testing API endpoints..."
    
    # Test health endpoint
    if curl -f -s http://localhost:8000/health | grep -q "ok"; then
        success "Health endpoint working!"
    else
        warning "Health endpoint test failed"
    fi
    
    # Test metrics endpoint
    if curl -f -s http://localhost:8000/metrics/app > /dev/null; then
        success "Metrics endpoint working!"
    else
        warning "Metrics endpoint test failed"
    fi
    
    success "Health checks completed!"
}

# Setup monitoring
setup_monitoring() {
    log "Setting up monitoring..."
    
    # Wait for Grafana to start
    log "Waiting for Grafana to start..."
    for i in {1..20}; do
        if curl -f -s http://localhost:3000/api/health > /dev/null; then
            break
        fi
        sleep 5
    done
    
    # Import Grafana dashboards (if any)
    if [[ -d "docker/grafana/dashboards" ]]; then
        log "Grafana dashboards will be auto-imported from docker/grafana/dashboards/"
    fi
    
    # Check Prometheus
    if curl -f -s http://localhost:9090/-/healthy > /dev/null; then
        success "Prometheus is healthy!"
    else
        warning "Prometheus health check failed"
    fi
    
    success "Monitoring setup complete!"
}

# Display deployment status
show_deployment_status() {
    log "Deployment Status:"
    echo ""
    echo "🚀 Trojan Trading Analytics Deployed Successfully!"
    echo ""
    echo "📊 Service URLs:"
    echo "  • API Documentation: http://localhost:8000/docs"
    echo "  • Analytics Dashboard: http://localhost:8000/ui"
    echo "  • Health Check: http://localhost:8000/health"
    echo "  • Metrics: http://localhost:8000/metrics"
    echo ""
    echo "🔧 Management URLs:"
    echo "  • Grafana (admin/admin): http://localhost:3000"
    echo "  • Prometheus: http://localhost:9090"
    echo "  • Celery Flower (admin/admin): http://localhost:5555"
    echo "  • Kafka UI: http://localhost:8081"
    echo "  • Database Admin: http://localhost:8080"
    echo ""
    echo "📈 Key Features:"
    echo "  • Real-time token analytics"
    echo "  • WebSocket streaming"
    echo "  • Helius integration"
    echo "  • Performance monitoring"
    echo "  • Background processing"
    echo ""
    echo "🎯 Next Steps:"
    echo "  1. Add tokens for tracking via API or UI"
    echo "  2. Monitor performance in Grafana"
    echo "  3. Check logs: docker-compose logs -f"
    echo "  4. Scale services: docker-compose up -d --scale celery-worker=3"
    echo ""
}

# Show service logs
show_logs() {
    log "Recent service logs:"
    echo ""
    docker-compose logs --tail=20 api
    echo ""
    log "To follow logs in real-time: docker-compose logs -f"
}

# Cleanup function
cleanup_on_exit() {
    if [[ $? -ne 0 ]]; then
        error "Deployment failed! Check logs for details."
        echo ""
        echo "🔧 Troubleshooting:"
        echo "  • Check logs: docker-compose logs"
        echo "  • Check service status: docker-compose ps"
        echo "  • Restart services: docker-compose restart"
        echo "  • Full reset: docker-compose down && docker-compose up -d"
        echo ""
        echo "📋 Common issues:"
        echo "  • Ensure ports 8000, 3000, 5432, 6379, 9092 are available"
        echo "  • Check .env file has valid HELIUS_API_KEY"
        echo "  • Ensure Docker has enough memory (4GB+ recommended)"
    fi
}

# Set trap for cleanup
trap cleanup_on_exit EXIT

# Main deployment flow
main() {
    log "Starting Trojan Trading Analytics deployment..."
    echo ""
    
    # Run deployment steps
    check_prerequisites
    create_backup
    setup_environment
    deploy_services
    perform_health_checks
    setup_monitoring
    
    # Show results
    show_deployment_status
    show_logs
    
    success "🎉 Deployment completed successfully!"
    
    # Remove trap since we completed successfully
    trap - EXIT
}

# Handle command line arguments
case "${1:-deploy}" in
    "deploy")
        main
        ;;
    "stop")
        log "Stopping all services..."
        docker-compose down
        success "All services stopped!"
        ;;
    "restart")
        log "Restarting all services..."
        docker-compose restart
        success "All services restarted!"
        ;;
    "logs")
        docker-compose logs -f
        ;;
    "status")
        docker-compose ps
        ;;
    "backup")
        create_backup
        ;;
    "clean")
        log "Cleaning up deployment..."
        docker-compose down -v
        docker system prune -f
        success "Cleanup completed!"
        ;;
    *)
        echo "Usage: $0 {deploy|stop|restart|logs|status|backup|clean}"
        echo ""
        echo "Commands:"
        echo "  deploy  - Deploy the complete system (default)"
        echo "  stop    - Stop all services"
        echo "  restart - Restart all services"
        echo "  logs    - Show live logs"
        echo "  status  - Show service status"
        echo "  backup  - Create backup"
        echo "  clean   - Remove all containers and volumes"
        exit 1
        ;;
esac 