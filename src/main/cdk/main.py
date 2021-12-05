#!/usr/bin/env python
from cdktf_cdktf_provider_aws import AwsProvider, AwsProviderAssumeRole
from base_stack import BaseStack
from constructs import Construct
from cdktf import App, TerraformHclModule
from cdktf_cdktf_provider_aws.waf_regional import DataAwsWafregionalWebAcl
from cdktf_cdktf_provider_archive import ArchiveProvider
from cdktf_cdktf_provider_aws.route53 import DataAwsRoute53Zone
from cdktf_cdktf_provider_aws.acm import DataAwsAcmCertificate
from cdktf_cdktf_provider_aws.iam import IamRole
from cdktf_cdktf_provider_aws.lambda_function import LambdaFunction


class MyStack(BaseStack):

    def __init__(self, scope: Construct, ns: str):
        super().__init__(scope, ns)

        common = TerraformHclModule(
            self,
            id="common",
            source="../../../../terraform/modules/common/",
            variables={
                "application_name": "build",
                "project_name": "experiment",
                "domain": self.tldn,
                "aws_account_id": self.aws_account_id,
                "dns_account_id": self.dns_account_id,
                "build_account_id": self.build_account_id,
                "build_account_name": self.build_account_name,
                "terraform_state_account_name": self.terraform_state_account_name,
                "terraform_state_account_id": self.terraform_state_account_id})

        aws_global_provider = self.create_providers(common)

        aws_wafregional_web_acl_main = DataAwsWafregionalWebAcl(
            self,
            id="main",
            name=common.get_string("web_acl_name")
        )

        route_53_zone = DataAwsRoute53Zone(
            self,
            id="environment",
            name=common.get_string("fqdn_no_app")
        )

        fqdn_no_app = common.get_string("fqdn_no_app")

        acm_cert = DataAwsAcmCertificate(
            self,
            id="main_cert",
            domain=f'*.{fqdn_no_app}',
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
            s3_bucket=common.get_string("destination_builds_bucket_name"),
            s3_key=f'builds/{self.app_name}/refs/branch/{self.environment}/lambda.zip'
        )

        TerraformHclModule(
            self,
            id="api_gateway",
            source="../../../../terraform/modules/api_gateway",
            variables={
                "aws_region": common.get_string("aws_region"),
                "fqdn": common.get_string("fqdn"),
                "zone_id": route_53_zone.id,
                "web_acl_id": aws_wafregional_web_acl_main.id,
                "certificate_arn": acm_cert.arn,
                "lambda_invoke_arn": lambda_function.invoke_arn
            }
        )

    def create_providers(self, common):
        profile = None
        assume_role = None
        if self.use_role_arn:
            assume_role = AwsProviderAssumeRole(
                self, role_arn=common.get_string("aws_role_arn"))
        else:
            profile = common.get_string("aws_profile")

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
