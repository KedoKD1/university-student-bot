# LabBase

LabBase is an educational platform built for Medical Laboratory Technology students.

The Telegram bot provides students with organized access to academic materials, summaries, drawings, schedules, exam dates, grades, search tools, and other student services from one place.

## Main Features

### Student Features

- Student stage selection
- Subject browsing
- Theoretical materials
- Practical materials
- Approved summaries
- Student drawings
- University grades
- Class schedules
- Exam dates
- Search
- Student settings
- Notifications

### Administration

LabBase includes an administration system for managing the platform's academic content and settings.

- Subject management
- File management
- Summary management
- Drawing management
- Schedule management
- Grade management
- Exam date management
- Notification management
- Content bundle descriptions
- Bot settings
- Admin and role management
- Permission-based access control

## Permissions

The administration system uses role-based and database-driven permissions.

Supported administrative roles include:

- Owner
- Admin
- Moderator

Administrators and moderators only receive the permissions assigned to their roles, while the Owner has full administrative access.

Administrative conversation state is isolated by user and chat to prevent operations in different chats from interfering with each other.

## Technology

- Python
- python-telegram-bot
- Supabase
- PostgreSQL
- GitHub
- Railway

## Project Structure

- `bot.py` — Application entry point and handler registration
- `bot/handlers/` — Student and administration handlers
- `bot/keyboards/` — Telegram inline keyboards
- `bot/database/` — Supabase database integration
- `bot/services/` — Internal services
- `bot/utils/` — Configuration, permissions, security, and utility modules
- `tests/` — Automated security, routing, regression, and isolation tests

## Security

Sensitive credentials must be stored in environment variables.

Never commit real API keys, bot tokens, passwords, or other secrets to the repository.

Administrative actions are protected by permission checks, callback guards, and conversation ownership controls.

## Deployment

LabBase is deployed using Railway and connected to the GitHub repository for deployment.

Database services are provided by Supabase.

## Project Status

LabBase is currently under active development and testing.

The current development focus is stability, security, administration tools, academic content management, and the student experience.
