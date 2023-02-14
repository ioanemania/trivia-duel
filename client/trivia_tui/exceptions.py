class RefreshTokenExpiredError(Exception):
    pass


class ResponseError(Exception):
    def __init__(self, error: dict):
        self.error = error


class UnAuthenticatedRequestError(Exception):
    pass
