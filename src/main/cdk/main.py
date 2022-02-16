#!/usr/bin/env python
from cdktf import App

from releasable_stack import ReleasableStack


app = App()
stack = ReleasableStack(app, "release")
app.synth()
