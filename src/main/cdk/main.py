#!/usr/bin/env python
from common_stack import CommonStack
from constructs import Construct
from cdktf import App, TerraformHclModule, TerraformLocal, TerraformOutput
from cdktf_cdktf_provider_aws.waf_regional import DataAwsWafregionalWebAcl
from cdktf_cdktf_provider_aws.route53 import DataAwsRoute53Zone
from cdktf_cdktf_provider_aws.acm import DataAwsAcmCertificate
from cdktf_cdktf_provider_aws.iam import IamRole
from cdktf_cdktf_provider_aws.lambda_function import LambdaFunction


class MyStack(CommonStack):

    def __init__(self, scope: Construct, ns: str):
        super().__init__(scope, ns)

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

        acm_cert = DataAwsAcmCertificate(
            self,
            id="main_cert",
            domain=f'*.{self.fqdn_no_app}',
            types=["AMAZON_ISSUED"],
            statuses=["ISSUED"],
            provider=self.aws_global_provider,
            most_recent=True
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

        build_artifact_key = f'builds/{self.app_name}/refs/branch/{self.environment}/cloudfront.zip'
        TerraformLocal(self, "build_artifact_key", build_artifact_key)

        TerraformHclModule(
            self,
            id="cloudfront_pipeline",
            source="git@github.com:deathtumble/terraform_modules.git//modules/cloudfront_pipeline?ref=v0.1.42",
            variables={
                "fqdn": f'web{self.fqdn}',
                "destination_builds_bucket_name": self.common.get_string("destination_builds_bucket_name"),
                "application_name": "releasable-target",
                "branch_name": self.environment,
                "artifacts_bucket_name": self.common.get_string("artifacts_bucket_name"),
                "build_artifact_key": build_artifact_key
            }
        )

        web_config = {
            "REACT_APP_API_ENDPOINT": "https://${var.application_name}-api.${module.common.fqdn_no_app}/query",
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
                "application_name": "releasable-target",
                "environment_config": web_config
            }
        )

        TerraformOutput(self, id="common_vars",
                        value=self.common.get_string("all"))


def file(file_name: str) -> str:
    f = open(file_name, "r")
    return f.read()


app = App()
stack = MyStack(app, "release")
app.synth()
