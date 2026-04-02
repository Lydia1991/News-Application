# News Application

## Overview
A Django-based news publishing platform with user authentication, article management, newsletters, and Sphinx documentation.

## Features
- User registration, login, and permissions
- Article creation, editing, approval, and deletion
- Newsletter management
- REST API with DRF
- Sphinx documentation (see docs/)
- Docker support

## Setup

### 1. Clone the repository
```
git clone https://github.com/Lydia1991/News-Application.git
cd News-Application
```

### 2. Create and activate a virtual environment
```
python -m venv .venv
.venv\Scripts\activate  # On Windows
```

### 3. Install dependencies
```
pip install -r requirements.txt
```

### 4. Apply migrations
```
python manage.py migrate
```

### 5. Run the development server
```
python manage.py runserver
```

### 6. Build Sphinx documentation
```
cd docs
sphinx-build -b html source build/html
```

## Docker Usage
- Build: `docker build -t news-app .`
- Run: `docker run -p 8000:8000 news-app`

## Notes
- Sphinx HTML output is ignored by git (see .gitignore).
- For static/media files, see the static/ and media/ folders.

## License
MIT
