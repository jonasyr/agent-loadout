import pytest

from loadout import secrets

PAT = "ghp_" + "a1B2" * 8
HEX = "0123456789abcdef" * 3
B64 = "Ab3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0eF3hI6kL9n"


@pytest.mark.parametrize("text,leak", [
    (f"npx server-github GITHUB_PERSONAL_ACCESS_TOKEN={PAT}", PAT),
    ("server --api-key=sk-" + "q" * 30, "sk-" + "q" * 30),
    ("server --token abcdefgh12345", "abcdefgh12345"),
    ("https://mcp.example.com/sse?api_key=s3cr3tv4lue99&x=1", "s3cr3tv4lue99"),
    ('{"headers": {"Authorization": "Bearer abcdefghijklmnop"}}', "abcdefghijklmnop"),
    (f"tool --config CACHE={HEX}", HEX),
    (f"tool SEED={B64}", B64),
    ('{"env": {"DB_PASSWORD": "p4ss word;x$y!"}}', "p4ss word;x$y!"),
])
def test_redact_masks_secrets(text, leak):
    out = secrets.redact(text)
    assert leak not in out
    assert "***" in out


def test_redact_leaves_ordinary_text():
    text = "serena start-mcp-server --context=claude-code --project-from-cwd https://x.dev/mcp?page=2"
    assert secrets.redact(text) == text


def test_high_entropy_only_for_keyed_values():
    assert secrets.looks_secret("CACHE", HEX, keyed_arg=True)
    assert not secrets.looks_secret("3", HEX)
    assert not secrets.looks_secret("MODE", "a" * 40, keyed_arg=True)  # no mix of cases/digits
