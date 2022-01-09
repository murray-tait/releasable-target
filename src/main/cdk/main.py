#!/usr/bin/env python
import json

from cdktf_cdktf_provider_aws.lambda_function import LambdaPermission
from cdktf_cdktf_provider_aws.secrets_manager import DataAwsSecretsmanagerSecretVersion
from cdktf_cdktf_provider_aws.lambda_function import LambdaFunction
from cdktf_cdktf_provider_aws.iam import IamRole, IamRolePolicyAttachment, IamPolicy
from cdktf_cdktf_provider_aws.acm import DataAwsAcmCertificate
from cdktf_cdktf_provider_aws.route53 import DataAwsRoute53Zone
from cdktf_cdktf_provider_aws.waf_regional import DataAwsWafregionalWebAcl
from cdktf import App, TerraformHclModule, TerraformLocal, TerraformOutput, S3Backend, TerraformStack
from cdktf_cdktf_provider_aws.cloud_watch import CloudwatchLogGroup
from constructs import Construct

from shared import Shared
from provider_factory import ProviderFactory
from accounts import Accounts
from config import Config


class MyStack(TerraformStack):

    def __init__(self, scope: Construct, ns: str):

        super().__init__(scope, ns)
        self._ns = ns

        self.environment = self._get_environment(scope, ns)

        if self.environment != "default":
            config = Config(scope, ns)
            self.accounts = Accounts(self.environment, config.accounts_profile)
            self.shared = Shared(config, self.accounts, self.environment)

            self._create_backend(config)
            self._provider_factory = ProviderFactory(
                self, config, self.shared.aws_role_arn, self.shared.aws_profile)

            self._provider_factory.build("eu-west-1")

            self.aws_global_provider = self._provider_factory.build(
                "us-east-1", "global_aws", "global")

            aws_wafregional_web_acl_main = DataAwsWafregionalWebAcl(
                self,
                id="main",
                name=self.shared.web_acl_name
            )

            route_53_zone = DataAwsRoute53Zone(
                self,
                id="environment",
                name=self.shared.environment_domain_name
            )

            lambda_service_role = IamRole(
                self,
                id="lambda_service_role",
                name=f'{config.app_name}-lambda-executeRole',
                assume_role_policy=file("policies/lambda_service_role.json")
            )

            lambda_function = LambdaFunction(
                scope=self,
                id="lambda",
                function_name=config.app_name,
                runtime="provided",
                handler="bootstrap",
                timeout=30,
                role=lambda_service_role.arn,
                s3_bucket=self.shared.destination_builds_bucket_name,
                s3_key=f'builds/{config.app_name}/refs/branch/{self.environment}/lambda.zip'
            )

            TerraformHclModule(
                self,
                id="lambda_pipeline",
                source="git@github.com:deathtumble/terraform_modules.git//modules/lambda_pipeline?ref=v0.4.2",
                # source="../../../../terraform/modules/lambda_pipeline",
                variables={
                    "application_name": config.app_name,
                    "destination_builds_bucket_name": self.shared.destination_builds_bucket_name,
                    "function_names": [lambda_function.function_name],
                    "function_arns": [lambda_function.arn],
                    "aws_sns_topic_env_build_notification_name": self.shared.aws_sns_topic_env_build_notification_name,
                    "aws_account_id": self.accounts.aws_account_id
                }
            )

            acm_cert = environment_certificate(
                self, self.aws_global_provider, self.shared.environment_domain_name
            )

            TerraformHclModule(
                self,
                id="api_gateway",
                source="git@github.com:deathtumble/terraform_modules.git//modules/api_gateway?ref=v0.4.2",
                # source="../../../../terraform/modules/api_gateway",
                variables={
                    "aws_region": config.aws_region,
                    "fqdn": self.shared.fqdn,
                    "zone_id": route_53_zone.id,
                    "web_acl_id": aws_wafregional_web_acl_main.id,
                    "certificate_arn": acm_cert.arn,
                    "lambda_invoke_arn": lambda_function.invoke_arn
                }
            )

            terraform_build_artifact_key = f'builds/{config.app_name}/refs/branch/{self.environment}/terraform.zip'
            TerraformLocal(self, "terraform_build_artifact_key",
                           terraform_build_artifact_key)
            build_artifact_key = f'builds/{config.app_name}/refs/branch/{self.environment}/cloudfront.zip'
            TerraformLocal(self, "build_artifact_key", build_artifact_key)

            TerraformHclModule(
                self,
                id="cloudfront_pipeline",
                source="git@github.com:deathtumble/terraform_modules.git//modules/cloudfront_pipeline?ref=v0.1.42",
                variables={
                    "fqdn": f'web{self.shared.fqdn}',
                    "destination_builds_bucket_name": self.shared.destination_builds_bucket_name,
                    "application_name": "releasable",
                    "branch_name": self.environment,
                    "artifacts_bucket_name": self.shared.artifacts_bucket_name,
                    "build_artifact_key": build_artifact_key
                }
            )

            web_config = {
                "REACT_APP_API_ENDPOINT": f"https://releasable.{self.shared.environment_domain_name}/query",
                "REACT_APP_PRIMARY_SLDN": self.shared.environment_domain_name,
                "REACT_APP_API_SLDN": self.shared.environment_domain_name,
                "REACT_APP_SSO_COOKIE_SLDN": self.shared.environment_domain_name,
                "REACT_APP_AWS_COGNITO_REGION": config.aws_region,
                "REACT_APP_AWS_COGNITO_IDENTITY_POOL_REGION": config.aws_region,
                "REACT_APP_AWS_COGNITO_AUTH_FLOW_TYPE": "USER_SRP_AUTH",
                "REACT_APP_AWS_COGNITO_COOKIE_EXPIRY_MINS": 55,
                "REACT_APP_AWS_COGNITO_COOKIE_SECURE": True,
            }
            TerraformLocal(self, "web_config", web_config)

            TerraformHclModule(
                self,
                id="web",
                source="git@github.com:deathtumble/terraform_modules.git//modules/web?ref=v0.4.1",
                variables={
                    "aws_profile": self.shared.aws_profile,
                    "fqdn": f'web{self.shared.fqdn}',
                    "fqdn_no_app": self.shared.environment_domain_name,
                    "web_acl_name": self.shared.web_acl_name,
                    "application_name": "releasable",
                    "environment_config": web_config
                }
            )

            DataAwsSecretsmanagerSecretVersion(
                self, id="repo_token", secret_id="repo_token")

            LambdaPermission(
                self,
                id="lambda_permission_api_gateway",
                statement_id="releasable-api-gateway-access",
                function_name="releasable",
                principal="apigateway.amazonaws.com",
                action="lambda:InvokeFunction",
                source_arn="arn:aws:execute-api:eu-west-1:481652375433:y6wsd502lh/*/*/*"
            )

            lambda_log_access = IamPolicy(
                self,
                id="lambda_log_access_policy",
                name="releasable-lambda-CloudWatchWriteAccess",
                policy=json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Action": [
                                    "logs:PutLogEvents",
                                    "logs:CreateLogStream"
                                ],
                                "Resource": f'arn:aws:logs:{config.aws_region}:{self.accounts.aws_account_id}:log-group:/aws/lambda/{config.app_name}:*',
                                "Effect":"Allow"
                            },
                            {
                                "Action": [
                                    "xray:PutTraceSegments",
                                    "xray:PutTelemetryRecords"
                                ],
                                "Resource": "*",
                                "Effect": "Allow"
                            }
                        ]
                    }
                )
            )

            IamRolePolicyAttachment(
                self,
                id="lambda_log_access_role_policy_attachement",
                role=lambda_service_role.name,
                policy_arn=lambda_log_access.arn
            )

            CloudwatchLogGroup(
                self,
                id="lambda_log_group",
                name=f'/aws/lambda/{lambda_function.function_name}',
                retention_in_days=14
            )

    def _create_backend(self, config):
        bucket = config.tldn + '.' + \
            self.accounts.terraform_state_account_name + '.terraform'
        dynamo_table = config.tldn + '.' + \
            self.accounts.terraform_state_account_name + '.terraform.lock'

        backend_args = {
            'region': "eu-west-1",
            'key': self._ns + '/terraform.tfstate',
            'bucket': bucket,
            'dynamodb_table': dynamo_table,
            'acl': "bucket-owner-full-control"
        }

        if config.use_role_arn:
            backend_args["role_arn"] = 'arn:aws:iam::' + \
                self.accounts.terraform_state_account_id + ':role/TerraformStateAccess'
        else:
            backend_args['profile'] = self.accounts.terraform_state_account_id + \
                "_TerraformStateAccess"

        S3Backend(self, **backend_args)

    @staticmethod
    def _get_environment(scope: Construct, ns: str):
        environment = None
        try:
            with open(scope.outdir + '/stacks/' + ns + '/.terraform/environment', 'r') as reader:
                environment = reader.read()
        except:
            pass
        return environment


def environment_certificate(scope, provider, environment_domain_name):
    acm_cert = DataAwsAcmCertificate(
        scope,
        id="main_cert",
        domain=f'*.{environment_domain_name}',
        types=["AMAZON_ISSUED"],
        statuses=["ISSUED"],
        provider=provider,
        most_recent=True
    )

    return acm_cert


def file(file_name: str) -> str:
    f = open(file_name, "r")
    return f.read()


app = App()
stack = MyStack(app, "release")
app.synth()
