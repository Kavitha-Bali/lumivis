FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
COPY vendor/ vendor/
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# collectstatic is NOT run here: static assets now upload to Azure Blob
# Storage (see products/storage_backends.AzureStaticStorage), which needs
# AZURE_CONNECTION_STRING — a runtime secret that isn't available at image
# build time (.env is excluded from the build context, see .dockerignore).
# Run `python manage.py collectstatic --noinput` as a separate deploy step
# (CI job / k8s Job / manually) whenever static assets change, from an
# environment that has the real Azure credentials.

EXPOSE 80

CMD ["gunicorn", "lumivis.wsgi:application", "--bind", "0.0.0.0:80"]
