#!/usr/bin/env python
from constructs import Construct
from cdktf import App

from BaseStack import BaseStack


class MyStack(BaseStack):

    def __init__(self, scope: Construct, ns: str):
        super().__init__(scope, ns)


app = App()
stack = MyStack(app, "release")
app.synth()
