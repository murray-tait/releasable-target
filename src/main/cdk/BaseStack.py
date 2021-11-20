import boto3
from cdktf import TerraformStack, TerraformLocal, S3Backend
from constructs import Construct, Node

import os


class BaseStack(TerraformStack):

    def __init__(self, scope: Construct):
        self._scope = scope
        ns = self._get_app_name()
        super().__init__(scope, ns)
        self._ns = ns

    def populate(self) -> None:
        tldn = self._get_top_level_domain_name()

        locals = self.get_locals_from_account_tags()

        locals["domain"] = self._get_top_level_domain_name()

        for key, value in locals.items():
            TerraformLocal(self, key, value)

        terraform_state_account_id = locals["terraform_state_account_id"]
        terraform_state_account_name = locals["terraform_state_account_name"]
        self.create_backend(tldn, terraform_state_account_name,
                            terraform_state_account_id)

    def create_backend(self, tldn, terraform_state_account_name, terraform_state_account_id):
        bucket = tldn + '.' + \
            terraform_state_account_name + '.terraform'
        dynamo_table = tldn + '.' + \
            terraform_state_account_name + '.terraform.lock'

        backend_args = {
            'region': "eu-west-1",
            'key': self._ns + '/terraform.tfstate',
            'bucket': bucket,
            'dynamodb_table': dynamo_table,
            'acl': "bucket-owner-full-control"
        }

        use_role_arn = self._get_use_terraform_state_role_arn()
        if use_role_arn:
            backend_args["role_arn"] = 'arn:aws:iam::' + \
                terraform_state_account_id + ':role/TerraformStateAccess'
        else:
            backend_args['profile'] = terraform_state_account_id + \
                "_TerraformStateAccess"

        S3Backend(self, **backend_args)

    def get_locals_from_account_tags(self):
        accounts_profile = self._get_accounts_profile()

        environment = self._get_environment()

        locals = {}

        session = boto3.Session(profile_name=accounts_profile)
        client = session.client('organizations')

        accounts = client.list_accounts()['Accounts']

        account_ids = {}
        for account in accounts:
            account_ids[account['Name']] = account['Id']

        for account in accounts:
            account_name = account['Name']
            account_id = account['Id']

            if account_name == environment:
                locals["aws_account_id"] = account_id

            tags = client.list_tags_for_resource(ResourceId=account_id)

            for tag in tags['Tags']:
                key = tag['Key'].replace('-', '_')
                value = tag['Value']
                children_key = key + '_children_account_ids'
                local_account_id_key = key + '_account_id'
                local_account_name_key = key + "_account_name"

                if value == environment:
                    if children_key not in locals:
                        locals[children_key] = []
                    locals[children_key].append(account_id)

                if account_name == environment:
                    locals[local_account_id_key] = account_ids[value]
                    locals[local_account_name_key] = value

        return locals

    def _get_environment(self):
        environment = None
        with open(self._scope.outdir + '/.terraform/environment', 'r') as reader:
            environment = reader.read()
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
