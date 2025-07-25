class MongoClient:
    def __init__(self, uri=None, *args, **kwargs):
        self.uri = uri
        self._dbs = {}
    def __getitem__(self, name):
        return self._dbs.setdefault(name, {})
