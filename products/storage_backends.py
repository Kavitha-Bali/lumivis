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


def _blob_path(path, prefix=None):
    """Namespace every blob under a prefix (e.g. 'media/', 'static/') —
    the container is shared across multiple Samanyastra apps."""
    prefix = (settings.AZURE_MEDIA_PREFIX if prefix is None else prefix).strip('/')
    path = path.lstrip('/')
    return f"{prefix}/{path}" if prefix else path


def _blob_client(path, prefix=None):
    return _blob_service_client().get_blob_client(container=settings.AZURE_CONTAINER, blob=_blob_path(path, prefix))


class _AzureBlobStorage(Storage):
    """
    Base for Azure Blob-backed storages. `.url()` never resolves to the real
    blob URL — it always points back at our own proxy view, which streams
    the blob content through Django so the Azure storage account is never
    exposed to clients. Subclasses set `prefix_setting` (the settings.py
    name holding the blob path prefix) and `url_name` (the proxy view).
    """

    prefix_setting = None
    url_name = None

    def _client(self, name):
        return _blob_client(name, prefix=getattr(settings, self.prefix_setting))

    def _open(self, name, mode='rb'):
        download = self._client(name).download_blob()
        return ContentFile(download.readall(), name=name)

    def _save(self, name, content):
        content_type = getattr(content.file, 'content_type', None) \
            or mimetypes.guess_type(name)[0] \
            or 'application/octet-stream'
        self._client(name).upload_blob(
            content,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
        return name

    def exists(self, name):
        try:
            self._client(name).get_blob_properties()
            return True
        except ResourceNotFoundError:
            return False

    def delete(self, name):
        try:
            self._client(name).delete_blob()
        except ResourceNotFoundError:
            pass

    def size(self, name):
        return self._client(name).get_blob_properties().size

    def url(self, name, parameters=None, expire=None):
        return reverse(self.url_name, kwargs={'path': name})


class AzureMediaStorage(_AzureBlobStorage):
    """Media uploads — proxied through /media/<path> (products.views.serve_media)."""
    prefix_setting = 'AZURE_MEDIA_PREFIX'
    url_name = 'serve_media'


class AzureStaticStorage(_AzureBlobStorage):
    """Static assets (collectstatic output) — proxied through /static/<path>
    (products.views.serve_static). Same rules as media: nothing is ever
    written to local/pod disk, so replicas and restarts stay stateless."""
    prefix_setting = 'AZURE_STATIC_PREFIX'
    url_name = 'serve_static'
