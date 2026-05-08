import os
import logging
from supabase import create_client, Client

logger = logging.getLogger(__name__)


class SupabaseClient:
    def __init__(self):
        self.url = os.environ.get("SUPABASE_URL")
        self.key = os.environ.get("SUPABASE_KEY")
        self._client: Client = None

    def is_configured(self) -> bool:
        return bool(self.url and self.key)

    def get_client(self) -> Client:
        if not self._client:
            if not self.is_configured():
                raise ValueError("SUPABASE_URL e SUPABASE_KEY não configurados")
            self._client = create_client(self.url, self.key)
        return self._client
