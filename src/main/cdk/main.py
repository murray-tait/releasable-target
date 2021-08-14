#!/usr/bin/env python
from constructs import Construct, Node
from cdktf import App, TerraformStack, TerraformVariable, TerraformLocal, S3Backend
from imports.aws import Instance
import boto3
import json
import traceback
import sys
import os


def get_config(scope, environment_name, context_name, default=None):
    node = Node.of(scope)
    config = os.environ.get(environment_name)
    config = config or node.try_get_context(context_name) or default
    return config


class MyStack(TerraformStack):

    def __init__(self, scope: Construct, ns: str):
        super().__init__(scope, ns)

        accounts_profile = get_config(
            scope, 'CDKTF_ACCOUNT_PROFILE', "accountsProfile")
        use_terraform_state_role_arn = get_config(
            scope, 'CDKTF_USE_TERRAFORM_STATE_ROLE_ARN', 'use_terraform_state_role_arn')
        top_level_domain_name = get_config(scope,
                                           "CDKTF_TOP_LEVEL_DOMAIN_NAME", "top_level_domain_name")

        environment = ''
        terraform_state_account_id = ''
        terraform_state_account_name = ''
        with open(scope.outdir + '/.terraform/environment', 'r') as reader:
            environment = reader.read()

        session = boto3.Session(profile_name=accounts_profile)
        client = session.client('organizations')
        organizations_json = client.describe_organization()

        accounts = client.list_accounts()['Accounts']

        account_ids = {}
        for account in accounts:
            account_ids[account['Name']] = account['Id']

        locals = {}

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
                    if key == 'terraform_state':
                        terraform_state_account_id = account_ids[value]
                        terraform_state_account_name = value

        locals["domain"] = top_level_domain_name

        for key, value in locals.items():
            TerraformLocal(self, key, value)

        bucket = ''
        dynamo_table = ''

        bucket = top_level_domain_name + '.' + \
            terraform_state_account_name + '.terraform'
        dynamo_table = top_level_domain_name + '.' + \
            terraform_state_account_name + '.terraform.lock'

        backend_args = {'scope': self, 'region': "eu-west-1",
                        'key': ns + '/terraform.tfstate',
                        'bucket': bucket,
                        'dynamodb_table': dynamo_table,
                        'acl': "bucket-owner-full-control"}

        if use_terraform_state_role_arn:
            backend_args["role_arn"] = 'arn:aws:iam::' + \
                terraform_state_account_id + ':role/TerraformStateAccess'
        else:
            backend_args['profile'] = terraform_state_account_id + \
                "_TerraformStateAccess"

        S3Backend(**backend_args)


app = App()
app_name = get_config(app, 'CDKTF_APP_NAME', 'appName', 'environment')
try:
    stack = MyStack(app, app_name)
except Exception as e:
    try:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception(exc_type, exc_value, exc_traceback,
                                  limit=2, file=sys.stdout)
    except Exception as e:
        print(str(e))

app.synth()
