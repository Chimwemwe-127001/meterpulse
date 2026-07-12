# MeterPulse API

Utility Meter Reading, Anomaly Detection & Alert Management System

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 15+

### Installation

```bash
# Clone and enter directory
cd meterpulse

# Create virtual environment
python -m venv venv

# Activate (Windows)
.\venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your settings:
# - DATABASE_URL: Your PostgreSQL connection string
#   (or sqlite:///./meterpulse.db for quick local development)
# - SECRET_KEY: Required — the app refuses to start without it.
#   Generate: python -c "import secrets; print(secrets.token_hex(32))"
# - CORS_ORIGINS: JSON list of allowed frontend origins
```

### Database Setup

```bash
# Run migrations (Alembic is the single schema authority;
# tables are not auto-created at startup)
alembic upgrade head
```

### Run Development Server

```bash
uvicorn app.main:app --reload
```

### Run Tests

```bash
pip install -r requirements-dev.txt
pytest
```

### API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Create new account |
| POST | `/auth/login` | Get JWT token |
| GET | `/auth/me` | Get current user |

### Meters
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/meters` | Register meter |
| GET | `/meters` | List meters |
| GET | `/meters/{id}` | Get meter |
| PUT | `/meters/{id}` | Update meter |
| DELETE | `/meters/{id}` | Delete meter |

### Readings
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/meters/{id}/readings` | Submit reading |
| GET | `/meters/{id}/readings` | List readings |
| GET | `/meters/{id}/readings/summary` | Aggregated data |

### Alerts
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/alerts` | List all alerts |
| GET | `/meters/{id}/alerts` | Meter alerts |
| PATCH | `/alerts/{id}/resolve` | Resolve alert |

## Project Structure

```
meterpulse/
├── app/
│   ├── main.py          # FastAPI application
│   ├── config.py        # Settings management
│   ├── database.py      # SQLAlchemy setup
│   ├── models/          # Database models
│   ├── schemas/         # Pydantic schemas
│   ├── routers/         # API endpoints
│   └── services/        # Business logic
├── migrations/          # Alembic migrations
├── tests/               # Pytest suite
├── requirements.txt
├── .env.example
└── Procfile            # Railway deployment
```

## Access Control

- All meter, reading, and alert endpoints are scoped at the object
  level: operators only see and modify meters they own; admins see all.
- New accounts are always created as operators — admin promotion is a
  separate administrative action, never a registration field.
- Alert resolution is audited (`resolved_by`, `resolved_at`).

## Tech Stack

- **Framework**: FastAPI
- **Database**: PostgreSQL + SQLAlchemy 2.0
- **Auth**: JWT (python-jose) + bcrypt
- **Validation**: Pydantic v2
- **Migrations**: Alembic

## Author

Chimwemwe (Student No. 2022067576)  
University of Zambia, Dept. of Computer Science

---

*Built as portfolio proof of work for HCS Backend Developer Internship*
