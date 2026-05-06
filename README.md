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
## Docker Compose Usage

To build and run the application using Docker Compose:

1. Ensure Docker and Docker Compose are installed.
2. From the project root, run:
	```
	docker-compose up --build
	```
	This will build the images and start both the Django app and MariaDB database.

3. The web application will be available at http://localhost:8000

To stop the services:
```
docker-compose down
```

You can also use the following for manual Docker usage:
- Build: `docker build -t news-app .`
- Run: `docker run -p 8000:8000 news-app`

### 6. Build Sphinx documentation (optional)
Sphinx and related tools are now in `requirements-dev.txt`.
To build documentation locally:
```
pip install -r requirements-dev.txt
cd docs
sphinx-build -b html source build/html
```
## License
MIT
