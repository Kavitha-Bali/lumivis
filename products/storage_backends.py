import mimetypes
from functools import lru_cache

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContentSettings
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.urls import reverse


@lru_cache(maxsize=1)
def _blob_service_client():
    return BlobServiceClient.from_connection_string(settings.AZURE_CONNECTION_STRING)


def _blob_path(path):
    """Namespace every blob under AZURE_MEDIA_PREFIX (e.g. 'lumivis/media/') —
    the container is shared across multiple Samanyastra apps."""
    prefix = settings.AZURE_MEDIA_PREFIX.strip('/')
    path = path.lstrip('/')
    return f"{prefix}/{path}" if prefix else path


def _blob_client(path):
    return _blob_service_client().get_blob_client(container=settings.AZURE_CONTAINER, blob=_blob_path(path))


class AzureMediaStorage(Storage):
    """
    Stores media files in Azure Blob Storage. `.url()` never resolves to the
    real blob URL — it always points back at our own /media/<path> proxy
    view (products.views.serve_media), which streams the blob content
    through Django so the Azure storage account is never exposed to clients.
    """

    def _open(self, name, mode='rb'):
        download = _blob_client(name).download_blob()
        return ContentFile(download.readall(), name=name)

    def _save(self, name, content):
        content_type = getattr(content.file, 'content_type', None) \
            or mimetypes.guess_type(name)[0] \
            or 'application/octet-stream'
        _blob_client(name).upload_blob(
            content,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
        return name

    def exists(self, name):
        try:
            _blob_client(name).get_blob_properties()
            return True
        except ResourceNotFoundError:
            return False

    def delete(self, name):
        try:
            _blob_client(name).delete_blob()
        except ResourceNotFoundError:
            pass

    def size(self, name):
        return _blob_client(name).get_blob_properties().size

    def url(self, name, parameters=None, expire=None):
        return reverse('serve_media', kwargs={'path': name})
