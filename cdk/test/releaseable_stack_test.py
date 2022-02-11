
from ..releasable_stack import ReleasableStack


class ReleasableStackTest:

    def test_happy_path():
        stack = ReleasableStack()
        assert stack is not None
