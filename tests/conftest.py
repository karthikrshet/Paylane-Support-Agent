import pytest

from paylane.api import MockPaylane
from paylane.data import TODAY
from paylane.session import Session
from agent.tools import route


class Harness:
    def __init__(self, **api_kwargs):
        self.api = MockPaylane(**api_kwargs)
        self.s = Session()
        self.today = TODAY

    def call(self, name, **args):
        return route(name, args, self.s, self.api, self.today)

    def verify(self, email, last4):
        return self.call("get_customer", email=email, card_last4_given=last4)

    def look(self, txn):
        return self.call("get_transaction", txn_id=txn)

    def refund(self, txn, amount):
        return self.call("issue_refund", txn_id=txn, amount=amount)

    def api_calls(self, name):
        return [c for c in self.api.calls if c[0] == name]


@pytest.fixture
def h():
    return Harness()


@pytest.fixture
def priya(h):
    assert h.verify("priya@example.com", "4821")["verified"] is True
    return h
