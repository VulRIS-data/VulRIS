class BaseService:
    def find(self, value):
        return value


class UserService(BaseService):
    def __init__(self, repo=None):
        self.repo = repo

    def find(self, value):
        return self.normalize(value)

    def normalize(self, value):
        return value.strip()
