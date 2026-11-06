"""Trusted local TOML policy; tool requests cannot modify permission grants."""
import hashlib
import json
import os
import re
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .errors import ComputerError
from .policy import _validated_paths, allowed_applications, normalize_executable

PROTECTED = re.compile(r'password|passcode|credential|secret|token|credit|card number|payment|purchase|checkout|delete|remove|transfer|submit|send|sign.?in|log.?in|install|administrator|security setting', re.IGNORECASE)
ACTIONS = {'click', 'type', 'press_keys', 'scroll', 'focus', 'move', 'double_click', 'drag'}
SAFE_KEYS = {'TAB', 'SHIFT+TAB', 'ARROWUP', 'ARROWDOWN', 'ARROWLEFT', 'ARROWRIGHT', 'HOME', 'END', 'PAGEUP', 'PAGEDOWN', 'ESCAPE'}


def protected(name: str, role: str = '') -> bool:
    return bool(PROTECTED.search(name) or 'password' in role.casefold())


def origin_of(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError
        port = parsed.port
        host = parsed.hostname.lower()
        if ':' in host:
            host = f'[{host}]'
        suffix = '' if port is None or (parsed.scheme, port) in (('http', 80), ('https', 443)) else f':{port}'
        return f'{parsed.scheme}://{host}{suffix}'
    except ValueError:
        raise ComputerError('INVALID_ARGUMENT', 'An HTTP(S) URL without embedded credentials is required.') from None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Permissions(StrictModel):
    inspect: bool = True
    screenshot: bool = False
    interact: bool = False
    navigate: bool = False
    focus: bool = False
    fallback: bool = False


class Limits(StrictModel):
    timeout_seconds: float = Field(default=5, ge=0.5, le=10)
    max_depth: int = Field(default=6, ge=1, le=10)
    max_elements: int = Field(default=200, ge=1, le=500)
    max_text_length: int = Field(default=2000, ge=1, le=5000)


class DesktopPolicy(StrictModel):
    allowed_apps: list[str] = Field(default_factory=list, max_length=32)

    @field_validator('allowed_apps')
    @classmethod
    def validate_apps(cls, value):
        return sorted(_validated_paths(value))


class BrowserPolicy(StrictModel):
    allowed_origins: list[str] = Field(default_factory=list, max_length=32)
    headless: bool = True

    @field_validator('allowed_origins')
    @classmethod
    def validate_origins(cls, value):
        result = []
        for entry in value:
            parsed = urlsplit(entry)
            if parsed.path not in ('', '/') or parsed.query or parsed.fragment:
                raise ValueError('Configure origins, not URL paths.')
            result.append(origin_of(entry))
        return sorted(set(result))


class ControlGrant(StrictModel):
    target: str
    role: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    actions: list[str] = Field(min_length=1, max_length=8)

    @field_validator('target')
    @classmethod
    def validate_target(cls, value):
        if value.startswith(('http://', 'https://')):
            parsed = urlsplit(value)
            if parsed.path not in ('', '/') or parsed.query or parsed.fragment:
                raise ValueError('Control grants use an origin, not a URL path.')
            return origin_of(value)
        return next(iter(_validated_paths([value])))

    @field_validator('actions')
    @classmethod
    def validate_actions(cls, value):
        if not set(value) <= ACTIONS:
            raise ValueError('Unknown action grant.')
        return value


class OperatorPolicy(StrictModel):
    permissions: Permissions = Field(default_factory=Permissions)
    limits: Limits = Field(default_factory=Limits)
    desktop: DesktopPolicy = Field(default_factory=DesktopPolicy)
    browser: BrowserPolicy = Field(default_factory=BrowserPolicy)
    grants: list[ControlGrant] = Field(default_factory=list, max_length=100)

    def apps(self) -> frozenset[str]:
        return allowed_applications() | frozenset(self.desktop.allowed_apps)

    def revision(self) -> str:
        """Fingerprint effective rules, including legacy local application grants."""
        values = self.model_dump(mode='json')
        values['effective_apps'] = sorted(self.apps())
        return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def check_control(self, scope: str, role: str, name: str, action: str) -> None:
        if not self.permissions.interact or protected(name, role):
            raise ComputerError('PERMISSION_DENIED', 'Interaction is disabled or the control is protected.')
        canonical = origin_of(scope) if scope.startswith(('http://', 'https://')) else normalize_executable(scope)
        for grant in self.grants:
            expected = origin_of(grant.target) if grant.target.startswith(('http://', 'https://')) else normalize_executable(grant.target)
            if expected == canonical and grant.role.casefold() == role.casefold() and grant.name == name and action in grant.actions:
                return
        raise ComputerError('PERMISSION_DENIED', 'No local operator grant matches this control and action.')


class PolicySource:
    def __init__(self, path: Path | None = None):
        self.path = path

    def load(self) -> OperatorPolicy:
        try:
            if self.path is None:
                policy = OperatorPolicy()
            else:
                if self.path.stat().st_size > 1_000_000:
                    raise ValueError('Policy is too large.')
                policy = OperatorPolicy.model_validate(tomllib.loads(self.path.read_text(encoding='utf-8')))
            if os.environ.get('COMPUTER_USE_ALLOW_SCREENSHOTS') == '1':
                policy.permissions.screenshot = True
            return policy
        except (OSError, ValueError, ValidationError, ToolError):
            raise ComputerError('INVALID_POLICY', 'The local policy file could not be loaded or validated.') from None
