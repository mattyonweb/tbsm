# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TBSM is a Django web application for trading bonds and securities management. It implements a financial contract system with timed payments, corporation management, and tradeable asset tracking.

## Core Architecture

The project follows Django's app-based structure with four main apps:

- **accounts**: Custom user authentication using email-based login (`CustomUser` model)
- **contracts**: Financial contract system with timed repayments (`Contract`, `RepaymentTemplate`, `TimelyAction`, `PaymentScheduler`)
- **corporations**: Entity management for trading participants (`Corporation` model with payment/bankruptcy logic)
- **things**: Tradeable assets system (`Thing`, `Material`, `Currency`, `Ownership` models with mutual exclusion constraints)

## Key Models & Relationships

- `Contract` represents financial instruments with multiple `RepaymentTemplate` schedules
- `TimelyAction` defines when payments occur (every X days, exactly in Y days, at specific date)
- `PaymentScheduler` tracks individual payment due dates and status
- `Thing` is a union type for materials, contracts, or currencies (enforced via check constraint)
- `Ownership` tracks who owns what and how much

## Development Commands

**Start development server:**
```bash
python manage.py runserver
```

**Database operations:**
```bash
python manage.py makemigrations
python manage.py migrate
```

**Create superuser:**
```bash
python manage.py createsuperuser
```

**Run tests:**
```bash
python manage.py test
```

**Run specific test module:**
```bash
python manage.py test contracts.test_payment_execution
```

**Run with Hypothesis verbose output:**
```bash
python manage.py test contracts.test_payment_execution --verbosity=2
```

**Django shell:**
```bash
python manage.py shell
```

## Dependencies & Environment

- Uses `uv` for package management (see `pyproject.toml`)
- Django 5.2.4+ required
- SQLite database (development)
- Python 3.13+
- Testing: Hypothesis for property-based testing, freezegun for time manipulation

## Testing

The project uses property-based testing with Hypothesis to generate random but meaningful test data:

- `contracts/test_payment_execution.py` contains comprehensive tests for the payment execution system
- Tests use freezegun to control time flow for testing scheduled payments
- Hypothesis strategies generate random corporations, contracts, and payment schedules
- Tests verify ownership transfers, bankruptcy handling, and payment status tracking

## Important Implementation Details

- Custom user model uses email as username field (defined in `settings.py`)
- Contract activation triggers automatic `PaymentScheduler` creation
- Corporation bankruptcy is tracked via timestamp field
- Payment execution logic is partially implemented in `contracts/tasks.py` (incomplete)
- Database constraints enforce mutual exclusion in `Thing` model

## Useful trivia

- To calculate a percentage, use `percentage` from `common/calculations.py`


## Authentication & Settings

- Uses Django's default session-based authentication
- Debug mode enabled in development
- Custom user model: `accounts.CustomUser`
- Admin interface available at `/admin/`