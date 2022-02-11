#!/usr/bin/env python
from cdktf import App

from releasable_stack import ReleasableStack


def file(file_name: str) -> str:
    f = open(file_name, "r")
    return f.read()


app = App()
stack = ReleasableStack(app, "release")
app.synth()
