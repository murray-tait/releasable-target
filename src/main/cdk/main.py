#!/usr/bin/env python
from cdktf_cdktf_provider_aws import AwsProvider, AwsProviderAssumeRole
from common_stack import CommonStack
from constructs import Construct
from cdktf import App, TerraformHclModule
from cdktf_cdktf_provider_aws.waf_regional import DataAwsWafregionalWebAcl
from cdktf_cdktf_provider_archive import ArchiveProvider
from cdktf_cdktf_provider_aws.route53 import DataAwsRoute53Zone
from cdktf_cdktf_provider_aws.acm import DataAwsAcmCertificate
from cdktf_cdktf_provider_aws.iam import IamRole
from cdktf_cdktf_provider_aws.lambda_function import LambdaFunction


class MyStack(CommonStack):

    def __init__(self, scope: Construct, ns: str):
        super().__init__(scope, ns)

        aws_global_provider = self.create_providers()

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
            provider=aws_global_provider,
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
            id="api_gateway",
            source="../../../../terraform/modules/api_gateway",
            variables={
                "aws_region": self.aws_region,
                "fqdn": self.fqdn,
                "zone_id": route_53_zone.id,
                "web_acl_id": aws_wafregional_web_acl_main.id,
                "certificate_arn": acm_cert.arn,
                "lambda_invoke_arn": lambda_function.invoke_arn
            }
        )

    def create_providers(self):
        profile = None
        assume_role = None
        if self.use_role_arn:
            assume_role = AwsProviderAssumeRole(
                self, role_arn=self.aws_role_arn)
        else:
            profile = self.aws_profile

        AwsProvider(
            self, id="aws", region="eu-west-1", profile=profile, assume_role=assume_role)

        aws_global_provider = AwsProvider(
            self, id="global_aws", region="us-east-1", profile=profile, assume_role=assume_role, alias="global"
        )

        ArchiveProvider(self, "archive")

        return aws_global_provider


def file(file_name: str) -> str:
    f = open(file_name, "r")
    return f.read()


app = App()
stack = MyStack(app, "release")
app.synth()
