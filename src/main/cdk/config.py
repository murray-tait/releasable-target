from constructs import Node, Construct

import os


class Config():

    def __init__(self, app: Construct, ns: str):
        self._scope = app
        self._ns = ns

        self.accounts_profile = self._get_accounts_profile()
        self.tldn = self._get_top_level_domain_name()
        self.use_role_arn = self._get_use_terraform_state_role_arn()
        self.app_name = self._get_app_name()
        self.aws_region = self._get_aws_region()
        self.project_name = self._project_name()

    def _get_use_terraform_state_role_arn(self):
        return self._get_config("use_terraform_state_role_arn", "CDKTF_USE_TERRAFORM_STATE_ROLE_ARN", False)

    def _get_top_level_domain_name(self):
        return self._get_config("top_level_domain_name", "CDKTF_TOP_LEVEL_DOMAIN_NAME")

    def _get_accounts_profile(self):
        return self._get_config("accounts_profile", "CDKTF_ACCOUNT_PROFILE")

    def _get_app_name(self):
        return self._get_config("app_name", "CDKTF_APP_NAME")

    def _get_aws_region(self):
        return self._get_config("aws_region", "CDKTF_AWS_REGION")

    def _project_name(self):
        return self._get_config("project_name", "CDKTF_PROJECT_NAME")

    def _get_config(self, context_name, environment_variable_name, default=None):
        node = Node.of(self._scope)
        config = os.environ.get(environment_variable_name)
        config = config or node.try_get_context(context_name) or default
        return config
