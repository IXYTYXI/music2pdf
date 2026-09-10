"""Persist connection addresses locally and secrets in an OS credential vault."""
import hashlib
import json
import sys
from pathlib import Path

PROFILE = Path(__file__).resolve().parent / 'data/cloud-profile.json'
SERVICE = 'Music2PDF.R2'


def vault():
    # Select OS implementations explicitly; never fall back to plaintext keyrings.
    if sys.platform == 'darwin':
        from keyring.backends.macOS import Keyring
    elif sys.platform == 'win32':
        from keyring.backends.Windows import WinVaultKeyring as Keyring
    else:
        from keyring.backends.SecretService import Keyring
    return Keyring()


def account(link):
    return hashlib.sha256(link.encode()).hexdigest()


def profile():
    if not PROFILE.exists(): return None
    return json.loads(PROFILE.read_text(encoding='utf-8'))


def save(link, access, secret):
    try:
        vault().set_password(SERVICE, account(link), json.dumps({'access': access, 'secret': secret}))
        PROFILE.parent.mkdir(parents=True, exist_ok=True)
        temp = PROFILE.with_suffix('.tmp')
        temp.write_text(json.dumps({'link': link}), encoding='utf-8')
        temp.replace(PROFILE)
    except Exception:
        raise ValueError('无法保存到系统凭据库，请解锁钥匙串或检查系统凭据服务；未使用明文保存。') from None


def load(link):
    try:
        raw = vault().get_password(SERVICE, account(link))
        if not raw: raise ValueError()
        data = json.loads(raw)
        return data['access'], data['secret']
    except Exception:
        raise ValueError('保存的凭据不可用，请解锁系统凭据库或重新输入并保存。') from None


def forget():
    p = profile()
    if not p: return
    try:
        store = vault()
        if store.get_password(SERVICE, account(p['link'])) is not None:
            store.delete_password(SERVICE, account(p['link']))
        PROFILE.unlink(missing_ok=True)
    except Exception:
        raise ValueError('删除凭据失败，请解锁系统凭据库后重试。') from None
