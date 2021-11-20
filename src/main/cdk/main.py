#!/usr/bin/env python
from constructs import Construct
from cdktf import App, TerraformStack, TerraformLocal, S3Backend

import boto3
import traceback
import sys

from config import get_config
from BaseStack import BaseStack


class MyStack(BaseStack):

    def __init__(self, scope: Construct):
        super().__init__(scope)

    def populate(self):
        super().populate()


app = App()
try:
    stack = MyStack(app)
    stack.populate()
    app.synth()
except Exception as e:
    try:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception(exc_type, exc_value, exc_traceback,
                                  limit=2, file=sys.stdout)
    except Exception as e:
        print(str(e))
