# Napino MES Project Structure

napino_mes/
├── config/                  # Django project configuration (settings, urls, wsgi)
│   ├── settings.py          # Main project settings
│   ├── urls.py              # Root URL routing
│   └── wsgi.py              # WSGI entry point for web servers
├── core/                    # Main application logic
│   ├── admin.py             # Admin interface configuration
│   ├── authentication.py    # Custom authentication classes
│   ├── management/          # Custom manage.py commands
│   ├── migrations/          # Database schema migrations
│   ├── models.py            # Database models (Serial, Part, Balancing records)
│   ├── templatetags/        # Custom template tags and filters
│   ├── urls.py              # App-specific URL routing
│   └── views.py             # Main logic (TODO: Refactor heavy logic into services/helpers)
├── templates/               # All HTML templates
│   ├── admin/               # Django admin template overrides
│   └── core/                # Core app templates (dashboard, markings, logs)
├── static/                  # Shared static assets
│   ├── css/                 # Global stylesheets
│   ├── js/                  # Global JavaScript files
│   └── images/              # Project images and logos
├── docs/                    # Project documentation (future)
├── AI_CONTEXT.md            # AI agent orientation and context file
├── README.md                # Project overview and setup instructions
├── walkthrough.md           # Step-by-step guide for developers
├── requirements.txt         # Python dependencies
├── manage.py                # Django command-line utility
└── .env.example             # Example environment variables
