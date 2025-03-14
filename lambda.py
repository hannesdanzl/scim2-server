import awsgi
from cli import get_app

def lambda_handler(event, context):
    """ run the request in AWS Lambda """
    return awsgi.response(_app, event, context, base64_content_types={"image/png"})

# initialize the app, backend and args. make sure to run the server locally first
_app, _backend, _args = get_app()

if __name__ == "__main__":
    _event = {
        "resource": "/v2/users",
        "path": "/v2/users",
        "httpMethod": "GET",
        "headers": {
            "accept": "application/json",
            "content-type": "application/json"
        },
        "queryStringParameters": None,
        "requestContext": {
            "path": "/test",
            "httpMethod": "GET",
            "identity": {
            "sourceIp": "123.123.123.123",
            "userAgent": "PostmanRuntime/7.29.2"
            }
        },
        "body": None,
        "isBase64Encoded": False
    }

    _context = {}
    result = lambda_handler(event=_event, context=_context)
    print(result)
