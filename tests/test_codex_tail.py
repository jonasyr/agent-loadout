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
