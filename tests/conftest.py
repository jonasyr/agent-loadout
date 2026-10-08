import pytest

from loadout import runner


class FakeRunner:
    """Records commands; returns canned results matched by command prefix."""

    def __init__(self):
        self.calls = []
        self.responses = {}
        self.missing = set()

    def __call__(self, cmd, cwd=None, timeout=300):
        self.calls.append(list(cmd))
        for prefix, result in self.responses.items():
            if tuple(cmd[: len(prefix)]) == prefix:
                return result
        return runner.Result(0, "", "")

    def have(self, binary):
        return binary not in self.missing


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("LOADOUT_PERSONAL", raising=False)
    return home


@pytest.fixture
def fake_runner(monkeypatch):
    fake = FakeRunner()
    monkeypatch.setattr(runner, "run", fake)
    monkeypatch.setattr(runner, "have", fake.have)
    return fake


@pytest.fixture
def kit_root():
    from loadout import paths
    return paths.kit_root()
