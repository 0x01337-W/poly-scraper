import os
from functools import lru_cache
from opensearchpy import OpenSearch


@lru_cache(maxsize=1)
def get_client() -> OpenSearch:
    url = os.getenv("OPENSEARCH_URL", "https://opensearch:9200")
    user = os.getenv("OPENSEARCH_USER", "")
    password = os.getenv("OPENSEARCH_PASSWORD", "")
    auth = (user, password) if user and password else None

    client = OpenSearch(
        hosts=[url],
        http_auth=auth,
        verify_certs=False,
        ssl_show_warn=False,
        timeout=30,
        max_retries=3,
        retry_on_timeout=True,
    )
    return client

