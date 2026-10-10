"""Fix pass 4, secret detection: code lines are not secret values (I1), word-like values under a PASSWORD/SECRET
key are secrets again (M3), a few more secret shapes, the regression baseline and linear time.
Corpora from the re-review 4 (/tmp/claude-1000/rr4/corpus4.py, probe2.py, redos4.py). Fake secrets are built at
runtime so the repo's static scan does not see them."""
import time

import pytest

from loadout import secrets
from test_fix_pass_3 import ALL_INPUTS as ALL_INPUTS_3, EXEMPT as EXEMPT_3, _old_redact

G = "gh" + "p_"

# I1: code, not secret values
CODE_LINES = [
    'api_key = os.getenv("API_KEY", "")',
    'password = getpass.getpass("Password: ")',
    "secret = load_secret(name, default)",
    "token = jwt.encode(payload, key)",
    "password = bcrypt.hashpw(pw, salt)",
    "password = input('Password: ')",
    "auth = HTTPBasicAuth(user, pw)",
    "token = tokens[i]",
    "api_key = cfg['api_key']",
    "password: Optional[str] = None",
    'token = f"Bearer {access}"',
]
# M3: word-like values under a PASSWORD/PASSWD/SECRET key are secrets
M3_SECRETS = ["password: hunter-22", "password: dragon.monkey.42", "MYSQL_ROOT_PASSWORD=rootpass"]
M3_PLACEHOLDERS = ["password: required", "password: optional", "password: none", "secret: null", "password: true",
                   "secret: false", "password: unlimited", "password: changeme", "PASSWORD=CHANGEME",
                   "password: your_password_here", "secret: YOUR_SECRET", "API_KEY=your_api_key_here",
                   "password: ${DB_PASSWORD}", "password: $DB_PASSWORD"]
# extra secret shapes
EXTRA_SECRETS = ['{"password":"Sunshine99"}', "os.environ['OPENAI_API_KEY'] = 'Zx9qQ8wW7eE6rR5tT4yY'", "curl -u admin:S3cretPass https://x",
                 "mysql -u root --password=Sup3rS3cret db", "sshpass -p 'Zx9qQ8wW7eE6' ssh host",
                 "client = Client(api_key='Zx9qQ8wW7eE6rR5tT4yY')"]

