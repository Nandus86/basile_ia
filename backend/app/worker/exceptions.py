class DirectPayloadException(BaseException):
    """Exception raised to instantly stop agents and return the direct workflow payload."""
    def __init__(self, payload):
        self.payload = payload
