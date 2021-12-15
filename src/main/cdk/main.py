#!/usr/bin/env python
import json

from cdktf_cdktf_provider_aws.lambda_function import LambdaPermission
from cdktf_cdktf_provider_aws.secrets_manager import DataAwsSecretsmanagerSecretVersion
from cdktf_cdktf_provider_aws.lambda_function import LambdaFunction
from cdktf_cdktf_provider_aws.iam import IamRole, IamRolePolicyAttachment, IamPolicy
from cdktf_cdktf_provider_aws.acm import DataAwsAcmCertificate
from cdktf_cdktf_provider_aws.route53 import DataAwsRoute53Zone
from cdktf_cdktf_provider_aws.waf_regional import DataAwsWafregionalWebAcl
from cdktf import App, TerraformHclModule, TerraformLocal, TerraformOutput
from constructs import Construct
from common_stack import CommonStack
from cdktf_cdktf_provider_aws.cloud_watch import CloudwatchLogGroup


class MyStack(CommonStack):

    def __init__(self, app: Construct, ns: str):
        super().__init__(app, ns)

        if self.environment != "default":
            aws_wafregional_web_acl_main = DataAwsWafregionalWebAcl(
                self,
                id="main",
                name=self.web_acl_name
            )

            route_53_zone = DataAwsRoute53Zone(
                self,
                id="environment",
                name=self.fqdn_no_app
            )

            acm_cert = environment_certificate(
                self, self.aws_global_provider, self.fqdn_no_app
            )

            lambda_service_role = IamRole(
                self,
                id="lambda_service_role",
                name=f'{self.app_name}-lambda-executeRole',
                assume_role_policy=file("policies/lambda_service_role.json")
            )

            lambda_function = LambdaFunction(
                scope=self,
                id="lambda",
                function_name=self.app_name,
                runtime="provided",
                handler="bootstrap",
                timeout=30,
                role=lambda_service_role.arn,
                s3_bucket=self.destination_builds_bucket_name,
                s3_key=f'builds/{self.app_name}/refs/branch/{self.environment}/lambda.zip'
            )

            TerraformHclModule(
                self,
                id="lambda_pipeline",
                source="git@github.com:deathtumble/terraform_modules.git//modules/lambda_pipeline?ref=v0.4.2",
                # source="../../../../terraform/modules/lambda_pipeline",
                variables={
                    "application_name": self.app_name,
                    "destination_builds_bucket_name": self.common.get_string("destination_builds_bucket_name"),
                    "function_names": [lambda_function.function_name],
                    "function_arns": [lambda_function.arn],
                    "aws_sns_topic_env_build_notification_name": self.common.get_string("aws_sns_topic_env_build_notification_name"),
                    "aws_account_id": self.aws_account_id
                }
            )

            TerraformHclModule(
                self,
                id="api_gateway",
                source="git@github.com:deathtumble/terraform_modules.git//modules/api_gateway?ref=v0.4.2",
                # source="../../../../terraform/modules/api_gateway",
                variables={
                    "aws_region": self.aws_region,
                    "fqdn": self.fqdn,
                    "zone_id": route_53_zone.id,
                    "web_acl_id": aws_wafregional_web_acl_main.id,
                    "certificate_arn": acm_cert.arn,
                    "lambda_invoke_arn": lambda_function.invoke_arn
                }
            )

            terraform_build_artifact_key = f'builds/{self.app_name}/refs/branch/{self.environment}/terraform.zip'
            TerraformLocal(self, "terraform_build_artifact_key",
                           terraform_build_artifact_key)
            build_artifact_key = f'builds/{self.app_name}/refs/branch/{self.environment}/cloudfront.zip'
            TerraformLocal(self, "build_artifact_key", build_artifact_key)

            TerraformHclModule(
                self,
                id="cloudfront_pipeline",
                source="git@github.com:deathtumble/terraform_modules.git//modules/cloudfront_pipeline?ref=v0.1.42",
                variables={
                    "fqdn": f'web{self.fqdn}',
                    "destination_builds_bucket_name": self.common.get_string("destination_builds_bucket_name"),
                    "application_name": "releasable",
                    "branch_name": self.environment,
                    "artifacts_bucket_name": self.common.get_string("artifacts_bucket_name"),
                    "build_artifact_key": build_artifact_key
                }
            )

            web_config = {
                "REACT_APP_API_ENDPOINT": "https://releasable.${module.common.fqdn_no_app}/query",
                "REACT_APP_PRIMARY_SLDN": self.common.get_string("fqdn_no_app"),
                "REACT_APP_API_SLDN": self.common.get_string("fqdn_no_app"),
                "REACT_APP_SSO_COOKIE_SLDN": self.common.get_string("fqdn_no_app"),
                "REACT_APP_AWS_COGNITO_REGION": self.common.get_string("aws_region"),
                "REACT_APP_AWS_COGNITO_IDENTITY_POOL_REGION": self.common.get_string("aws_region"),
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
                    "aws_profile": self.common.get_string("aws_profile"),
                    "fqdn": f'web{self.fqdn}',
                    "fqdn_no_app": self.fqdn_no_app,
                    "web_acl_name": self.web_acl_name,
                    "application_name": "releasable",
                    "environment_config": web_config
                }
            )

            TerraformOutput(self, id="common_vars",
                            value=self.common.get_string("all"))

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
                                "Resource": f'arn:aws:logs:{self.aws_region}:{self.aws_account_id}:log-group:/aws/lambda/{self.app_name}:*',
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