# re-review 4 corpus (corpus4.py)
SECRETS_4 = [
    "db:\n  password: Wq7#rT9!kLm2", "  api_token: 'Mx82LpQz0vRt5Yb1'", "client_secret: \"9fK2-pQ8_zR4-wE6\"",
    "aws_secret_access_key: \"AbCdEfGhIjKlMnOpQrStUvWxYz0123456789+/ab\"", "smtp_password: Gr33nApples!",
    "secret: Tr0ub4dor&3", "password: Sunshine99", "password: s3cr3t-p4ss", "password: hunter-22",
    "password: correct-horse-battery", "password: dragon.monkey.42", "password: mypassword123",
    "password: letmein2024", "token: a1b2-c3d4-e5f6-g7h8", "auth_token: 550e8400-e29b-41d4-a716-446655440000",
    "webhook_secret: whsec_abcdefghijklmnop", "slack_token: xox" + "p-1234567890-abcdefghij",
    "DATABASE_PASSWORD=Pa55w0rd!!", "STRIPE_SECRET=sk_live_" + "a" * 24, "JWT_SECRET=supersecretjwtkey",
    "JWT_SECRET=mysupersecretvalue", "SESSION_SECRET=keyboard-cat-2", "REDIS_PASSWORD=foobared1",
    "OPENAI_API_KEY=" + "sk-" + "A1b2" * 6, "MYSQL_ROOT_PASSWORD=rootpass", "MYSQL_ROOT_PASSWORD=r00tpassw0rd",
    "SECRET_KEY_BASE=6f0e5d7c2b1a9f8e7d6c5b4a3f2e1d0c", "NEXTAUTH_SECRET=Zm9vYmFyYmF6cXV4", "DB_PASS='p@ss word'",
    "APP_KEY=base64:Zm9vYmFyYmF6cXV4cXV1eA==", "export GH_TOKEN=" + G + "A" * 36, "PGPASSWORD=mydbpass12",
    "AWS_SESSION_TOKEN=FwoGZXIvYXdzEBYaDHk7Yd", '{"client_secret": "abc123def456ghi"}', '{"password":"Sunshine99"}',
    '{"accessKey": "Zx9qQ8wW7eE6"}', '{"privateKey": "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC"}',
    '{"auth": {"token": "a1b2c3d4e5f6g7h8"}}', '{"bearerToken": "abcdEFGHijkl1234"}',
    "curl -H 'Authorization: Bearer abcd1234efgh5678' https://x", "curl -u admin:S3cretPass https://x",
    "mysql -u root --password=Sup3rS3cret db", "docker login -p Hunter2Hunter2 reg",
    "git clone https://oauth2:glpat-" + "x" * 20 + "@gitlab.com/a/b", "export API_KEY=\"Zx9qQ8wW7eE6rR5tT4yY\"",
    "sshpass -p 'Zx9qQ8wW7eE6' ssh host", "--client-secret Zx9qQ8wW7eE6", "API_KEY = 'Zx9qQ8wW7eE6rR5tT4yY'",
    "password = \"Sunshine99\"", "client = Client(api_key='Zx9qQ8wW7eE6rR5tT4yY')", "self.secret = 'Zx9qQ8wW7eE6rR5t'",
    "os.environ['OPENAI_API_KEY'] = 'Zx9qQ8wW7eE6rR5tT4yY'", "token='abcd1234efgh5678'",
    "Use the token `abcd1234efgh5678wxyz` to log in.", "My password is Sunshine99, don't tell.",
    "      env:\n        NPM_TOKEN: npm_" + "a1" * 18, "        password: Zx9qQ8wW7eE6",
    "        with:\n          token: " + G + "B" * 36, "    api-key: Zx9qQ8wW7eE6rR5t",
]
NONSECRETS_4 = [
    "auth: required", "token_limit: 4096", "password_min_length: 12", "key: Enter", "sort_key: created_at",
    "secret_name: my-app-secret", "api_key_header: X-API-Key", "token_ttl: 3600s", "password_reset_url: /reset",
    "auth_method: oauth", "keyboard: us", "primary_key: id", "cache_key: deps-v1", "token: ''",
    "password: ''", "password: ~", "password: !vault |", "secret: !Ref DbSecret", "password: !Sub '${DbPass}'",
    "auth: AWS_IAM", "authType: OAUTH2", "tokenType: Bearer", "secretRef: db-credentials",
    "passwordPolicy: Strong", "auth: CognitoUserPools", "auth: IAM", "secret: SecretName",
    "key: MyDocumentKey", "key: sk-proj placeholder text",
    "API_KEY=", "API_KEY=changeme", "API_KEY=your_api_key_here", "API_KEY=<your-key>", "DB_PASSWORD=${DB_PASSWORD}",
    "TOKEN=xxxxxxxx", "SECRET_KEY=replace-me", "AUTH_PROVIDER=github", "PASSWORD_HASH_ROUNDS=10",
    "API_KEY=REPLACE_ME", "NEXTAUTH_SECRET=generate-with-openssl", "SECRET=CHANGEME",
    '{"token": "${GITHUB_TOKEN}"}', '{"apiKeyHelper": "~/bin/key.sh"}', '{"auth": "none"}',
    '{"keybindings": "default"}', '{"password": ""}', '{"tokenizer": "cl100k_base"}',
    '{"authorization": "required"}',
    "export TOKEN=$(gh auth token)", "export API_KEY=\"$(cat ~/.key)\"", "read -s PASSWORD",
    "gh auth login --with-token < token.txt", "ssh-keygen -t ed25519 -f ~/.ssh/key", "PASSWORD=$1",
    "TOKEN=\"${1:-}\"", "--token-file /etc/token", "kubectl create secret generic db --from-file=./pw",
    "password = getpass.getpass()", "api_key = os.getenv('API_KEY')", "token = request.headers['Authorization']",
    "secret = config.get('secret')", "self.password = password", "api_key = settings.API_KEY",
    "password = input('Password: ')", "token = None", "secret_key = os.environ.get(\"SECRET_KEY\")",
    "key = 'name'", "auth = HTTPBasicAuth(user, pw)", "token = generate_token()", "password = hash_pw(raw)",
    "self.token = token or self._fetch_token()",
    "The auth: flow is described below.", "Set your token in the settings page.",
    "token authentication is required", "Pass the token to the API.", "The password: must be 12 characters.",
    "Your API key: find it in the dashboard.", "- **token**: string, the access token",
    "| password | string | the user's password |", "Token management is hard.",
    "Use a Bearer token for auth.", "Authorization: Bearer <token>", "Authorization: Bearer $TOKEN",
    "tokenization strategies differ", "See token_budget: unlimited for details.",
    "the token: abc", "Run `loadout auth login` first.",
    "        token: ${{ secrets.GITHUB_TOKEN }}", "      GH_TOKEN: ${{ github.token }}",
    "          password: ${{ secrets.DOCKER_PASSWORD }}", "    permissions:\n      id-token: write",
    "      - uses: actions/checkout@v4\n        with:\n          persist-credentials: false",
    "          key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}",
    "          restore-keys: |\n            ${{ runner.os }}-pip-", "      NODE_AUTH_TOKEN: ${{secrets.NPM_TOKEN}}",
    "          registry-url: https://registry.npmjs.org", "        secrets: inherit",
    "          api-key: ${{ secrets.API_KEY }}", "      id-token: write",
    "          token: ${{ steps.app.outputs.token }}", "          password: ${{ env.PW }}",
]
# probe2.py: code lines (the I1 list is a subset)
PROBE_CODE = [
    'api_key = os.getenv("API_KEY", "")', 'token = os.environ.get("TOKEN", None)', 'password = getpass.getpass("Password: ")',
    "secret = load_secret(name, default)", 'api_key: str = Field(..., env="API_KEY")', "token = jwt.encode(payload, key)",
    "const token = await getToken();", "password: Optional[str] = None", 'api_key=os.environ["OPENAI_API_KEY"],',
    'token = f"Bearer {access}"', "auth = (user, password)", "self.api_key = api_key or os.getenv('X')",
    'password = kwargs.get("password")', "token: str", "secret_key = secrets.token_hex(32)",
    "password = bcrypt.hashpw(pw, salt)", "  token: ${{ secrets.X }}", "token = tokens[i]", "token = next(it)",
    "api_key = cfg['api_key']", "TOKEN=$(cat token)", 'password=""',
]

