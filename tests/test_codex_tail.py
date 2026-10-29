from loadout import codex, runner

GIT = ("Cloning into '/home/u/.codex/.tmp/marketplaces/.staging/marketplace-linux-uVGJ1X/checkout'...\n"
       "error: RPC failed; curl 56 Recv failure: Connection reset by peer\n"
       "error: 13993 bytes of body are still expected\n"
       "fetch-pack: unexpected disconnect while reading sideband packet\n"
       "fatal: early EOF\nfatal: fetch-pack: invalid index-pack output\n")


def test_tail_names_the_first_error_and_the_network():
    assert codex._tail(runner.Result(128, "", GIT)) == \
        "RPC failed; curl 56 Recv failure: Connection reset by peer (network error; loadout update retries)"


def test_tail_fatal_only_and_empty():
    assert codex._tail(runner.Result(1, "", "fatal: repository 'x' not found\n")) == "repository 'x' not found"
    assert codex._tail(runner.Result(1, "", "")) == "exit code 1"


def test_tail_keeps_a_plain_message_short():
    assert len(codex._tail(runner.Result(1, "x" * 900, ""))) <= 300


def test_auth_failure_is_not_called_a_network_error():
    # final review: a private repo or bad token is no network error, and a retry does not help
    res = runner.Result(128, "", "fatal: unable to access 'https://github.com/x/y.git/': "
                                 "The requested URL returned error: 403\n")
    assert codex.NETWORK_HINT not in codex._tail(res)


def test_capitalised_error_line_is_picked():
    res = runner.Result(1, "", "Error: failed to add marketplace\n\nCaused by:\n    0: git clone failed\n")
    assert codex._tail(res) == "failed to add marketplace"
