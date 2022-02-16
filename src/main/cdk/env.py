#!/usr/bin/env python
from constructs import Construct


def get_environment(scope: Construct, ns: str):
    environment = None
    with open(scope.outdir + '/stacks/' + ns + '/.terraform/environment', 'r') as reader:
        environment = reader.read().split()[0]
    return environment