# The baseline exempts the reviewer-labelled non-secrets, the I1 code lines, the placeholder words the M3 rule
# names (9b59606 flagged `password: required`, `PASSWORD=CHANGEME`, ...) and one probe2 code line (an env lookup).
EXEMPT = (EXEMPT_3 | set(NONSECRETS_4) | set(CODE_LINES) | set(M3_PLACEHOLDERS)
          | {'api_key=os.environ["OPENAI_API_KEY"],'})
ALL_INPUTS = list(dict.fromkeys(ALL_INPUTS_3 + SECRETS_4 + NONSECRETS_4 + PROBE_CODE + M3_SECRETS
                                + M3_PLACEHOLDERS + EXTRA_SECRETS))


@pytest.mark.parametrize("text", CODE_LINES)
def test_code_lines_are_not_secrets(text):
    assert secrets.redact(text) == text


@pytest.mark.parametrize("text", M3_SECRETS)
def test_word_like_password_values_are_secrets(text):
    assert secrets.redact(text) != text


@pytest.mark.parametrize("text", M3_PLACEHOLDERS)
def test_placeholder_words_and_references_under_password_keys_are_not(text):
    assert secrets.redact(text) == text


@pytest.mark.parametrize("text", EXTRA_SECRETS)
def test_more_secret_shapes_flagged(text):
    out = secrets.redact(text)
    assert out != text
    assert not any(s in out for s in ("Sunshine99", "S3cretPass", "Sup3rS3cret", "Zx9qQ8wW7eE6"))


