from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    """
    Wrap every DRF exception in the project's standard envelope:
      { "status": "error", "message": "...", "errors": {...} }
    """
    response = exception_handler(exc, context)

    if response is None:
        return Response(
            {'status': 'error', 'message': 'An unexpected server error occurred.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    payload = {'status': 'error'}

    # Validation errors come as a dict of field → [messages]
    if isinstance(response.data, dict):
        if 'detail' in response.data:
            payload['message'] = str(response.data['detail'])
        else:
            payload['message'] = 'Validation failed.'
            payload['errors']  = response.data
    else:
        payload['message'] = str(response.data)

    response.data = payload
    return response
