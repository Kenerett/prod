from waitress import serve
from school_project.wsgi import application  # если твой проект называется school_project

if __name__ == "__main__":
    serve(application, host="0.0.0.0", port=8000)