@pytest.mark.parametrize("rev", ["04cb6b6", "43d0c4f", "9b59606", "be59c0e"])
def test_nothing_flagged_at_an_older_revision_is_unflagged_now(rev, tmp_path):
    old = _old_redact(rev, tmp_path)
    lost = [t for t in ALL_INPUTS if t not in EXEMPT and old(t) != t and secrets.redact(t) == t]
    assert lost == []


def test_nothing_flagged_before_this_pass_is_unflagged_now(tmp_path):
    old = _old_redact("abd6583", tmp_path)
    lost = [t for t in ALL_INPUTS if t not in EXEMPT and old(t) != t and secrets.redact(t) == t]
    assert lost == []


N = 100_000
REDOS = {  # redos4.py, plus inputs for the new rules
    "call-parens": "password: a(" + "(" * N,
    "call-long": "password = f" + "a." * (N // 2) + "(" + "x" * 10,
    "call-nested": "password = " + "a(" * (N // 2),
    "env-lookup": "password: process.env." + "a" * N,
    "words-seg": "password: " + "ab-" * (N // 3),
    "words-digit": "password: " + "a1." * (N // 3),
    "camel": "x" + "aKey" * (N // 4) + ": vvvvvvvvvv",
    "upper": "A" * N + "PASSWORD: x1y2z3w4v5",
    "id-tail": "key" + "_id" * (N // 3) + ": abcdefgh12",
    "seps": "a" + "_." * (N // 2) + "key: abcdefgh12",
    "prose-token": ("token " + "Abcdefghijklmno ") * (N // 22),
    "dollar": "password: " + "$" * N,
    "lines-call": ("password = f(a, b)\n") * (N // 19),
    "lines-camel": ("aKey: Zx9qQ8wW7eE6\n") * (N // 20),
    "nul-ish": ("password:\t" + "x" * 30 + "\n") * (N // 42),
    "brace": "password: " + "{{" * (N // 2),
    "eq-many": "a=" * (N // 2),
    "bearer": "Bearer " + "a" * N,
    # new rules
    "index-open": "token = a" + "[" * N,
    "fstring": 'token = f"' + "{a}" * (N // 3),
    "annotation": "password: " + "Optional[" * (N // 9) + "= x",
    "annotation-eq": "password: str" + " " * N + "= None",
    "curl-u": "curl -u " + "a" * N + ":",
    "curl-u-many": "curl -u a:b " * (N // 12),
    "flag-eq": "--password=" * (N // 11),
    "sshpass": "sshpass -p " * (N // 11),
    "kwarg": "Client(" + "api_key=" * (N // 8),
    "json-compact": '{"password":"' * (N // 13),
}


@pytest.mark.parametrize("name", list(REDOS))
def test_redact_linear_on_adversarial_input(name):
    text = REDOS[name]
    best = None
    for _ in range(3):
        t = time.perf_counter()
        secrets.redact(text)
        d = time.perf_counter() - t
        best = d if best is None else min(best, d)
    assert best < 3.0  # the target is under 0.5 s (see the fix pass 4 report); 3 s leaves room for slow CI


@pytest.mark.parametrize("line", ["password: Summer(2024)!x", "password: P4ss[w0rd]!",
                                  "secret = Xk9(mQ2)pLz7", "api_key: abc[1]def9Zq"])
def test_values_that_only_start_like_code_are_still_secrets(line):
    from loadout import secrets
    assert secrets.redact(line) != line, line


@pytest.mark.parametrize("line", ['api_key = os.getenv("API_KEY", "")', "password = getpass.getpass('Password: ')",
                                  "token = tokens[i]", "api_key = cfg['api_key']", "secret = load_secret(name, default),",
                                  "token = jwt.encode(payload, key)  # sign", "auth = HTTPBasicAuth(user, pw);"])
def test_closed_calls_and_indexes_are_code(line):
    from loadout import secrets
    assert secrets.redact(line) == line, line


def test_long_call_chains_are_linear_and_do_not_recurse():
    import time
    from loadout import secrets
    line = "token = a.b(1)" + ".c(2)" * 20000
    start = time.monotonic()
    assert secrets.redact(line) == line  # a closed chain is code
    assert time.monotonic() - start < 3.0
