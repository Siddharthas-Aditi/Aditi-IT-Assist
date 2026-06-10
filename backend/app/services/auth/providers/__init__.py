"""Auth providers package."""

from app.services.auth.providers.base import AuthProvider, AuthResult
from app.services.auth.providers.local import LocalAuthProvider
from app.services.auth.providers.saml import SAMLAuthProvider

__all__ = ["AuthProvider", "AuthResult", "LocalAuthProvider", "SAMLAuthProvider"]
