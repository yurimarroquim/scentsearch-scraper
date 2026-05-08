import logging
import base64
from typing import Optional

import requests

from config.settings import WP_URL, WP_USERNAME, WP_APP_PASSWORD, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


class WordPressClient:
    def __init__(self, url: str = None, username: str = None, app_password: str = None):
        self.base_url = (url or WP_URL).rstrip("/")
        self.username = username or WP_USERNAME
        self.app_password = app_password or WP_APP_PASSWORD
        self.api_url = f"{self.base_url}/wp-json/wp/v2"

        credentials = f"{self.username}:{self.app_password}"
        token = base64.b64encode(credentials.encode()).decode("utf-8")
        self.headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def is_configured(self) -> bool:
        return bool(self.base_url and self.username and self.app_password)

    def test_connection(self) -> bool:
        if not self.is_configured():
            logger.warning("WordPress is not configured")
            return False
        try:
            response = self.session.get(
                f"{self.api_url}/users/me",
                timeout=REQUEST_TIMEOUT,
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"WordPress connection test failed: {e}")
            return False

    def get_posts(self, per_page: int = 10, page: int = 1) -> list[dict]:
        try:
            response = self.session.get(
                f"{self.api_url}/posts",
                params={"per_page": per_page, "page": page},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching posts: {e}")
            return []

    def get_post(self, post_id: int) -> Optional[dict]:
        try:
            response = self.session.get(
                f"{self.api_url}/posts/{post_id}",
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching post {post_id}: {e}")
            return None

    def create_post(self, title: str, content: str, status: str = "draft",
                    categories: list[int] = None, tags: list[int] = None,
                    meta: dict = None) -> Optional[dict]:
        payload = {
            "title": title,
            "content": content,
            "status": status,
        }
        if categories:
            payload["categories"] = categories
        if tags:
            payload["tags"] = tags
        if meta:
            payload["meta"] = meta

        try:
            response = self.session.post(
                f"{self.api_url}/posts",
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            post = response.json()
            logger.info(f"Created WordPress post: {post['id']} - {title[:50]}")
            return post
        except Exception as e:
            logger.error(f"Error creating post '{title[:50]}': {e}")
            return None

    def update_post(self, post_id: int, title: str = None, content: str = None,
                    status: str = None, meta: dict = None) -> Optional[dict]:
        payload = {}
        if title is not None:
            payload["title"] = title
        if content is not None:
            payload["content"] = content
        if status is not None:
            payload["status"] = status
        if meta is not None:
            payload["meta"] = meta

        try:
            response = self.session.post(
                f"{self.api_url}/posts/{post_id}",
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            logger.info(f"Updated WordPress post: {post_id}")
            return response.json()
        except Exception as e:
            logger.error(f"Error updating post {post_id}: {e}")
            return None

    def delete_post(self, post_id: int, force: bool = False) -> bool:
        try:
            response = self.session.delete(
                f"{self.api_url}/posts/{post_id}",
                params={"force": force},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            logger.info(f"Deleted WordPress post: {post_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting post {post_id}: {e}")
            return False

    def get_or_create_category(self, name: str) -> Optional[int]:
        try:
            response = self.session.get(
                f"{self.api_url}/categories",
                params={"search": name},
                timeout=REQUEST_TIMEOUT,
            )
            data = response.json()
            if data:
                return data[0]["id"]

            response = self.session.post(
                f"{self.api_url}/categories",
                json={"name": name},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()["id"]
        except Exception as e:
            logger.error(f"Error getting/creating category '{name}': {e}")
            return None
