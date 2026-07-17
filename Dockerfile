FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
COPY vendor/ vendor/
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput


EXPOSE 80

CMD ["gunicorn", "lumivis.wsgi:application", "--bind", "0.0.0.0:80"]
