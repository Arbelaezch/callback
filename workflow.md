# Workflow instructions

## To run the development server

1. docker compose up --build

## For making migrations

docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate

docker compose exec backend python manage.py startapp users

docker compose exec backend python manage.py createsuperuser


docker compose exec backend python manage.py check


docker compose exec frontend env | grep API_URL


Need to add the following keys to the lambda function.
ANTHROPIC_API_KEY     = your Anthropic API key
DJANGO_CALLBACK_URL   = https://yourcallbackdomain.com
