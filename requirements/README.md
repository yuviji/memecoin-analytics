# Requirements Structure

This directory contains the Python package requirements for the Trojan Trading Analytics project.

## File Structure

```
requirements/
├── base.txt      # Core dependencies (production-ready)
├── dev.txt       # Development and testing dependencies
├── prod.txt      # Production-only dependencies (monitoring, security)
└── README.md     # This file
```

## Usage

### Production Installation
```bash
pip install -r requirements/prod.txt
```

### Development Installation
```bash
pip install -r requirements/dev.txt
```

### Base Dependencies Only
```bash
pip install -r requirements/base.txt
```

## Dependencies Overview

### Base Dependencies (`base.txt`)
- **FastAPI**: Web framework
- **SQLAlchemy**: Database ORM
- **Redis**: Caching
- **Kafka**: Message streaming
- **Solana**: Blockchain integration
- **Celery**: Background tasks
- **Prometheus**: Monitoring

### Development Dependencies (`dev.txt`)
- **pytest**: Testing framework
- **black**: Code formatting
- **flake8**: Linting
- **mypy**: Type checking
- **pre-commit**: Git hooks

### Production Dependencies (`prod.txt`)
- **gunicorn**: WSGI server
- **sentry-sdk**: Error tracking
- **psutil**: System monitoring

## Docker Usage

The Dockerfile uses the production requirements:
```dockerfile
COPY requirements/ requirements/
RUN pip install -r requirements/prod.txt
```

## Main Requirements File

The root `requirements.txt` file simply references the base requirements:
```
-r requirements/base.txt
```

This provides compatibility with tools that expect a `requirements.txt` file in the project root. 