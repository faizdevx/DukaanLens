"""Store each user's Gemini API key encrypted, never in plain text.

The encryption key is derived from SECRET_KEY. If SECRET_KEY changes, saved API keys
can no longer be read and users must enter them again.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

from .extensions import db
from .models import ApiKey

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def _fernet():
    digest = hashlib.sha256(current_app.config["SECRET_KEY"].encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def can_store_keys():
    """Keys may only be saved when SECRET_KEY is set, otherwise they would be
    unreadable after the next restart (a random key is used when it is missing)."""
    return bool(os.environ.get("SECRET_KEY")) or current_app.config.get("TESTING", False)


def save_key(user_id, api_key, model):
    record = ApiKey.query.filter_by(user_id=user_id).first() or ApiKey(user_id=user_id)
    record.encrypted_key = _fernet().encrypt(api_key.encode()).decode()
    record.key_hint = api_key[-4:]
    record.model = model
    db.session.add(record)
    db.session.commit()


def delete_key(user_id):
    ApiKey.query.filter_by(user_id=user_id).delete()
    db.session.commit()


def get_key_record(user_id):
    return ApiKey.query.filter_by(user_id=user_id).first()


def get_credentials(user_id):
    """Returns (api_key, model) or (None, None). Falls back to GEMINI_API_KEY from the
    environment if the user has not saved a key of their own."""
    record = get_key_record(user_id)
    if record:
        try:
            return _fernet().decrypt(record.encrypted_key.encode()).decode(), record.model
        except InvalidToken:
            return None, None
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key:
        return env_key, DEFAULT_MODEL
    return None, None
