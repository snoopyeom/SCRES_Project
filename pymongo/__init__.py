"""아주 단순한 pymongo 대체 모듈."""


class Collection:
    """메모리 상의 문서 컬렉션."""

    def __init__(self):
        self._docs = []

    # MongoDB 컬렉션 호환 메서드
    def replace_one(self, filt, doc, upsert=False):
        for i, existing in enumerate(self._docs):
            if all(existing.get(k) == v for k, v in filt.items()):
                self._docs[i] = doc
                return
        if upsert:
            self._docs.append(doc)

    def find_one(self, filt):
        for doc in self._docs:
            if all(doc.get(k) == v for k, v in filt.items()):
                return doc
        return None

    def find(self):
        # 리스트를 그대로 순회하는 제너레이터 반환
        for doc in list(self._docs):
            yield doc


class Database:
    def __init__(self):
        self._cols = {}

    def __getitem__(self, name):
        return self._cols.setdefault(name, Collection())


class MongoClient:
    def __init__(self, uri=None, *args, **kwargs):
        self.uri = uri
        self._dbs = {}

    def __getitem__(self, name):
        return self._dbs.setdefault(name, Database())
