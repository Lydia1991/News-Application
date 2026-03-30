# News Application

A Django-based news publishing platform with user roles, REST API, Sphinx documentation, and Docker support.

## Features
- User registration and authentication (Reader, Journalist, Editor)
- Article, Newsletter, and Publisher management
- REST API endpoints
- Sphinx-generated documentation (see `docs/`)
- Containerized with Docker

## Getting Started

### 1. Clone the Repository
```
git clone https://github.com/Lydia1991/News-Application.git
cd News-Application
```

### 2. Run Locally with Virtual Environment
1. Create and activate a virtual environment:
   - Windows:
     ```
     python -m venv .venv
     .venv\Scripts\activate
     ```
   - macOS/Linux:
     ```
     python3 -m venv .venv
     source .venv/bin/activate
     ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Apply migrations and run the server:
   ```
   python manage.py migrate
   python manage.py runserver
   ```

### 3. Run with Docker
1. Build the Docker image:
   ```
   docker build -t news-app .
   ```
2. Run the container:
   ```
   docker run -p 8000:8000 news-app
   ```

### 4. Documentation
- Build Sphinx docs:
  ```
  .venv\Scripts\python.exe -m sphinx -b html docs\source docs\build\html
  ```
- Open `docs/build/html/index.html` in your browser.

## Security
**Do not commit secrets (passwords, API keys, etc.) to the repository.**
- Use environment variables or a `.env` file for sensitive settings.
- For marking, you may provide a temporary text file with credentials, but remove it before making the repo public.

## License
MIT
