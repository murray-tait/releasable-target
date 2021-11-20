from constructs import Node

import os


def get_config(scope, context_name, environment_variable_name, default=None):
    node = Node.of(scope)
    config = os.environ.get(environment_variable_name)
    config = config or node.try_get_context(context_name)
    config = config or default
    return config
