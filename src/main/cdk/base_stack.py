import boto3
from cdktf import TerraformStack, TerraformLocal, S3Backend
from constructs import Construct, Node

import os


class BaseStack(TerraformStack):

    def __init__(self, app: Construct, ns: str):
        super().__init__(app, ns)
        self._scope = app
        self._ns = ns
        self.environment = self._get_environment()

        self._locals = self._get_locals_from_account_tags()
        self.tldn = self._get_top_level_domain_name()
        self.use_role_arn = self._get_use_terraform_state_role_arn()
        self.app_name = self._get_app_name()

        TerraformLocal(self, "domain", self.tldn)

        self.aws_account_id = self._locals.get("aws_account_id")
        self.dns_account_id = self._locals.get("dns_account_id")
        self.build_account_id = self._locals.get("build_account_id")
        self.build_account_name = self._locals.get("build_account_name")
        self.terraform_state_account_name = self._locals.get(
            "terraform_state_account_name")
        self.terraform_state_account_id = self._locals.get(
            "terraform_state_account_id")

        self._create_backend()

    def _create_backend(self):
        bucket = self.tldn + '.' + \
            self.terraform_state_account_name + '.terraform'
        dynamo_table = self.tldn + '.' + \
            self.terraform_state_account_name + '.terraform.lock'

        backend_args = {
            'region': "eu-west-1",
            'key': self._ns + '/terraform.tfstate',
            'bucket': bucket,
            'dynamodb_table': dynamo_table,
            'acl': "bucket-owner-full-control"
        }

        if self.use_role_arn:
            backend_args["role_arn"] = 'arn:aws:iam::' + \
                self.terraform_state_account_id + ':role/TerraformStateAccess'
        else:
            backend_args['profile'] = self.terraform_state_account_id + \
                "_TerraformStateAccess"

        S3Backend(self, **backend_args)

    def _get_locals_from_account_tags(self):
        accounts_profile = self._get_accounts_profile()

        locals = {}
        session = boto3.Session(profile_name=accounts_profile)
        client = session.client('organizations')

        accounts = client.list_accounts()['Accounts']

        account_ids = {}
        for account in accounts:
            account_ids[account['Name']] = account['Id']

        locals["terraform_state_account_name"] = "build"
        locals["terraform_state_account_id"] = account_ids["build"]

        for account in accounts:
            account_name = account['Name']
            account_id = account['Id']

            if account_name == self.environment:
                locals["aws_account_id"] = account_id

            tags = client.list_tags_for_resource(ResourceId=account_id)

            for tag in tags['Tags']:
                key = tag['Key'].replace('-', '_')
                value = tag['Value']
                children_key = key + '_children_account_ids'
                local_account_id_key = key + '_account_id'
                local_account_name_key = key + "_account_name"

                if value == self.environment:
                    if children_key not in locals:
                        locals[children_key] = []
                    locals[children_key].append(account_id)

                if account_name == self.environment:
                    locals[local_account_id_key] = account_ids[value]
                    locals[local_account_name_key] = value

        for key, value in locals.items():
            TerraformLocal(self, key, value)

        return locals

    def _get_environment(self):
        environment = None
        try:
            with open(self._scope.outdir + '/stacks/' + self._ns + '/.terraform/environment', 'r') as reader:
                environment = reader.read()
        except:
            pass
        return environment

    def _get_use_terraform_state_role_arn(self):
        return self._get_config("use_terraform_state_role_arn", "CDKTF_USE_TERRAFORM_STATE_ROLE_ARN", False)

    def _get_top_level_domain_name(self):
        return self._get_config("top_level_domain_name", "CDKTF_TOP_LEVEL_DOMAIN_NAME")

    def _get_accounts_profile(self):
        return self._get_config("accounts_profile", "CDKTF_ACCOUNT_PROFILE")

    def _get_app_name(self):
        return self._get_config("app_name", "CDKTF_APP_NAME")

    def _get_config(self, context_name, environment_variable_name, default=None):
        node = Node.of(self._scope)
        config = os.environ.get(environment_variable_name)
        config = config or node.try_get_context(context_name) or default
        return config
