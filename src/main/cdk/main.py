#!/usr/bin/env python
from cdktf import App

from releasable_stack import ReleasableStack
from constructs import Construct


def file(file_name: str) -> str:
    f = open(file_name, "r")
    return f.read()


app = App()
stack = ReleasableStack(app, "release")
app.synth()

def get_environment(scope: Construct, ns: str):
    environment = None
    with open(scope.outdir + '/stacks/' + ns + '/.terraform/environment', 'r') as reader:
        environment = reader.read().split()[0]
    return environment